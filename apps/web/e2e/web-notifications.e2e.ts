import { expect, test } from "@playwright/test";

const browserAccessToken = "playwright-web-browser-token";
const browserTokenStorageKey = "remnastore.browser_access_token";
const telegramAuthStorageKey = "remnastore.telegram_auth";

const bootstrapPayload = {
  account: {
    id: "account-1",
    email: "alice@example.com",
    display_name: "Alice",
    username: "alice",
    telegram_id: null,
    balance: 1250,
    referral_code: "ALICE123",
    referral_earnings: 340,
    referrals_count: 2,
    referred_by_account_id: null,
    has_used_trial: false,
    subscription_status: "ACTIVE",
    subscription_url: "https://example.com/subscription/alice",
    subscription_expires_at: "2026-04-20T09:00:00Z",
    subscription_last_synced_at: "2026-03-20T09:00:00Z",
    subscription_is_trial: false,
    trial_used_at: null,
    trial_ends_at: null,
  },
  subscription: {
    remnawave_user_uuid: "remnawave-user-1",
    subscription_url: "https://example.com/subscription/alice",
    status: "ACTIVE",
    expires_at: "2026-04-20T09:00:00Z",
    last_synced_at: "2026-03-20T09:00:00Z",
    is_active: true,
    is_trial: false,
    has_used_trial: false,
    trial_used_at: null,
    trial_ends_at: null,
    days_left: 31,
  },
  trial_ui: {
    can_start_now: true,
    reason: null,
    has_used_trial: false,
    checked_at: "2026-03-20T09:00:00Z",
    strict_check_required_on_start: true,
  },
};

function buildNotificationsResponse(unreadCount: number) {
  return {
    items: [
      {
        id: 101,
        type: "payment_succeeded",
        title: "Оплата подтверждена",
        body: "Баланс обновлен после последнего пополнения.",
        priority: "success",
        payload: null,
        action_label: null,
        action_url: null,
        read_at: unreadCount === 0 ? "2026-03-20T10:00:00Z" : null,
        is_read: unreadCount === 0,
        created_at: "2026-03-20T09:30:00Z",
      },
      {
        id: 102,
        type: "subscription_expiring",
        title: "Подписка скоро закончится",
        body: "Продлите доступ заранее, чтобы не потерять соединение.",
        priority: "warning",
        payload: null,
        action_label: "Открыть тарифы",
        action_url: "/plans",
        read_at: unreadCount === 0 ? "2026-03-20T10:00:00Z" : null,
        is_read: unreadCount === 0,
        created_at: "2026-03-20T08:45:00Z",
      },
    ],
    total: 2,
    unread_count: unreadCount,
  };
}

function buildReferralSummaryResponse(availableForWithdraw: number) {
  return {
    referral_code: "ALICE123",
    referrals_count: 2,
    referral_earnings: 340,
    available_for_withdraw: availableForWithdraw,
    effective_reward_rate: 20,
  };
}

function buildReferralFeedResponse(
  items: Array<{
    referred_account_id: string;
    display_name: string;
    created_at: string;
    reward_amount: number;
    status: "active" | "pending";
  }>,
  options: {
    total?: number;
    limit?: number;
    offset?: number;
    status?: "all" | "active" | "pending";
  } = {},
) {
  return {
    items,
    total: options.total ?? items.length,
    limit: options.limit ?? 20,
    offset: options.offset ?? 0,
    status_filter: options.status ?? "all",
  };
}

function buildWithdrawalsResponse(
  availableForWithdraw: number,
  items: Array<{
    id: number;
    amount: number;
    destination_value: string;
    user_comment?: string | null;
    status: "new" | "in_progress" | "paid" | "rejected" | "cancelled";
    created_at: string;
  }>,
) {
  return {
    items: items.map((item) => ({
      id: item.id,
      amount: item.amount,
      destination_type: "card",
      destination_value: item.destination_value,
      user_comment: item.user_comment ?? null,
      admin_comment: null,
      status: item.status,
      reserved_ledger_entry_id: null,
      released_ledger_entry_id: null,
      processed_at: null,
      created_at: item.created_at,
      updated_at: item.created_at,
    })),
    total: items.length,
    limit: 10,
    offset: 0,
    available_for_withdraw: availableForWithdraw,
    minimum_amount_rub: 300,
  };
}

async function mockAuthenticatedMobileSession(
  page: Parameters<typeof test>[0]["page"],
  options: {
    initialUnreadCount?: number;
    getBootstrapPayload?: () => typeof bootstrapPayload;
    withStoredToken?: boolean;
  } = {},
) {
  let unreadCount = options.initialUnreadCount ?? 2;

  if (options.withStoredToken !== false) {
    await page.addInitScript(([storageKey, token]) => {
      window.localStorage.setItem(storageKey, token);
    }, [browserTokenStorageKey, browserAccessToken]);
  }

  await page.route("https://telegram.org/js/telegram-web-app.js", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/javascript",
      body: "",
    });
  });

  await page.route("**/api/v1/bootstrap/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(options.getBootstrapPayload?.() ?? bootstrapPayload),
    });
  });

  await page.route("**/api/v1/notifications/unread-count", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ unread_count: unreadCount }),
    });
  });

  await page.route("**/api/v1/payments?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [],
        total: 0,
        limit: 20,
        offset: 0,
      }),
    });
  });

  await page.route("**/api/v1/notifications?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(buildNotificationsResponse(unreadCount)),
    });
  });

  await page.route("**/api/v1/referrals/summary", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(buildReferralSummaryResponse(340)),
    });
  });

  await page.route("**/api/v1/referrals/feed?**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        buildReferralFeedResponse(
          [
            {
              referred_account_id: "ref-2",
              display_name: "carol@example.com",
              created_at: "2026-03-19T09:00:00Z",
              reward_amount: 140,
              status: "active",
            },
            {
              referred_account_id: "ref-1",
              display_name: "bob@example.com",
              created_at: "2026-03-18T09:00:00Z",
              reward_amount: 200,
              status: "active",
            },
          ],
          { total: 2, limit: 20, offset: 0, status: "all" },
        ),
      ),
    });
  });

  await page.route("**/api/v1/notifications/read-all", async (route) => {
    unreadCount = 0;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ updated: true }),
    });
  });
}

test.describe("web mobile browser smoke", () => {
  test("signs in with email password and restores the browser account", async ({ page }) => {
    await mockAuthenticatedMobileSession(page, {
      initialUnreadCount: 0,
      withStoredToken: false,
    });

    await page.route("https://example.supabase.co/auth/v1/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());

      if (url.pathname.endsWith("/token") && url.searchParams.get("grant_type") === "password") {
        const payload = request.postData() ?? "";
        expect(payload).toContain("alice@example.com");
        expect(payload).toContain("supersecret123");

        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            access_token: browserAccessToken,
            token_type: "bearer",
            expires_in: 3600,
            expires_at: 1764000000,
            refresh_token: "playwright-refresh-token",
            user: {
              id: "supabase-user-1",
              aud: "authenticated",
              role: "authenticated",
              email: "alice@example.com",
              email_confirmed_at: "2026-03-20T09:00:00Z",
              phone: "",
              confirmed_at: "2026-03-20T09:00:00Z",
              last_sign_in_at: "2026-03-20T09:30:00Z",
              app_metadata: {
                provider: "email",
                providers: ["email"],
              },
              user_metadata: {
                avatar_url: null,
              },
              identities: [],
              created_at: "2026-03-20T09:00:00Z",
              updated_at: "2026-03-20T09:30:00Z",
              is_anonymous: false,
            },
          }),
        });
        return;
      }

      if (url.pathname.endsWith("/user")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            id: "supabase-user-1",
            aud: "authenticated",
            role: "authenticated",
            email: "alice@example.com",
            app_metadata: {
              provider: "email",
              providers: ["email"],
            },
            user_metadata: {
              avatar_url: null,
            },
          }),
        });
        return;
      }

      await route.abort();
    });

    await page.goto("/");

    await expect(page.getByRole("button", { name: "Войти по email" })).toBeVisible();

    await page.getByLabel("Email").fill("alice@example.com");
    await page.getByLabel("Пароль").fill("supersecret123");
    await page.getByRole("button", { name: "Войти по email" }).click();

    await expect(page.getByRole("button", { name: "Открыть уведомления" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Ваш доступ" })).toBeVisible();
    await expect(page.getByText("Alice", { exact: true })).toBeVisible();

    const storedToken = await page.evaluate((storageKey) => {
      return window.localStorage.getItem(storageKey);
    }, browserTokenStorageKey);
    expect(storedToken).toBe(browserAccessToken);
  });

  test("restores browser session, opens notifications, and marks everything as read", async ({
    page,
  }) => {
    await mockAuthenticatedMobileSession(page);
    await page.goto("/");

    const notificationsButton = page.getByRole("button", { name: "Открыть уведомления" });
    await expect(notificationsButton).toBeVisible();
    await expect(page.getByRole("button", { name: "Пополнить" })).toBeVisible();
    await expect(page.getByText(/1.?250 ₽/)).toBeVisible();
    await expect(notificationsButton.locator("span").last()).toHaveText("2");

    await notificationsButton.click();

    await expect(page.getByRole("heading", { name: "Уведомления" })).toBeVisible();
    await expect(page.getByText("2 непрочитанных из 2")).toBeVisible();
    await expect(page.getByText("Оплата подтверждена")).toBeVisible();
    await expect(page.getByText("Подписка скоро закончится")).toBeVisible();

    await page.getByRole("button", { name: "Прочитать все" }).click();

    await expect(page.getByText("Все уведомления прочитаны (2)")).toBeVisible();
    await expect(page.getByRole("button", { name: "Прочитать все" })).toBeDisabled();
  });

  test("applies promo deep link and opens settings with the code prefilled", async ({ page }) => {
    await mockAuthenticatedMobileSession(page, { initialUnreadCount: 0 });
    await page.goto("/?promo=spring20&tab=settings");

    await expect(page.getByRole("heading", { name: "Настройки" })).toBeVisible();
    await expect(
      page.getByText("Промокод перенесен из Telegram. Нажмите «Активировать», чтобы применить его."),
    ).toBeVisible();
    await expect(page.getByPlaceholder("Введите код")).toHaveValue("SPRING20");
  });

  test("opens topup modal, creates YooKassa payment, and follows confirmation redirect", async ({
    page,
  }) => {
    await mockAuthenticatedMobileSession(page, { initialUnreadCount: 0 });

    await page.route("**/api/v1/payments/yookassa/topup", async (route) => {
      const request = route.request();
      const payload = request.postDataJSON() as {
        amount_rub: number;
        success_url: string;
        description: string;
        idempotency_key: string;
      };
      const successUrl = new URL(payload.success_url);

      expect(payload.amount_rub).toBe(1000);
      expect(successUrl.origin).toBe("http://127.0.0.1:4175");
      expect(successUrl.pathname).toBe("/");
      expect(payload.description.replace(/\s+/g, " ")).toContain("1 000");
      expect(payload.idempotency_key).toContain("topup");

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          provider: "yookassa",
          flow_type: "wallet_topup",
          account_id: "account-1",
          status: "pending",
          amount: 1000,
          currency: "RUB",
          provider_payment_id: "yookassa-topup-1",
          confirmation_url: "https://pay.example/topup/confirm",
          expires_at: "2026-03-20T10:30:00Z",
        }),
      });
    });

    await page.route("https://pay.example/topup/confirm", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/html",
        body: "<html><body><h1>Mock YooKassa</h1><p>Topup confirmation page</p></body></html>",
      });
    });

    await page.goto("/");

    await page.getByRole("button", { name: "Пополнить" }).click();

    await expect(page.getByRole("heading", { name: "Пополнение баланса" })).toBeVisible();
    await page.getByRole("button", { name: /1.?000 ₽/ }).click();

    await expect(page).toHaveURL("https://pay.example/topup/confirm");
    await expect(page.getByRole("heading", { name: "Mock YooKassa" })).toBeVisible();
  });

  test("creates withdrawal request and refreshes referral payouts", async ({ page }) => {
    await mockAuthenticatedMobileSession(page, { initialUnreadCount: 0 });

    let availableForWithdraw = 340;
    let withdrawalItems: Array<{
      id: number;
      amount: number;
      destination_value: string;
      user_comment?: string | null;
      status: "new" | "in_progress" | "paid" | "rejected" | "cancelled";
      created_at: string;
    }> = [];

    await page.route("**/api/v1/referrals/summary", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(buildReferralSummaryResponse(availableForWithdraw)),
      });
    });

    await page.route("**/api/v1/withdrawals?**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(buildWithdrawalsResponse(availableForWithdraw, withdrawalItems)),
      });
    });

    await page.route("**/api/v1/withdrawals", async (route) => {
      const request = route.request();
      const payload = request.postDataJSON() as {
        amount: number;
        destination_type: string;
        destination_value: string;
        user_comment: string | null;
      };

      expect(payload.amount).toBe(320);
      expect(payload.destination_type).toBe("card");
      expect(payload.destination_value).toBe("4242424242424242");
      expect(payload.user_comment).toBe("основная карта для выплат");

      availableForWithdraw = 20;
      withdrawalItems = [
        {
          id: 501,
          amount: payload.amount,
          destination_value: "4242 4242 4242 4242",
          user_comment: payload.user_comment,
          status: "new",
          created_at: "2026-03-20T10:20:00Z",
        },
      ];

      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          id: 501,
          amount: payload.amount,
          destination_type: "card",
          destination_value: "4242 4242 4242 4242",
          user_comment: payload.user_comment,
          admin_comment: null,
          status: "new",
          reserved_ledger_entry_id: 9001,
          released_ledger_entry_id: null,
          processed_at: null,
          created_at: "2026-03-20T10:20:00Z",
          updated_at: "2026-03-20T10:20:00Z",
        }),
      });
    });

    await page.goto("/");
    await page.getByRole("button", { name: "Рефералы" }).click();

    await expect(page.getByRole("heading", { name: "Реферальная программа" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Новая заявка" })).toBeVisible();

    await page.getByRole("button", { name: "Новая заявка" }).click();

    await expect(page.getByRole("heading", { name: "Заявка на вывод" })).toBeVisible();
    await page.getByLabel("Сумма вывода").fill("320");
    await page.getByLabel("Номер карты").fill("4242 4242 4242 4242");
    await page.getByLabel("Комментарий для администратора").fill("основная карта для выплат");
    await page.getByRole("button", { name: "Отправить заявку" }).click();

    await expect(
      page.getByText("Заявка на вывод создана и отправлена на рассмотрение администратора."),
    ).toBeVisible();
    await expect(page.getByRole("heading", { name: "Заявка на вывод" })).not.toBeVisible();
    await expect(page.getByText("На рассмотрении")).toBeVisible();
    await expect(page.getByText("320 ₽")).toBeVisible();
    await expect(page.getByText("Комментарий: основная карта для выплат")).toBeVisible();
  });

  test("paginates the referral feed, supports filters, and keeps content inside the viewport", async ({
    page,
  }) => {
    await mockAuthenticatedMobileSession(page, { initialUnreadCount: 0 });

    const feedItems = Array.from({ length: 25 }, (_, index) => {
      const itemNumber = index + 1;
      const isActive = index < 13;

      return {
        referred_account_id: `ref-${itemNumber}`,
        display_name: `very-long-referral-user-${itemNumber}@example-super-long-domain.test`,
        created_at: `2026-03-${String(25 - index).padStart(2, "0")}T09:00:00Z`,
        reward_amount: isActive ? 100 + itemNumber : 0,
        status: (isActive ? "active" : "pending") as "active" | "pending",
      };
    });

    await page.route("**/api/v1/referrals/summary", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...buildReferralSummaryResponse(340),
          referrals_count: feedItems.length,
        }),
      });
    });

    await page.route("**/api/v1/referrals/feed?**", async (route) => {
      const url = new URL(route.request().url());
      const limit = Number(url.searchParams.get("limit") ?? "20");
      const offset = Number(url.searchParams.get("offset") ?? "0");
      const status = (url.searchParams.get("status") ?? "all") as "all" | "active" | "pending";

      const filteredItems = feedItems.filter((item) => {
        if (status === "active") {
          return item.status === "active";
        }
        if (status === "pending") {
          return item.status === "pending";
        }
        return true;
      });

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          buildReferralFeedResponse(
            filteredItems.slice(offset, offset + limit),
            {
              total: filteredItems.length,
              limit,
              offset,
              status,
            },
          ),
        ),
      });
    });

    await page.goto("/");
    await page.getByRole("button", { name: "Рефералы" }).click();

    await expect(page.getByRole("heading", { name: "Реферальная программа" })).toBeVisible();
    await expect(page.getByTestId("referral-feed-item")).toHaveCount(20);
    await expect(page.getByText("Показаны 20 из 25")).toBeVisible();

    const hasHorizontalOverflow = await page.evaluate(() => {
      const root = document.documentElement;
      const body = document.body;
      return root.scrollWidth > root.clientWidth + 1 || body.scrollWidth > body.clientWidth + 1;
    });
    expect(hasHorizontalOverflow).toBeFalsy();

    await page.getByTestId("referral-feed-load-more").click();
    await expect(page.getByTestId("referral-feed-item")).toHaveCount(25);

    await page.getByRole("button", { name: "С покупкой" }).click();
    await expect(page.getByTestId("referral-feed-item")).toHaveCount(13);
    await expect(page.getByText("Показаны 13 из 13")).toBeVisible();

    await page.getByRole("button", { name: "Ожидают" }).click();
    await expect(page.getByTestId("referral-feed-item")).toHaveCount(12);
    await expect(page.getByText("Показаны 12 из 12")).toBeVisible();
  });

  test("starts Telegram account linking from settings and opens the external link", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, "__openedUrls", {
        value: [] as string[],
        writable: true,
      });

      window.open = ((url?: string | URL | undefined) => {
        (window as unknown as { __openedUrls: string[] }).__openedUrls.push(String(url ?? ""));
        return null;
      }) as typeof window.open;
    });

    await mockAuthenticatedMobileSession(page, { initialUnreadCount: 0 });

    await page.route("**/api/v1/accounts/link-telegram", async (route) => {
      expect(route.request().method()).toBe("POST");

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          link_url: "https://t.me/remnastore_test_bot?start=link-account-123",
        }),
      });
    });

    await page.goto("/");
    await page.getByRole("button", { name: "Настройки" }).click();

    await expect(page.getByRole("heading", { name: "Настройки" })).toBeVisible();
    await expect(page.getByText("Привязать Telegram")).toBeVisible();

    await page.getByRole("button", { name: "Связать" }).click();

    await expect(page.getByText("Ссылка для привязки Telegram открыта")).toBeVisible();

    const openedUrls = await page.evaluate(
      () => (window as unknown as { __openedUrls: string[] }).__openedUrls,
    );
    expect(openedUrls).toContain("https://t.me/remnastore_test_bot?start=link-account-123");
  });

  test("completes browser account linking callback and refreshes settings state", async ({
    page,
  }) => {
    let linkedTelegramId: number | null = null;

    await mockAuthenticatedMobileSession(page, {
      initialUnreadCount: 0,
      getBootstrapPayload: () => ({
        ...bootstrapPayload,
        account: {
          ...bootstrapPayload.account,
          telegram_id: linkedTelegramId,
        },
      }),
    });

    await page.route("**/api/v1/accounts/link-browser-complete", async (route) => {
      expect(route.request().method()).toBe("POST");
      const payload = route.request().postDataJSON() as { link_token: string };
      expect(payload.link_token).toBe("browser-link-token-123");

      linkedTelegramId = 100500;

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ linked: true }),
      });
    });

    await page.goto("/?link_flow=browser&link_token=browser-link-token-123");

    await expect(page.getByText("Браузерный вход успешно привязан")).toBeVisible();
    await expect(page).toHaveURL("http://127.0.0.1:4175/");

    await page.getByRole("button", { name: "Настройки" }).click();

    await expect(page.getByRole("heading", { name: "Настройки" })).toBeVisible();
    await expect(page.getByText("Telegram аккаунт")).toBeVisible();
    await expect(page.getByText("Привязать Telegram")).toHaveCount(0);
  });

  test("prefetches browser account linking in Telegram and opens the cached external link", async ({
    page,
  }) => {
    let linkBrowserRequests = 0;

    await page.addInitScript(() => {
      Object.defineProperty(window, "__telegramOpenedLinks", {
        value: [] as string[],
        writable: true,
      });

      window.Telegram = {
        WebApp: {
          initData: "tg-init-data",
          initDataUnsafe: {
            user: {
              id: 100500,
              photo_url: "https://example.com/telegram-user.png",
            },
          },
          platform: "ios",
          colorScheme: "light",
          expand: () => {},
          openLink: (url: string) => {
            (window as unknown as { __telegramOpenedLinks: string[] }).__telegramOpenedLinks.push(
              url,
            );
          },
        },
      };
    });

    await mockAuthenticatedMobileSession(page, {
      initialUnreadCount: 0,
      withStoredToken: false,
      getBootstrapPayload: () => ({
        ...bootstrapPayload,
        account: {
          ...bootstrapPayload.account,
          email: null,
          telegram_id: 100500,
          display_name: "Alice Telegram",
        },
      }),
    });

    await page.route("**/api/v1/auth/telegram/webapp", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "telegram-session-token",
          account: {
            id: "telegram-account-1",
            email: null,
            display_name: "Alice Telegram",
            username: "alice_tg",
            telegram_id: 100500,
            balance: 1250,
            referral_code: "ALICE123",
            referral_earnings: 340,
            referrals_count: 2,
            referred_by_account_id: null,
            has_used_trial: false,
            subscription_status: "ACTIVE",
            subscription_url: "https://example.com/subscription/alice",
            subscription_expires_at: "2026-04-20T09:00:00Z",
            subscription_last_synced_at: "2026-03-20T09:00:00Z",
            subscription_is_trial: false,
            trial_used_at: null,
            trial_ends_at: null,
          },
          referral_result: null,
        }),
      });
    });

    await page.route("**/api/v1/accounts/link-browser", async (route) => {
      linkBrowserRequests += 1;

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          link_url: "http://127.0.0.1:4175/?link_flow=browser&link_token=prefetched-link-123",
        }),
      });
    });

    await page.goto("/");
    await page.waitForFunction((storageKey) => {
      return window.localStorage.getItem(storageKey) !== null;
    }, telegramAuthStorageKey);

    await expect
      .poll(() => linkBrowserRequests, {
        message: "browser linking URL should be prefetched before the user presses the button",
      })
      .toBe(1);

    await page.getByRole("button", { name: "Настройки" }).click();
    await expect(page.getByRole("heading", { name: "Настройки" })).toBeVisible();
    await expect(page.getByText("Привязать браузерный вход")).toBeVisible();

    await page.getByRole("button", { name: "Связать" }).click();

    const openedLinks = await page.evaluate(
      () => (window as unknown as { __telegramOpenedLinks: string[] }).__telegramOpenedLinks,
    );
    expect(openedLinks).toContain(
      "http://127.0.0.1:4175/?link_flow=browser&link_token=prefetched-link-123",
    );
    expect(linkBrowserRequests).toBe(1);
  });

  test("completes cross-surface account linking from Telegram Mini App to browser callback", async ({
    page,
    context,
  }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, "__telegramOpenedLinks", {
        value: [] as string[],
        writable: true,
      });

      window.Telegram = {
        WebApp: {
          initData: "tg-init-data",
          initDataUnsafe: {
            user: {
              id: 100500,
              photo_url: "https://example.com/telegram-user.png",
            },
          },
          platform: "ios",
          colorScheme: "light",
          expand: () => {},
          openLink: (url: string) => {
            (window as unknown as { __telegramOpenedLinks: string[] }).__telegramOpenedLinks.push(
              url,
            );
          },
        },
      };
    });

    await mockAuthenticatedMobileSession(page, {
      initialUnreadCount: 0,
      withStoredToken: false,
      getBootstrapPayload: () => ({
        ...bootstrapPayload,
        account: {
          ...bootstrapPayload.account,
          email: null,
          telegram_id: 100500,
          display_name: "Alice Telegram",
        },
      }),
    });

    await page.route("**/api/v1/auth/telegram/webapp", async (route) => {
      expect(route.request().method()).toBe("POST");

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "telegram-session-token",
          account: {
            id: "telegram-account-1",
            email: null,
            display_name: "Alice Telegram",
            username: "alice_tg",
            telegram_id: 100500,
            balance: 1250,
            referral_code: "ALICE123",
            referral_earnings: 340,
            referrals_count: 2,
            referred_by_account_id: null,
            has_used_trial: false,
            subscription_status: "ACTIVE",
            subscription_url: "https://example.com/subscription/alice",
            subscription_expires_at: "2026-04-20T09:00:00Z",
            subscription_last_synced_at: "2026-03-20T09:00:00Z",
            subscription_is_trial: false,
            trial_used_at: null,
            trial_ends_at: null,
          },
          referral_result: null,
        }),
      });
    });

    await page.route("**/api/v1/accounts/link-browser", async (route) => {
      expect(route.request().method()).toBe("POST");

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          link_url: "http://127.0.0.1:4175/?link_flow=browser&link_token=cross-surface-link-123",
        }),
      });
    });

    await page.goto("/");
    await page.waitForFunction((storageKey) => {
      return window.localStorage.getItem(storageKey) !== null;
    }, telegramAuthStorageKey);
    await page.getByRole("button", { name: "Настройки" }).click();

    await expect(page.getByRole("heading", { name: "Настройки" })).toBeVisible();
    await expect(page.getByText("Привязать браузерный вход")).toBeVisible();

    await page.getByRole("button", { name: "Связать" }).click();

    const openedLinks = await page.evaluate(
      () => (window as unknown as { __telegramOpenedLinks: string[] }).__telegramOpenedLinks,
    );
    expect(openedLinks).toContain(
      "http://127.0.0.1:4175/?link_flow=browser&link_token=cross-surface-link-123",
    );

    let linkedTelegramId: number | null = null;
    const browserPage = await context.newPage();

    await mockAuthenticatedMobileSession(browserPage, {
      initialUnreadCount: 0,
      getBootstrapPayload: () => ({
        ...bootstrapPayload,
        account: {
          ...bootstrapPayload.account,
          telegram_id: linkedTelegramId,
        },
      }),
    });

    await browserPage.route("**/api/v1/accounts/link-browser-complete", async (route) => {
      expect(route.request().method()).toBe("POST");
      const payload = route.request().postDataJSON() as { link_token: string };
      expect(payload.link_token).toBe("cross-surface-link-123");

      linkedTelegramId = 100500;

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ linked: true }),
      });
    });

    await browserPage.goto(openedLinks[0]);

    await expect(browserPage.getByText("Браузерный вход успешно привязан")).toBeVisible();
    await browserPage.getByRole("button", { name: "Настройки" }).click();
    await expect(browserPage.getByText("Telegram аккаунт")).toBeVisible();
    await expect(browserPage.getByText("Привязать Telegram")).toHaveCount(0);
  });
});
