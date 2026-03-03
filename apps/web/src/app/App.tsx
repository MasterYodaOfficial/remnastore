import WebApp from "@twa-dev/sdk";
import { useEffect, useMemo, useState } from "react";

const BOT_URL =
  import.meta.env.VITE_TELEGRAM_BOT_URL || "https://t.me/your_bot_username";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

type Tab = "profile" | "plans" | "settings";
type Theme = "dark" | "light";

export function App() {
  const [hasInitData, setHasInitData] = useState(false);
  const [profile, setProfile] = useState<WebApp.User | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("profile");
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    WebApp.ready();
    const initData = WebApp.initDataUnsafe;
    const user = initData?.user;
    const hasUser = Boolean(user);
    setHasInitData(hasUser);

    if (hasUser) {
      setProfile(user as WebApp.User);
      void fetch(`${API_BASE_URL}/api/v1/accounts/telegram`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          telegram_id: user.id,
          username: user.username,
          first_name: user.first_name,
          last_name: user.last_name,
          is_premium: Boolean(user.is_premium),
          locale: user.language_code,
          last_login_source: "telegram_webapp",
        }),
      }).catch(() => {
        // fail silently; UI не блокируем
      });
    }
  }, []);

  const authButtons = useMemo(
    () => [
      { label: "Войти через Google", href: BOT_URL },
      { label: "Войти через Яндекс", href: BOT_URL },
      { label: "Войти через ВКонтакте", href: BOT_URL },
    ],
    []
  );

  const renderTab = () => {
    if (!hasInitData) {
      return (
        <section className="card">
          <h2>Вход</h2>
          <p>Зайдите через Telegram или привяжите аккаунт.</p>
          <div className="actions">
            {authButtons.map((btn) => (
              <a key={btn.label} className="ghost" href={btn.href}>
                {btn.label}
              </a>
            ))}
          </div>
          <p className="note">
            Нет Telegram рядом? Авторизуйтесь и нажмите “Открыть в Telegram” позже —
            учётка сохранится.
          </p>
        </section>
      );
    }

    switch (activeTab) {
      case "profile":
        return (
          <>
            <section className="card hero-card">
              <div className="hero-top">
                <div>
                  <div className="brand">Remnastore</div>
                  <div className="subtitle">VPN подписки</div>
                </div>
                <button
                  className="ghost small"
                  onClick={() => setTheme((prev) => (prev === "dark" ? "light" : "dark"))}
                >
                  {theme === "dark" ? "Светлая" : "Тёмная"}
                </button>
              </div>
              <div className="profile-row">
                <div className="avatar">
                  {profile?.photo_url ? (
                    <img src={profile.photo_url} alt="avatar" />
                  ) : (
                    <span>{(profile?.first_name || "U").slice(0, 1)}</span>
                  )}
                </div>
                <div className="profile-meta">
                  <div className="profile-name">
                    {[profile?.first_name, profile?.last_name].filter(Boolean).join(" ") ||
                      profile?.username ||
                      "Профиль"}
                  </div>
                  <div className="profile-sub">
                    {profile?.username ? "@" + profile.username : "Telegram WebApp"}
                  </div>
                </div>
              </div>
            </section>

            <section className="card balance-card">
              <div className="balance-row">
                <div>
                  <div className="label">Баланс</div>
                  <div className="amount">0 ₽</div>
                  <div className="muted">Пополните, чтобы купить подписку</div>
                </div>
                <button className="primary ghost-contrast">Пополнить</button>
              </div>
            </section>

            <section className="card">
              <h2>Подписка</h2>
              <div className="placeholder">
                Здесь будут данные активной подписки, срок действия и кнопка продления.
              </div>
            </section>
          </>
        );
      case "plans":
        return (
          <section className="card">
            <h2>Тарифы</h2>
            <div className="placeholder">
              Здесь будет список тарифов, цены и кнопка оплаты.
            </div>
          </section>
        );
      case "settings":
        return (
          <section className="card">
            <h2>Настройки</h2>
            <div className="placeholder">
              Здесь будут уведомления, привязки и выбор языка.
            </div>
          </section>
        );
      default:
        return null;
    }
  };

  return (
    <div className={`page theme-${theme}`}>
      <header className="header">
        <div className="brand">Remnastore</div>
        <div className="subtitle">VPN подписки</div>
        <div className="actions-inline">
          <button
            className="ghost small"
            onClick={() => setTheme((prev) => (prev === "dark" ? "light" : "dark"))}
          >
            {theme === "dark" ? "Светлая тема" : "Тёмная тема"}
          </button>
        </div>
      </header>
      <main className="content">{renderTab()}</main>

      <nav className="bottom-nav">
        <button
          className={`nav-btn ${activeTab === "profile" ? "active" : ""}`}
          onClick={() => setActiveTab("profile")}
        >
          Профиль
        </button>
        <button
          className={`nav-btn ${activeTab === "plans" ? "active" : ""}`}
          onClick={() => setActiveTab("plans")}
        >
          Тарифы
        </button>
        <button
          className={`nav-btn ${activeTab === "settings" ? "active" : ""}`}
          onClick={() => setActiveTab("settings")}
        >
          Настройки
        </button>
      </nav>
    </div>
  );
}
