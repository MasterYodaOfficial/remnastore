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
  pending_withdrawals: 3,
  pending_payments: 5,
  blocked_accounts: 7,
  new_accounts_last_7d: 19,
  total_wallet_balance: 45210,
  total_referral_earnings: 9200,
  pending_withdrawals_amount: 3100,
  paid_withdrawals_amount_last_30d: 11800,
  successful_payments_last_30d: 41,
  successful_payments_amount_last_30d: 58200,
  wallet_topups_amount_last_30d: 14350,
  direct_plan_revenue_last_30d: 43850,
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

    await page.getByLabel("Логин или email").fill("root@example.com");
    await page.getByLabel("Пароль").fill("wrong-password");
    await page.getByRole("button", { name: "Войти" }).click();

    await expect(page.getByText("Неверный логин или пароль.")).toBeVisible();
  });

  test("logs in through mocked API, renders dashboard, and navigates to accounts", async ({
    page,
  }) => {
    await mockAdminSession(page);
    await page.goto("/");

    await page.getByLabel("Логин или email").fill("root@example.com");
    await page.getByLabel("Пароль").fill("test-password");
    await page.getByRole("button", { name: "Войти" }).click();

    await expect(
      page.getByRole("heading", { name: "Единая операционная панель" }),
    ).toBeVisible();
    const accountsCard = page.locator(".metric-card", { hasText: "Пользователи" }).first();
    await expect(accountsCard).toBeVisible();
    await expect(accountsCard.getByText("128")).toBeVisible();

    await page.getByRole("button", { name: "Пользователи" }).click();

    await expect(
      page.getByRole("heading", { name: "telegram_id, email или username" }),
    ).toBeVisible();
    await expect(page.getByText("Список пуст. Сначала выполни поиск.")).toBeVisible();
  });

  test("clears the session on logout and returns to the login form", async ({ page }) => {
    await mockAdminSession(page);
    await page.goto("/");

    await page.getByLabel("Логин или email").fill("root@example.com");
    await page.getByLabel("Пароль").fill("test-password");
    await page.getByRole("button", { name: "Войти" }).click();

    await expect(
      page.getByRole("heading", { name: "Единая операционная панель" }),
    ).toBeVisible();

    await page.getByRole("button", { name: "Выйти" }).click();

    await expect(page.getByRole("button", { name: "Войти" })).toBeVisible();
    await expect(page.getByLabel("Пароль")).toHaveValue("");
    await expect
      .poll(() => page.evaluate(() => localStorage.getItem("remnastore_admin_token")))
      .toBeNull();
  });
});
