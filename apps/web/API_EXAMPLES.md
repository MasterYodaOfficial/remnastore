# Примеры запросов к текущему API

Документ показывает базовые примеры для нового backend-контура.

Важно:
- примеры ниже относятся к `FastAPI` backend из `apps/api`
- бизнес-операции должны идти через `API`, а не через старые `Supabase Edge Functions`
- фактический набор платежных и referral endpoints будет расширяться по мере реализации roadmap

## Получение текущего аккаунта

```javascript
const response = await fetch(`${API_BASE}/api/v1/accounts/me`, {
  headers: {
    Authorization: `Bearer ${accessToken}`,
  },
});

const data = await response.json();
```

## Логин из Telegram Mini App

```javascript
const response = await fetch(`${API_BASE}/api/v1/auth/telegram/webapp`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    init_data: window.Telegram.WebApp.initData,
  }),
});

const data = await response.json();
// { access_token, account }
```

## Старт связки Browser -> Telegram

```javascript
const response = await fetch(`${API_BASE}/api/v1/accounts/link-telegram`, {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${accessToken}`,
  },
});

const data = await response.json();
// { bot_url }
```

## Старт связки Telegram -> Browser

```javascript
const response = await fetch(`${API_BASE}/api/v1/accounts/link-browser`, {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${accessToken}`,
  },
});

const data = await response.json();
// { browser_url, link_token }
```

## Завершение связки Telegram -> Browser после OAuth login

```javascript
const response = await fetch(`${API_BASE}/api/v1/accounts/link-browser-complete`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${accessToken}`,
  },
  body: JSON.stringify({
    link_token,
  }),
});

const data = await response.json();
```

## Общий формат ошибок

```javascript
{
  detail: 'Описание ошибки'
}
```

## Примечание

Примеры по платежам, реферальным начислениям, ledger и выводам будут дополняться вместе с реализацией соответствующих backend-модулей.
