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
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }

  return (await response.json()) as T;
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

export default function App() {
  const [token, setToken] = useState<string>(() => localStorage.getItem(TOKEN_KEY) || "");
  const [profile, setProfile] = useState<AdminProfile | null>(null);
  const [summary, setSummary] = useState<AdminDashboardSummary | null>(null);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState<boolean>(Boolean(token));
  const [error, setError] = useState<string | null>(null);

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

  useEffect(() => {
    if (!token) {
      setLoading(false);
      setProfile(null);
      setSummary(null);
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
        const detail = await response.text();
        throw new Error(detail || "Не удалось войти");
      }

      const body = (await response.json()) as AdminAuthResponse;
      localStorage.setItem(TOKEN_KEY, body.access_token);
      setToken(body.access_token);
      setProfile(body.admin);
      setPassword("");
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
    setError(null);
  }

  async function handleRefresh() {
    if (!token) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await loadDashboard(token);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : "Не удалось обновить данные");
    } finally {
      setLoading(false);
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
              Текущий контур уже держит bootstrap admin, auth и сводку. Дальше сюда встанут поиск
              пользователей, выводы и ручные действия над балансом и подписками.
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

      {error ? <div className="form-error form-error--banner">{error}</div> : null}

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
          <li>Поиск пользователя по `telegram_id`, email и username</li>
          <li>Карточка пользователя с ledger, платежами и подпиской</li>
          <li>Очередь выводов и admin processing</li>
          <li>Ручные корректировки баланса и ручная выдача подписки</li>
        </ul>
      </section>
    </main>
  );
}
