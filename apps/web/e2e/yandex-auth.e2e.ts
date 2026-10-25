import { expect, test } from '@playwright/test';

test('Yandex login uses the custom provider and PKCE while retaining referral intent', async ({ page }) => {
  await page.route('**/runtime-config.js', (route) => route.fulfill({
    contentType: 'application/javascript',
    body: 'window.__REMNASTORE_RUNTIME_CONFIG__ = Object.freeze({ VITE_YANDEX_AUTH_ENABLED: "true" });',
  }));
  await page.route('https://example.supabase.co/auth/v1/authorize?**', async (route) => {
    const url = new URL(route.request().url());
    expect(url.searchParams.get('provider')).toBe('custom:yandex');
    expect(url.searchParams.get('redirect_to')).toBe('http://127.0.0.1:4175/');
    expect(url.searchParams.get('code_challenge_method')).toBe('s256');
    expect(url.searchParams.get('code_challenge')).toMatch(/^[A-Za-z0-9_-]{43}$/);
    await route.fulfill({
      contentType: 'text/html',
      body: '<h1>Mock Supabase authorization</h1>',
    });
  });

  await page.goto('/?ref=YANDEX-REF');
  await expect(page.getByRole('button', { name: 'Войти с Яндекс ID' })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath('yandex-login.png'), fullPage: true });
  await page.getByRole('button', { name: 'Войти с Яндекс ID' }).click();
  await expect(page.getByRole('heading', { name: 'Mock Supabase authorization' })).toBeVisible();
  // Read the app's storage on its own origin after returning from the mocked provider.
  await page.goto('/');
  expect(await page.evaluate(() => window.localStorage.getItem('remnastore.pending_referral_code')))
    .toBe('YANDEX-REF');
});

for (const callback of [
  { query: '#error=access_denied&error_code=provider_email_needs_verification', message: 'Подтвердите почту:' },
  { query: '?error=access_denied', message: 'Вход отменён.' },
  { query: '#error=server_error&error_description=private-provider-detail', message: 'Не удалось завершить вход.' },
]) {
  test(`OAuth callback displays a safe message for ${callback.query.split('=')[1]}`, async ({ page }) => {
    await page.goto(`/${callback.query}`);
    await expect(page.getByText(callback.message, { exact: false })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Продолжить через Google' })).toBeVisible();
    await expect(page).toHaveURL('http://127.0.0.1:4175/');
    await expect(page.getByText('private-provider-detail')).toHaveCount(0);
  });
}
