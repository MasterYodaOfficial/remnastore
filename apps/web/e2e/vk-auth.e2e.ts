import { expect, test } from '@playwright/test';

for (const width of [390, 1280]) {
  test(`VK ID starts Supabase PKCE login and retains referral at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.route('**/runtime-config.js', (route) => route.fulfill({
      contentType: 'application/javascript',
      body: 'window.__REMNASTORE_RUNTIME_CONFIG__ = Object.freeze({ VITE_VK_AUTH_ENABLED: "true", VITE_YANDEX_AUTH_ENABLED: "true" });',
    }));
    await page.route('https://example.supabase.co/auth/v1/authorize?**', async (route) => {
      const url = new URL(route.request().url());
      expect(url.searchParams.get('provider')).toBe('custom:vk');
      expect(url.searchParams.get('redirect_to')).toBe('http://127.0.0.1:4175/');
      expect(url.searchParams.get('code_challenge_method')).toBe('s256');
      expect(url.searchParams.get('code_challenge')).toMatch(/^[A-Za-z0-9_-]{43}$/);
      await route.fulfill({
        contentType: 'text/html',
        body: '<h1>Mock Supabase VK authorization</h1>',
      });
    });
    await page.goto('/?ref=VK-REF');
    const button = page.getByRole('button', { name: 'Войти с VK ID' });
    await expect(button).toBeVisible();
    await page.screenshot({ path: test.info().outputPath(`vk-login-${width}.png`), fullPage: true });
    await button.click();
    await expect(page.getByRole('heading', { name: 'Mock Supabase VK authorization' })).toBeVisible();
    await page.goto('/');
    expect(await page.evaluate(() => window.localStorage.getItem('remnastore.pending_referral_code')))
      .toBe('VK-REF');
  });
}
