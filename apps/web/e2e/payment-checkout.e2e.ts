import { expect, test } from '@playwright/test';

for (const width of [390, 1280]) {
  test(`checkout switches SBP on the same payment and survives reload at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    let succeeded = false;
    const requests: string[] = [];
    await page.route('**/api/v1/**', async route => {
      requests.push(new URL(route.request().url()).pathname);
      expect(route.request().postDataJSON()).toEqual({ ticket: 'scoped-test-ticket' });
      await route.fulfill({ json: {
        provider_payment_id: 'same-payment', amount: 500, currency: 'RUB',
        status: succeeded ? 'succeeded' : 'pending', finalized: succeeded,
        confirmation_token: succeeded ? null : 'same-confirmation-token', return_url: 'http://127.0.0.1:4175/',
      } });
    });
    await page.route('https://yookassa.ru/checkout-widget/v1/checkout-widget.js', route => route.fulfill({
      contentType: 'application/javascript', body: `
        window.widgetCalls = [];
        window.YooMoneyCheckoutWidget = class {
          constructor(options) { this.options = options; window.widgetCalls.push(options); }
          render(id) { this.container = document.getElementById(id); this.container.textContent = this.options.customization ? 'СБП QR / банк' : 'Общая форма'; return Promise.resolve(); }
          destroy() { if (this.container) this.container.textContent = ''; }
        };
      `,
    }));
    await page.goto('/checkout?payment_id=same-payment&mode=sbp#checkout_token=scoped-test-ticket');
    await expect(page.getByText('СБП QR / банк', { exact: true })).toBeVisible();
    expect(new URL(page.url()).hash).toBe('');
    await page.getByRole('button', { name: 'Все способы оплаты', exact: true }).click();
    await expect(page.getByText('Общая форма', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => Reflect.get(window, 'widgetCalls').map((call: { confirmation_token: string }) => call.confirmation_token)))
      .toEqual(['same-confirmation-token', 'same-confirmation-token']);
    await page.reload();
    await expect(page.getByText('Общая форма', { exact: true })).toBeVisible();
    const bankReturn = await page.evaluate(() => Reflect.get(window, 'widgetCalls')[0].return_url as string);
    await page.evaluate(() => window.sessionStorage.clear());
    await page.goto(bankReturn);
    await expect(page.getByText('Общая форма', { exact: true })).toBeVisible();
    succeeded = true;
    await page.getByRole('button', { name: 'Проверить оплату', exact: true }).click();
    await expect(page.getByText('Оплата завершена.', { exact: true })).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Способы оплаты' })).toHaveCount(0);
    expect(requests.every(path => path === '/api/v1/payments/yookassa/checkout')).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

test('invalid checkout link never loads a payment form', async ({ page }) => {
  let widgetRequested = false;
  await page.route('https://yookassa.ru/**', route => { widgetRequested = true; return route.abort(); });
  await page.goto('/checkout?payment_id=missing');
  await expect(page.getByRole('alert')).toContainText('Ссылка оплаты недействительна');
  expect(widgetRequested).toBe(false);
});

test('a store without SBP customization can use the general form of the same payment', async ({ page }) => {
  await page.route('**/api/v1/payments/yookassa/checkout', route => route.fulfill({ json: {
    provider_payment_id: 'same-payment', amount: 500, currency: 'RUB', status: 'pending',
    finalized: false, confirmation_token: 'same-token', return_url: 'http://127.0.0.1:4175/',
  } }));
  await page.route('https://yookassa.ru/checkout-widget/v1/checkout-widget.js', route => route.fulfill({
    contentType: 'application/javascript', body: `
      window.YooMoneyCheckoutWidget = class {
        constructor(options) { this.options = options; }
        render(id) { this.container = document.getElementById(id);
          if (this.options.customization) this.options.error_callback({ error: 'customization_of_payment_methods_not_allowed' });
          else this.container.textContent = 'Общая форма';
          return Promise.resolve();
        }
        destroy() { if (this.container) this.container.textContent = ''; }
      };
    `,
  }));
  await page.goto('/checkout?payment_id=same-payment&mode=sbp#checkout_token=test-ticket');
  await expect(page.getByRole('alert')).toContainText('Способ оплаты недоступен');
  await page.getByRole('button', { name: 'Все способы оплаты', exact: true }).click();
  await expect(page.getByText('Общая форма', { exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});
