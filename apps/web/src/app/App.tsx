import WebApp from "@twa-dev/sdk";
import { useEffect, useMemo, useState } from "react";

const BOT_URL =
  import.meta.env.VITE_TELEGRAM_BOT_URL || "https://t.me/your_bot_username";

export function App() {
  const [hasInitData, setHasInitData] = useState(false);

  useEffect(() => {
    WebApp.ready();
    const initData = WebApp.initDataUnsafe;
    setHasInitData(Boolean(initData?.user));
  }, []);

  const authButtons = useMemo(
    () => [
      { label: "Войти через Google", href: BOT_URL },
      { label: "Войти через Яндекс", href: BOT_URL },
      { label: "Войти через ВКонтакте", href: BOT_URL },
    ],
    []
  );

  return (
    <div className="page">
      <header className="header">
        <div className="brand">Remnastore</div>
        <div className="subtitle">VPN подписки</div>
      </header>
      <main className="content">
        {hasInitData ? (
          <section className="card">
            <h2>Готовы начать</h2>
            <p>Вы авторизованы через Telegram WebApp. Можно продолжить покупку.</p>
            <button className="primary">Купить подписку</button>
          </section>
        ) : (
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
        )}
      </main>
    </div>
  );
}
