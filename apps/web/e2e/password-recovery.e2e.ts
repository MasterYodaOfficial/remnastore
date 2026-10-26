import { expect, test, type Page } from '@playwright/test';
import { Buffer } from 'node:buffer';

const authKey = 'sb-example-auth-token';
const recoveryKey = 'remnastore.password_recovery_active';
const userId = '11111111-1111-4111-8111-111111111111';
const user = {
  id: userId, aud: 'authenticated', role: 'authenticated', email: 'person@example.com',
  app_metadata: { provider: 'email', providers: ['email'] }, user_metadata: {},
  created_at: '2026-01-01T00:00:00Z',
};

function session(sessionId: string) {
  const expires = Math.floor(Date.now() / 1000) + 3600;
  const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');
  return {
    access_token: `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode({ sub: userId, session_id: sessionId, exp: expires, aud: 'authenticated', role: 'authenticated' })}.mock-signature`,
    refresh_token: `refresh-${sessionId}`, token_type: 'bearer', expires_in: 3600,
    expires_at: expires, user,
  };
}

const bootstrap = {
  account: {
    id: userId, email: user.email, display_name: 'Previous user', username: null,
    telegram_id: null, balance: 100, referral_code: 'PERSON', referral_earnings: 0,
    referrals_count: 0, referred_by_account_id: null, has_used_trial: false,
    subscription_status: null, subscription_url: null, subscription_expires_at: null,
    subscription_last_synced_at: null, subscription_is_trial: false, trial_used_at: null, trial_ends_at: null,
  },
  subscription: {
    remnawave_user_uuid: null, subscription_url: null, status: null, expires_at: null,
    last_synced_at: null, is_active: false, is_trial: false, has_used_trial: false,
    trial_used_at: null, trial_ends_at: null, days_left: 0,
  },
  trial_ui: { can_start_now: true, reason: null, has_used_trial: false, checked_at: null, strict_check_required_on_start: true },
};

async function setup(page: Page, options: { verifier?: boolean; expired?: boolean; holdBootstrap?: Promise<void> } = {}) {
  const recoverySession = session('22222222-2222-4222-8222-222222222222');
  const stats = { bootstraps: 0, passwords: [] as string[], exchanges: 0 };
  await page.addInitScript(({ key, existing, verifier }) => {
    if (window.localStorage.getItem('recovery-test-initialized')) return;
    window.localStorage.setItem('recovery-test-initialized', '1');
    window.localStorage.setItem(key, JSON.stringify(existing));
    window.localStorage.setItem('remnastore.browser_access_token', 'old-browser-token');
    if (verifier) window.localStorage.setItem(`${key}-code-verifier`, JSON.stringify('verifier/PASSWORD_RECOVERY'));
  }, { key: authKey, existing: session('33333333-3333-4333-8333-333333333333'), verifier: options.verifier !== false });
  await page.route('https://telegram.org/js/telegram-web-app.js', route => route.fulfill({ contentType: 'application/javascript', body: '' }));
  await page.route('https://example.supabase.co/auth/v1/token?**', route => {
    stats.exchanges += 1;
    return options.expired
      ? route.fulfill({ status: 400, json: { code: 'otp_expired', msg: 'Expired code' } })
      : route.fulfill({ json: recoverySession });
  });
  await page.route('https://example.supabase.co/auth/v1/user', async route => {
    if (route.request().method() === 'PUT') stats.passwords.push(route.request().postDataJSON().password);
    await route.fulfill({ json: user });
  });
  await page.route('https://example.supabase.co/auth/v1/logout?**', route => route.fulfill({ json: {} }));
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith('/bootstrap/me')) {
      stats.bootstraps += 1;
      await options.holdBootstrap;
      await route.fulfill({ json: bootstrap });
    } else if (path.endsWith('/payments/plans')) await route.fulfill({ json: [] });
    else await route.fulfill({ json: { items: [], total: 0, limit: 20, offset: 0, unread_count: 0 } });
  });
  return { stats, recoverySession };
}

test('PKCE recovery survives reload and opens the cabinet only after the password is saved', async ({ page }) => {
  const { stats } = await setup(page);
  await page.goto('/?auth_action=reset-password&code=valid-code');
  await expect(page.getByRole('heading', { name: 'Новый пароль', exact: true })).toBeVisible();
  expect(stats.bootstraps).toBe(0);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Новый пароль', exact: true })).toBeVisible();
  expect(stats.exchanges).toBe(1);
  expect(stats.bootstraps).toBe(0);
  await page.getByPlaceholder('Минимум 8 символов').fill('new-valid-password');
  await page.getByPlaceholder('Повторите новый пароль').fill('new-valid-password');
  await page.getByRole('button', { name: 'Сохранить новый пароль' }).click();
  await expect.poll(() => stats.passwords).toEqual(['new-valid-password']);
  await expect(page.getByRole('button', { name: 'Настройки', exact: true })).toBeVisible();
  expect(await page.evaluate(key => window.sessionStorage.getItem(key), recoveryKey)).toBeNull();
  await expect(page).toHaveURL('http://127.0.0.1:4175/');
});

for (const verifier of [true, false]) {
  test(`invalid recovery does not use an old session (verifier: ${verifier})`, async ({ page }) => {
    const { stats } = await setup(page, { verifier, expired: true });
    await page.goto('/?auth_action=reset-password&code=expired-code');
    await expect(page.getByRole('heading', { name: 'Ссылка больше не действует' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Запросить новую ссылку' })).toBeVisible();
    expect(stats.bootstraps).toBe(0);
    expect(stats.passwords).toEqual([]);
    await expect(page.getByRole('button', { name: 'Настройки', exact: true })).toHaveCount(0);
  });
}

test('cancelling recovery clears its marker and returns to sign-in', async ({ page }) => {
  const { stats } = await setup(page);
  await page.goto('/?auth_action=reset-password&code=valid-code');
  await expect(page.getByRole('heading', { name: 'Новый пароль', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Отменить', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Продолжить через Google' })).toBeVisible();
  expect(await page.evaluate(key => window.sessionStorage.getItem(key), recoveryKey)).toBeNull();
  expect(stats.passwords).toEqual([]);
});

test('a late bootstrap cannot reopen the cabinet after PASSWORD_RECOVERY', async ({ page }) => {
  let release!: () => void;
  const holdBootstrap = new Promise<void>(resolve => { release = resolve; });
  const { stats, recoverySession } = await setup(page, { verifier: false, holdBootstrap });
  await page.goto('/');
  await expect.poll(() => stats.bootstraps).toBeGreaterThan(0);
  await page.evaluate(({ key, nextSession }) => {
    window.localStorage.setItem(key, JSON.stringify(nextSession));
    const channel = new BroadcastChannel(key);
    channel.postMessage({ event: 'PASSWORD_RECOVERY', session: nextSession });
    channel.close();
  }, { key: authKey, nextSession: recoverySession });
  await expect(page.getByRole('heading', { name: 'Новый пароль', exact: true })).toBeVisible();
  const reply = page.waitForResponse('**/api/v1/bootstrap/me');
  release();
  await (await reply).finished();
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page.getByRole('heading', { name: 'Новый пароль', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Настройки', exact: true })).toHaveCount(0);
});
