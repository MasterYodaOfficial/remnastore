import { expect, test } from "@playwright/test";

const adminProfile = {
  id: "admin-1",
  username: "root",
  email: "root@example.com",
  full_name: "Root Operator",
  is_active: true,
  is_superuser: true,
  last_login_at: "2026-03-20T09:00:00Z",
  created_at: "2026-03-01T09:00:00Z",
};

const dashboardSummary = {
  total_accounts: 128,
  active_subscriptions: 64,
  accounts_with_telegram: 92,
  paying_accounts_last_30d: 31,
  pending_withdrawals: 3,
  pending_payments: 5,
  blocked_accounts: 7,
  new_accounts_last_7d: 19,
  total_wallet_balance: 45210,
  total_referral_earnings: 9200,
  pending_withdrawals_amount: 3100,
  paid_withdrawals_amount_last_30d: 11800,
  successful_payments_rub_last_30d: 29,
  successful_payments_amount_rub_last_30d: 58200,
  wallet_topups_amount_last_30d: 14350,
  direct_plan_purchases_rub_last_30d: 18,
  direct_plan_revenue_rub_last_30d: 43850,
  direct_plan_purchases_stars_last_30d: 12,
  direct_plan_revenue_stars_last_30d: 1875,
};

const accountListResponse = {
  items: [
    {
      id: "1f0f8f6d-93df-4c0b-89ad-8bcead0b0201",
      email: "user@example.com",
      display_name: "Иван Петров",
      telegram_id: 777000111,
      username: "ivan",
      status: "active",
      balance: 1500,
      subscription_status: "active",
      subscription_expires_at: "2026-04-30T09:00:00Z",
      referrals_count: 3,
      last_seen_at: "2026-04-15T08:00:00Z",
      created_at: "2026-03-10T09:00:00Z",
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
};

async function mockAdminSession(page: Parameters<typeof test>[0]["page"]) {
  await page.route("**/api/v1/admin/auth/login", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "playwright-admin-token",
        token_type: "bearer",
        admin: adminProfile,
      }),
    });
  });

  await page.route("**/api/v1/admin/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(adminProfile),
    });
  });

  await page.route("**/api/v1/admin/dashboard/summary", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(dashboardSummary),
    });
  });

  await page.route("**/api/v1/admin/accounts?*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(accountListResponse),
    });
  });

  await page.route("**/api/v1/admin/accounts/subscription-plans", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
}

test.describe("admin browser smoke", () => {
  test("shows a stable login error when backend returns admin error_code", async ({
    page,
  }) => {
    await page.route("**/api/v1/admin/auth/login", async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "invalid admin credentials",
          error_code: "admin_invalid_credentials",
        }),
      });
    });

    await page.goto("/");

    await page.getByLabel("Логин").fill("root@example.com");
    await page.getByLabel("Пароль").fill("wrong-password");
    await page.getByRole("button", { name: "Войти" }).click();

    await expect(page.getByText("Неверный логин или пароль.")).toBeVisible();
  });

  test("logs in through mocked API, renders dashboard, and navigates to accounts", async ({
    page,
  }) => {
    await mockAdminSession(page);
    await page.goto("/");

    await page.getByLabel("Логин").fill("root@example.com");
    await page.getByLabel("Пароль").fill("test-password");
    await page.getByRole("button", { name: "Войти" }).click();

    await expect(
      page.getByRole("heading", { name: "Рабочая панель сервиса" }),
    ).toBeVisible();
    const accountsCard = page.locator(".metric-card", { hasText: "Пользователи" }).first();
    await expect(accountsCard).toBeVisible();
    await expect(accountsCard.getByText("128")).toBeVisible();
    await expect(page.locator(".metric-card", { hasText: "Покупки в Telegram Stars" })).toContainText(
      "1 875 XTR",
    );

    await page.getByRole("button", { name: "Пользователи" }).click();

    await expect(
      page.getByRole("heading", { name: "Реестр пользователей" }),
    ).toBeVisible();
    await expect(page.locator("th", { hasText: "Пользователь" })).toBeVisible();
    await expect(page.getByText("Иван Петров")).toBeVisible();
  });

  test("clears the session on logout and returns to the login form", async ({ page }) => {
    await mockAdminSession(page);
    await page.goto("/");

    await page.getByLabel("Логин").fill("root@example.com");
    await page.getByLabel("Пароль").fill("test-password");
    await page.getByRole("button", { name: "Войти" }).click();

    await expect(
      page.getByRole("heading", { name: "Рабочая панель сервиса" }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Выйти" }).click();

    await expect(page.getByRole("button", { name: "Войти" })).toBeVisible();
    await expect(page.getByLabel("Пароль")).toHaveValue("");
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem("remnastore_admin_token")))
      .toBeNull();
  });
});
