import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type AdminProfile = {
  id: string;
  username: string;
  email: string | null;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  last_login_at: string | null;
  created_at: string;
};

type AdminDashboardSummary = {
  total_accounts: number;
  active_subscriptions: number;
  pending_withdrawals: number;
  pending_payments: number;
};

type AdminAuthResponse = {
  access_token: string;
  token_type: string;
  admin: AdminProfile;
};

type DashboardCardProps = {
  label: string;
  value: number;
  hint: string;
};

type AdminAccountSearchItem = {
  id: string;
  email: string | null;
  display_name: string | null;
  telegram_id: number | null;
  username: string | null;
  status: "active" | "blocked";
  balance: number;
  subscription_status: string | null;
  subscription_expires_at: string | null;
  created_at: string;
};

type AdminAccountSearchResponse = {
  items: AdminAccountSearchItem[];
};

type AdminAccountAuthIdentity = {
  provider: string;
  provider_uid: string;
  email: string | null;
  display_name: string | null;
  linked_at: string;
};

type AdminAccountLedgerEntry = {
  id: number;
  entry_type: string;
  amount: number;
  currency: string;
  balance_before: number;
  balance_after: number;
  reference_type: string | null;
  reference_id: string | null;
  comment: string | null;
  created_at: string;
};

type AdminAccountPayment = {
  id: number;
  provider: string;
  flow_type: string;
  status: string;
  amount: number;
  currency: string;
  plan_code: string | null;
  description: string | null;
  created_at: string;
  finalized_at: string | null;
};

type AdminAccountWithdrawal = {
  id: number;
  amount: number;
  destination_type: string;
  destination_value: string;
  status: string;
  user_comment: string | null;
  admin_comment: string | null;
  created_at: string;
  processed_at: string | null;
};

type AdminAccountDetail = {
  id: string;
  email: string | null;
  display_name: string | null;
  telegram_id: number | null;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  locale: string | null;
  status: "active" | "blocked";
  balance: number;
  referral_code: string | null;
  referral_earnings: number;
  referrals_count: number;
  referred_by_account_id: string | null;
  remnawave_user_uuid: string | null;
  subscription_url: string | null;
  subscription_status: string | null;
  subscription_expires_at: string | null;
  subscription_last_synced_at: string | null;
  subscription_is_trial: boolean;
  trial_used_at: string | null;
  trial_ends_at: string | null;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
  auth_accounts: AdminAccountAuthIdentity[];
  recent_ledger_entries: AdminAccountLedgerEntry[];
  recent_payments: AdminAccountPayment[];
  recent_withdrawals: AdminAccountWithdrawal[];
  ledger_entries_count: number;
  payments_count: number;
  pending_payments_count: number;
  withdrawals_count: number;
  pending_withdrawals_count: number;
};

type AdminBalanceAdjustmentResponse = {
  account_id: string;
  balance: number;
  ledger_entry: AdminAccountLedgerEntry;
};

type AdminSubscriptionPlan = {
  code: string;
  name: string;
  price_rub: number;
  price_stars: number | null;
  duration_days: number;
  features: string[];
  popular: boolean;
};

type AdminSubscriptionGrantResponse = {
  account_id: string;
  plan_code: string;
  subscription_grant_id: number;
  audit_log_id: number;
  subscription_status: string | null;
  subscription_expires_at: string | null;
  subscription_url: string | null;
};

type AdminView = "dashboard" | "accounts";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") || "http://localhost:8000";
const TOKEN_KEY = "remnastore_admin_token";

function formatDate(value: string | null): string {
  if (!value) {
    return "Не было";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Некорректная дата";
  }

  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatMoney(value: number, currency = "RUB"): string {
  return new Intl.NumberFormat("ru-RU", {
    maximumFractionDigits: 0,
  }).format(value) + ` ${currency}`;
}

async function readErrorMessage(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) {
    return `HTTP ${response.status}`;
  }

  try {
    const parsed = JSON.parse(text) as { detail?: string };
    return parsed.detail || text;
  } catch {
    return text;
  }
}

async function adminFetch<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers || {}),
    },
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  return (await response.json()) as T;
}

function humanizeAccountStatus(status: string): string {
  return status === "blocked" ? "Заблокирован" : "Активен";
}

function humanizePaymentStatus(status: string): string {
  switch (status) {
    case "created":
      return "Создан";
    case "pending":
      return "Ожидает";
    case "requires_action":
      return "Ждет действия";
    case "succeeded":
      return "Успешен";
    case "failed":
      return "Ошибка";
    case "cancelled":
      return "Отменен";
    case "expired":
      return "Истек";
    default:
      return status;
  }
}

function humanizePaymentFlow(flow: string): string {
  return flow === "wallet_topup" ? "Пополнение" : "Покупка тарифа";
}

function humanizeLedgerType(entryType: string): string {
  switch (entryType) {
    case "topup_payment":
      return "Пополнение по платежу";
    case "subscription_debit":
      return "Оплата подписки";
    case "referral_reward":
      return "Реферальное начисление";
    case "withdrawal_reserve":
      return "Резерв на вывод";
    case "withdrawal_release":
      return "Возврат резерва";
    case "withdrawal_payout":
      return "Выплата вывода";
    case "admin_credit":
      return "Зачисление админом";
    case "admin_debit":
      return "Списание админом";
    default:
      return entryType;
  }
}

function humanizeWithdrawalStatus(status: string): string {
  switch (status) {
    case "new":
      return "Новый";
    case "in_progress":
      return "В работе";
    case "paid":
      return "Выплачен";
    case "rejected":
      return "Отклонен";
    case "cancelled":
      return "Отменен";
    default:
      return status;
  }
}

function DashboardCard({ label, value, hint }: DashboardCardProps) {
  return (
    <article className="metric-card">
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      <span className="metric-hint">{hint}</span>
    </article>
  );
}

function DetailFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default function App() {
  const [token, setToken] = useState<string>(() => localStorage.getItem(TOKEN_KEY) || "");
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [summary, setSummary] = useState<AdminDashboardSummary | null>(null);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState<boolean>(Boolean(token));
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<AdminView>("dashboard");
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<AdminAccountSearchItem[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [selectedAccount, setSelectedAccount] = useState<AdminAccountDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [subscriptionPlans, setSubscriptionPlans] = useState<AdminSubscriptionPlan[]>([]);
  const [plansLoading, setPlansLoading] = useState(false);
  const [balanceAdjustmentAmount, setBalanceAdjustmentAmount] = useState("");
  const [balanceAdjustmentComment, setBalanceAdjustmentComment] = useState("");
  const [balanceSubmitting, setBalanceSubmitting] = useState(false);
  const [subscriptionGrantPlanCode, setSubscriptionGrantPlanCode] = useState("");
  const [subscriptionGrantComment, setSubscriptionGrantComment] = useState("");
  const [subscriptionSubmitting, setSubscriptionSubmitting] = useState(false);

  const cards = useMemo(() => {
    if (!summary) {
      return [];
    }
    return [
      {
        label: "Пользователи",
        value: summary.total_accounts,
        hint: "всего локальных аккаунтов",
      },
      {
        label: "Активные подписки",
        value: summary.active_subscriptions,
        hint: "текущий рабочий пул",
      },
      {
        label: "Выводы",
        value: summary.pending_withdrawals,
        hint: "очередь к обработке",
      },
      {
        label: "Платежи",
        value: summary.pending_payments,
        hint: "незавершенные попытки",
      },
    ];
  }, [summary]);

  const selectedGrantPlan = useMemo(
    () => subscriptionPlans.find((plan) => plan.code === subscriptionGrantPlanCode) || null,
    [subscriptionGrantPlanCode, subscriptionPlans],
  );

  const loadDashboard = useCallback(
    async (activeToken: string) => {
      const [admin, dashboard] = await Promise.all([
        adminFetch<AdminProfile>("/api/v1/admin/auth/me", activeToken),
        adminFetch<AdminDashboardSummary>("/api/v1/admin/dashboard/summary", activeToken),
      ]);
      setProfile(admin);
      setSummary(dashboard);
    },
    [],
  );

  const loadAccountDetail = useCallback(
    async (accountId: string, activeToken: string): Promise<AdminAccountDetail | null> => {
      setDetailLoading(true);
      try {
        const detail = await adminFetch<AdminAccountDetail>(`/api/v1/admin/accounts/${accountId}`, activeToken);
        setSelectedAccount(detail);
        setSelectedAccountId(accountId);
        return detail;
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить карточку пользователя");
        setSelectedAccount(null);
        return null;
      } finally {
        setDetailLoading(false);
      }
    },
    [],
  );

  const loadSubscriptionPlans = useCallback(
    async (activeToken: string): Promise<AdminSubscriptionPlan[]> => {
      setPlansLoading(true);
      try {
        const plans = await adminFetch<AdminSubscriptionPlan[]>(
          "/api/v1/admin/accounts/subscription-plans",
          activeToken,
        );
        setSubscriptionPlans(plans);
        return plans;
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить тарифы");
        return [];
      } finally {
        setPlansLoading(false);
      }
    },
    [],
  );

  function updateSearchResultSnapshot(account: Pick<AdminAccountDetail, "id" | "balance" | "status" | "subscription_status" | "subscription_expires_at">) {
    setSearchResults((items) =>
      items.map((item) =>
        item.id === account.id
          ? {
              ...item,
              balance: account.balance,
              status: account.status,
              subscription_status: account.subscription_status,
              subscription_expires_at: account.subscription_expires_at,
            }
          : item,
      ),
    );
  }

  useEffect(() => {
    if (!token) {
      setLoading(false);
      setProfile(null);
      setSummary(null);
      setSubscriptionPlans([]);
      setSearchResults([]);
      setSelectedAccount(null);
      setNotice(null);
      return;
    }

    let cancelled = false;

    async function bootstrap() {
      try {
        setLoading(true);
        setError(null);
        await loadDashboard(token);
      } catch (fetchError) {
        if (cancelled) {
          return;
        }
        localStorage.removeItem(TOKEN_KEY);
        setToken("");
        setProfile(null);
        setSummary(null);
        setSearchResults([]);
        setSelectedAccount(null);
        setNotice(null);
        setError(fetchError instanceof Error ? fetchError.message : "Не удалось загрузить админку");
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, [loadDashboard, token]);

  useEffect(() => {
    if (!token || activeView !== "accounts" || subscriptionPlans.length > 0) {
      return;
    }

    void loadSubscriptionPlans(token);
  }, [activeView, loadSubscriptionPlans, subscriptionPlans.length, token]);

  useEffect(() => {
    if (subscriptionGrantPlanCode || subscriptionPlans.length === 0) {
      return;
    }

    const defaultPlan = subscriptionPlans.find((plan) => plan.popular) || subscriptionPlans[0];
    if (defaultPlan) {
      setSubscriptionGrantPlanCode(defaultPlan.code);
    }
  }, [subscriptionGrantPlanCode, subscriptionPlans]);

  useEffect(() => {
    setBalanceAdjustmentAmount("");
    setBalanceAdjustmentComment("");
    setSubscriptionGrantComment("");
  }, [selectedAccountId]);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          login,
          password,
        }),
      });

      if (!response.ok) {
        throw new Error(await readErrorMessage(response));
      }

      const body = (await response.json()) as AdminAuthResponse;
      localStorage.setItem(TOKEN_KEY, body.access_token);
      setToken(body.access_token);
      setProfile(body.admin);
      setPassword("");
      setNotice(null);
      await loadDashboard(body.access_token);
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Не удалось войти");
    } finally {
      setSubmitting(false);
    }
  }

  function handleLogout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken("");
    setProfile(null);
    setSummary(null);
    setSubscriptionPlans([]);
    setSearchResults([]);
    setSelectedAccount(null);
    setError(null);
    setNotice(null);
    setActiveView("dashboard");
  }

  async function handleRefresh() {
    if (!token) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await loadDashboard(token);
      if (activeView === "accounts" && subscriptionPlans.length === 0) {
        await loadSubscriptionPlans(token);
      }
      if (selectedAccountId) {
        await loadAccountDetail(selectedAccountId, token);
      }
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Не удалось обновить данные");
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !searchQuery.trim()) {
      return;
    }

    setSearching(true);
    setError(null);
    setNotice(null);
    setSelectedAccount(null);
    try {
      const response = await adminFetch<AdminAccountSearchResponse>(
        `/api/v1/admin/accounts/search?query=${encodeURIComponent(searchQuery.trim())}`,
        token,
      );
      setSearchResults(response.items);
      if (response.items[0]) {
        await loadAccountDetail(response.items[0].id, token);
      } else {
        setSelectedAccountId(null);
      }
    } catch (searchError) {
      setSearchResults([]);
      setSelectedAccountId(null);
      setError(searchError instanceof Error ? searchError.message : "Не удалось выполнить поиск");
    } finally {
      setSearching(false);
    }
  }

  async function handleSelectAccount(accountId: string) {
    if (!token) {
      return;
    }
    setError(null);
    setNotice(null);
    await loadAccountDetail(accountId, token);
  }

  async function handleBalanceAdjustment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!token || !selectedAccount) {
      return;
    }

    const parsedAmount = Number.parseInt(balanceAdjustmentAmount, 10);
    const trimmedComment = balanceAdjustmentComment.trim();

    if (!Number.isInteger(parsedAmount) || parsedAmount === 0) {
      setError("Сумма должна быть целым числом и не равняться нулю");
      return;
    }

    if (!trimmedComment) {
      setError("Комментарий обязателен");
      return;
    }

    setBalanceSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const idempotencyKey =
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : `admin-adjust-${Date.now()}`;

      const response = await adminFetch<AdminBalanceAdjustmentResponse>(
        `/api/v1/admin/accounts/${selectedAccount.id}/balance-adjustments`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            amount: parsedAmount,
            comment: trimmedComment,
            idempotency_key: idempotencyKey,
          }),
        },
      );

      const refreshedAccount = await loadAccountDetail(selectedAccount.id, token);
      if (refreshedAccount) {
        updateSearchResultSnapshot(refreshedAccount);
      } else {
        setSearchResults((items) =>
          items.map((item) =>
            item.id === response.account_id
              ? {
                  ...item,
                  balance: response.balance,
                }
              : item,
          ),
        );
      }

      await loadDashboard(token);
      setBalanceAdjustmentAmount("");
      setBalanceAdjustmentComment("");
      setNotice(
        `Корректировка проведена: ${
          response.ledger_entry.amount > 0 ? "зачислено" : "списано"
        } ${formatMoney(Math.abs(response.ledger_entry.amount), response.ledger_entry.currency)}.`,
      );
    } catch (adjustmentError) {
      setError(
        adjustmentError instanceof Error
          ? adjustmentError.message
          : "Не удалось провести корректировку баланса",
      );
    } finally {
      setBalanceSubmitting(false);
    }
  }

  async function handleSubscriptionGrant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!token || !selectedAccount) {
      return;
    }

    const trimmedComment = subscriptionGrantComment.trim();
    if (!subscriptionGrantPlanCode) {
      setError("Выбери тариф для выдачи");
      return;
    }

    if (!trimmedComment) {
      setError("Комментарий обязателен");
      return;
    }

    setSubscriptionSubmitting(true);
    setError(null);
    setNotice(null);

    try {
      const idempotencyKey =
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : `admin-grant-${Date.now()}`;

      const response = await adminFetch<AdminSubscriptionGrantResponse>(
        `/api/v1/admin/accounts/${selectedAccount.id}/subscription-grants`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            plan_code: subscriptionGrantPlanCode,
            comment: trimmedComment,
            idempotency_key: idempotencyKey,
          }),
        },
      );

      const refreshedAccount = await loadAccountDetail(selectedAccount.id, token);
      if (refreshedAccount) {
        updateSearchResultSnapshot(refreshedAccount);
      } else {
        setSearchResults((items) =>
          items.map((item) =>
            item.id === response.account_id
              ? {
                  ...item,
                  subscription_status: response.subscription_status,
                  subscription_expires_at: response.subscription_expires_at,
                }
              : item,
          ),
        );
      }

      await loadDashboard(token);
      setSubscriptionGrantComment("");
      setNotice(
        `Подписка выдана: ${selectedGrantPlan?.name || response.plan_code} до ${formatDate(
          response.subscription_expires_at,
        )}.`,
      );
    } catch (grantError) {
      setError(
        grantError instanceof Error ? grantError.message : "Не удалось выдать подписку",
      );
    } finally {
      setSubscriptionSubmitting(false);
    }
  }

  if (!token) {
    return (
      <main className="admin-shell admin-shell--auth">
        <section className="auth-panel">
          <div className="auth-copy">
            <span className="eyebrow">Remnastore Admin Command</span>
            <h1>Тихий зал управления</h1>
            <p>
              Отдельный операционный контур с темным интерфейсом, зелеными акцентами и быстрым
              доступом к ключевым действиям. Для первого входа задай
              `ADMIN_BOOTSTRAP_USERNAME` и `ADMIN_BOOTSTRAP_PASSWORD` в `.env`.
            </p>
            <div className="scene-panel">
              <div className="sage-portrait" aria-hidden="true">
                <span className="sage-aura" />
                <span className="sage-head" />
                <span className="sage-ears sage-ears--left" />
                <span className="sage-ears sage-ears--right" />
                <span className="sage-robe" />
                <span className="energy-blade" />
                <span className="energy-hilt" />
              </div>
              <div className="scene-copy">
                <span className="scene-label">Боевой пост</span>
                <strong>Темный мостик. Зеленый контур. Один источник истины.</strong>
                <p>
                  Без декоративного мусора: только вход, операционные сигналы и быстрый переход к
                  следующим админским модулям.
                </p>
              </div>
            </div>
          </div>
          <form className="auth-form" onSubmit={handleLogin}>
            <label>
              <span>Логин или email</span>
              <input
                autoComplete="username"
                value={login}
                onChange={(event) => setLogin(event.target.value)}
                placeholder="root или root@example.com"
                required
              />
            </label>
            <label>
              <span>Пароль</span>
              <input
                autoComplete="current-password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Введите пароль"
                required
              />
            </label>
            {error ? <div className="form-error">{error}</div> : null}
            <button type="submit" disabled={submitting}>
              {submitting ? "Входим..." : "Войти"}
            </button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="admin-shell">
      <section className="dashboard-hero">
        <div className="hero-copy">
          <span className="eyebrow">Фаза 7 · command deck</span>
          <h1>Операционный мостик админки</h1>
          <p>
            Текущий контур уже держит bootstrap admin, auth, сводку, поиск пользователей и ручные
            действия над балансом и подписками. Следом сюда встают выводы, блокировки и
            расширенная история.
          </p>
        </div>
        <div className="hero-side">
          <div className="hero-blade" aria-hidden="true">
            <span className="hero-blade__beam" />
            <span className="hero-blade__hilt" />
          </div>
          <div className="hero-actions">
            <button className="ghost-button" type="button" onClick={handleRefresh} disabled={loading}>
              {loading ? "Обновляем..." : "Обновить"}
            </button>
            <button className="ghost-button" type="button" onClick={handleLogout}>
              Выйти
            </button>
          </div>
        </div>
      </section>

      <nav className="module-nav" aria-label="Модули админки">
        <button
          type="button"
          className={activeView === "dashboard" ? "module-nav__button module-nav__button--active" : "module-nav__button"}
          onClick={() => setActiveView("dashboard")}
        >
          Сводка
        </button>
        <button
          type="button"
          className={activeView === "accounts" ? "module-nav__button module-nav__button--active" : "module-nav__button"}
          onClick={() => setActiveView("accounts")}
        >
          Пользователи
        </button>
      </nav>

      {error ? <div className="form-error form-error--banner">{error}</div> : null}
      {notice ? <div className="form-success form-success--banner">{notice}</div> : null}

      {activeView === "dashboard" ? (
        <>
          <section className="dashboard-grid">
            <article className="profile-card">
              <span className="eyebrow">Профиль оператора</span>
              <h2>{profile?.full_name || profile?.username || "Администратор"}</h2>
              <dl className="profile-list">
                <div>
                  <dt>Логин</dt>
                  <dd>{profile?.username}</dd>
                </div>
                <div>
                  <dt>Email</dt>
                  <dd>{profile?.email || "Не задан"}</dd>
                </div>
                <div>
                  <dt>Роль</dt>
                  <dd>{profile?.is_superuser ? "Суперадмин" : "Оператор"}</dd>
                </div>
                <div>
                  <dt>Последний вход</dt>
                  <dd>{formatDate(profile?.last_login_at || null)}</dd>
                </div>
              </dl>
            </article>

            <section className="metrics-grid">
              {cards.map((card) => (
                <DashboardCard key={card.label} {...card} />
              ))}
            </section>
          </section>

          <section className="roadmap-card">
            <span className="eyebrow">Следующий сектор</span>
            <ul>
              <li>Полная история ledger с пагинацией и фильтрами</li>
              <li>Очередь выводов и admin processing</li>
              <li>Блокировка пользователя и запрет новых операций</li>
              <li>Audit trail и расширенная статистика</li>
            </ul>
          </section>
        </>
      ) : (
        <section className="search-shell">
          <aside className="search-column">
            <form className="search-panel" onSubmit={handleSearch}>
              <span className="eyebrow">Поиск пользователя</span>
              <h2>telegram_id, email или username</h2>
              <div className="search-bar">
                <input
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                  placeholder="Например: 777000111 или user@example.com"
                  required
                />
                <button type="submit" disabled={searching}>
                  {searching ? "Ищем..." : "Найти"}
                </button>
              </div>
            </form>

            <div className="results-list">
              {searchResults.length === 0 ? (
                <div className="empty-state">Список пуст. Сначала выполни поиск.</div>
              ) : (
                searchResults.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={selectedAccountId === item.id ? "result-card result-card--active" : "result-card"}
                    onClick={() => void handleSelectAccount(item.id)}
                  >
                    <div className="result-card__top">
                      <strong>{item.display_name || item.username || item.email || item.id}</strong>
                      <span className={`status-pill status-pill--${item.status}`}>{humanizeAccountStatus(item.status)}</span>
                    </div>
                    <span>{item.email || item.username || "Без email и username"}</span>
                    <span>Баланс: {formatMoney(item.balance)}</span>
                    <span>Telegram: {item.telegram_id ? item.telegram_id : "не привязан"}</span>
                  </button>
                ))
              )}
            </div>
          </aside>

          <div className="detail-column">
            {detailLoading ? <div className="detail-skeleton">Загружаем карточку пользователя...</div> : null}
            {!detailLoading && !selectedAccount ? (
              <div className="detail-skeleton">Выбери пользователя из результата поиска.</div>
            ) : null}
            {!detailLoading && selectedAccount ? (
              <>
                <section className="detail-header">
                  <div>
                    <span className="eyebrow">Карточка пользователя</span>
                    <h2>{selectedAccount.display_name || selectedAccount.username || selectedAccount.email || selectedAccount.id}</h2>
                    <p>
                      {selectedAccount.email || "Без email"} · {selectedAccount.telegram_id ? `Telegram ${selectedAccount.telegram_id}` : "Telegram не привязан"}
                    </p>
                  </div>
                  <span className={`status-pill status-pill--${selectedAccount.status}`}>
                    {humanizeAccountStatus(selectedAccount.status)}
                  </span>
                </section>

                <section className="detail-facts-grid">
                  <DetailFact label="Баланс" value={formatMoney(selectedAccount.balance)} />
                  <DetailFact label="Реферальный доход" value={formatMoney(selectedAccount.referral_earnings)} />
                  <DetailFact label="Подписка" value={selectedAccount.subscription_status || "нет"} />
                  <DetailFact label="Создан" value={formatDate(selectedAccount.created_at)} />
                </section>

                <section className="detail-section detail-section--action">
                  <span className="eyebrow">Ручная корректировка баланса</span>
                  <div className="detail-section__intro">
                    <h3>Зачисление или списание без захода в БД</h3>
                    <p>
                      Положительная сумма делает `admin_credit`, отрицательная делает `admin_debit`.
                      Комментарий обязателен и попадет в ledger.
                    </p>
                  </div>
                  <form className="adjustment-form" onSubmit={handleBalanceAdjustment}>
                    <label className="form-field">
                      <span>Сумма, RUB</span>
                      <input
                        type="number"
                        step="1"
                        value={balanceAdjustmentAmount}
                        onChange={(event) => setBalanceAdjustmentAmount(event.target.value)}
                        placeholder="Например: 500 или -300"
                        required
                      />
                    </label>
                    <label className="form-field form-field--wide">
                      <span>Комментарий</span>
                      <textarea
                        value={balanceAdjustmentComment}
                        onChange={(event) => setBalanceAdjustmentComment(event.target.value)}
                        placeholder="Почему меняем баланс и на каком основании"
                        rows={3}
                        required
                      />
                    </label>
                    <div className="adjustment-form__footer">
                      <span className="form-hint">
                        `+500` зачислит средства, `-300` спишет. Повторный клик не должен заменять
                        комментарий вроде "поправить баланс".
                      </span>
                      <button className="action-button" type="submit" disabled={balanceSubmitting}>
                        {balanceSubmitting ? "Проводим..." : "Провести корректировку"}
                      </button>
                    </div>
                  </form>
                </section>

                <section className="detail-section detail-section--action">
                  <span className="eyebrow">Ручная выдача подписки</span>
                  <div className="detail-section__intro">
                    <h3>Продление доступа без платежного flow</h3>
                    <p>
                      Выбор тарифа идет из backend-каталога. Комментарий обязателен, а операция
                      фиксируется в audit trail как admin action.
                    </p>
                  </div>
                  <form className="adjustment-form" onSubmit={handleSubscriptionGrant}>
                    <label className="form-field">
                      <span>Тариф</span>
                      <select
                        value={subscriptionGrantPlanCode}
                        onChange={(event) => setSubscriptionGrantPlanCode(event.target.value)}
                        disabled={plansLoading || subscriptionPlans.length === 0}
                        required
                      >
                        {subscriptionPlans.length === 0 ? (
                          <option value="">
                            {plansLoading ? "Загружаем тарифы..." : "Тарифы недоступны"}
                          </option>
                        ) : null}
                        {subscriptionPlans.map((plan) => (
                          <option key={plan.code} value={plan.code}>
                            {plan.name} · {plan.duration_days} дн. · {formatMoney(plan.price_rub)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="form-field form-field--wide">
                      <span>Комментарий</span>
                      <textarea
                        value={subscriptionGrantComment}
                        onChange={(event) => setSubscriptionGrantComment(event.target.value)}
                        placeholder="Почему выдаем подписку вручную и что это компенсирует"
                        rows={3}
                        required
                      />
                    </label>
                    <div className="adjustment-form__footer">
                      <span className="form-hint">
                        {selectedGrantPlan
                          ? `Будет выдан тариф ${selectedGrantPlan.name} на ${selectedGrantPlan.duration_days} дней. Повторный клик защищен idempotency key.`
                          : "Сначала загрузим тарифы из backend-каталога."}
                      </span>
                      <button
                        className="action-button"
                        type="submit"
                        disabled={
                          plansLoading || subscriptionPlans.length === 0 || subscriptionSubmitting
                        }
                      >
                        {subscriptionSubmitting ? "Выдаем..." : "Выдать подписку"}
                      </button>
                    </div>
                  </form>
                </section>

                <section className="detail-sections-grid">
                  <article className="detail-section">
                    <span className="eyebrow">Идентичность</span>
                    <div className="detail-kv">
                      <div><span>Username</span><strong>{selectedAccount.username || "-"}</strong></div>
                      <div><span>Имя</span><strong>{[selectedAccount.first_name, selectedAccount.last_name].filter(Boolean).join(" ") || "-"}</strong></div>
                      <div><span>Locale</span><strong>{selectedAccount.locale || "-"}</strong></div>
                      <div><span>Referral code</span><strong>{selectedAccount.referral_code || "-"}</strong></div>
                      <div><span>Referrals</span><strong>{selectedAccount.referrals_count}</strong></div>
                      <div><span>Last seen</span><strong>{formatDate(selectedAccount.last_seen_at)}</strong></div>
                    </div>
                  </article>

                  <article className="detail-section">
                    <span className="eyebrow">Подписка</span>
                    <div className="detail-kv">
                      <div><span>Статус</span><strong>{selectedAccount.subscription_status || "нет"}</strong></div>
                      <div><span>Истекает</span><strong>{formatDate(selectedAccount.subscription_expires_at)}</strong></div>
                      <div><span>Trial</span><strong>{selectedAccount.subscription_is_trial ? "Да" : "Нет"}</strong></div>
                      <div><span>Trial used</span><strong>{formatDate(selectedAccount.trial_used_at)}</strong></div>
                      <div><span>Sync</span><strong>{formatDate(selectedAccount.subscription_last_synced_at)}</strong></div>
                      <div><span>Remnawave UUID</span><strong>{selectedAccount.remnawave_user_uuid || "-"}</strong></div>
                    </div>
                    {selectedAccount.subscription_url ? (
                      <a className="detail-link" href={selectedAccount.subscription_url} target="_blank" rel="noreferrer">
                        Открыть subscription URL
                      </a>
                    ) : null}
                  </article>
                </section>

                <section className="detail-facts-grid detail-facts-grid--compact">
                  <DetailFact label="Ledger entries" value={String(selectedAccount.ledger_entries_count)} />
                  <DetailFact label="Payments" value={String(selectedAccount.payments_count)} />
                  <DetailFact label="Pending payments" value={String(selectedAccount.pending_payments_count)} />
                  <DetailFact label="Withdrawals" value={String(selectedAccount.withdrawals_count)} />
                </section>

                <section className="detail-section">
                  <span className="eyebrow">Auth identities</span>
                  <div className="activity-list">
                    {selectedAccount.auth_accounts.length === 0 ? (
                      <div className="activity-empty">Привязанных identity нет.</div>
                    ) : (
                      selectedAccount.auth_accounts.map((identity) => (
                        <article key={`${identity.provider}:${identity.provider_uid}`} className="activity-item">
                          <div>
                            <strong>{identity.provider}</strong>
                            <span>{identity.email || identity.display_name || identity.provider_uid}</span>
                          </div>
                          <span>{formatDate(identity.linked_at)}</span>
                        </article>
                      ))
                    )}
                  </div>
                </section>

                <section className="activity-grid">
                  <article className="detail-section">
                    <span className="eyebrow">Последний ledger</span>
                    <div className="activity-list">
                      {selectedAccount.recent_ledger_entries.length === 0 ? (
                        <div className="activity-empty">Записей пока нет.</div>
                      ) : (
                        selectedAccount.recent_ledger_entries.map((entry) => (
                          <article key={entry.id} className="activity-item activity-item--dense">
                            <div>
                              <strong>{humanizeLedgerType(entry.entry_type)}</strong>
                              <span>{entry.comment || `${entry.reference_type || "entry"} ${entry.reference_id || ""}`.trim()}</span>
                            </div>
                            <div className="activity-item__meta">
                              <strong>{formatMoney(entry.amount, entry.currency)}</strong>
                              <span>После: {formatMoney(entry.balance_after, entry.currency)}</span>
                            </div>
                          </article>
                        ))
                      )}
                    </div>
                  </article>

                  <article className="detail-section">
                    <span className="eyebrow">Последние платежи</span>
                    <div className="activity-list">
                      {selectedAccount.recent_payments.length === 0 ? (
                        <div className="activity-empty">Платежей пока нет.</div>
                      ) : (
                        selectedAccount.recent_payments.map((payment) => (
                          <article key={payment.id} className="activity-item activity-item--dense">
                            <div>
                              <strong>{humanizePaymentFlow(payment.flow_type)}</strong>
                              <span>{payment.description || payment.plan_code || payment.provider}</span>
                            </div>
                            <div className="activity-item__meta">
                              <strong>{formatMoney(payment.amount, payment.currency)}</strong>
                              <span>{humanizePaymentStatus(payment.status)}</span>
                            </div>
                          </article>
                        ))
                      )}
                    </div>
                  </article>
                </section>

                <section className="detail-section">
                  <span className="eyebrow">Последние выводы</span>
                  <div className="activity-list">
                    {selectedAccount.recent_withdrawals.length === 0 ? (
                      <div className="activity-empty">Выводов пока нет.</div>
                    ) : (
                      selectedAccount.recent_withdrawals.map((withdrawal) => (
                        <article key={withdrawal.id} className="activity-item activity-item--dense">
                          <div>
                            <strong>{formatMoney(withdrawal.amount)}</strong>
                            <span>{withdrawal.destination_type}: {withdrawal.destination_value}</span>
                          </div>
                          <div className="activity-item__meta">
                            <strong>{humanizeWithdrawalStatus(withdrawal.status)}</strong>
                            <span>{formatDate(withdrawal.created_at)}</span>
                          </div>
                        </article>
                      ))
                    )}
                  </div>
                </section>
              </>
            ) : null}
          </div>
        </section>
      )}
    </main>
  );
}
