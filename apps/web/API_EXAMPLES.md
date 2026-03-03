# Примеры использования API

Все эндпоинты сервера имеют префикс `/make-server-0ad4a249`.

## Авторизация

### Регистрация пользователя

```javascript
const response = await fetch(`${API_BASE}/signup`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${publicAnonKey}`,
  },
  body: JSON.stringify({
    email: 'user@example.com',
    password: 'securePassword123',
    name: 'Имя Пользователя',
    telegramId: null, // или ID из Telegram
  }),
});

const data = await response.json();
// { success: true, user: { ... } }
```

### Получение профиля

```javascript
const response = await fetch(`${API_BASE}/profile`, {
  headers: {
    'Authorization': `Bearer ${accessToken}`,
  },
});

const data = await response.json();
// { user: { id, name, email, balance, referralCode, ... } }
```

## Баланс

### Пополнение баланса

```javascript
const response = await fetch(`${API_BASE}/balance/add`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${accessToken}`,
  },
  body: JSON.stringify({
    amount: 1000, // сумма в рублях
  }),
});

const data = await response.json();
// { success: true, balance: 1000 }
```

## Подписки

### Получение информации о подписке

```javascript
const response = await fetch(`${API_BASE}/subscription`, {
  headers: {
    'Authorization': `Bearer ${accessToken}`,
  },
});

const data = await response.json();
// { subscription: { isActive, startDate, endDate, isTrial } }
```

### Активация пробного периода

```javascript
const response = await fetch(`${API_BASE}/subscription/trial`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
  },
});

const data = await response.json();
// { success: true }
```

## Тарифные планы

### Получение списка тарифов

```javascript
const response = await fetch(`${API_BASE}/plans`, {
  headers: {
    'Authorization': `Bearer ${publicAnonKey}`,
  },
});

const data = await response.json();
// { plans: [{ id, name, price, duration, features, popular }, ...] }
```

### Покупка тарифного плана

```javascript
const response = await fetch(`${API_BASE}/plans/buy`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${accessToken}`,
  },
  body: JSON.stringify({
    planId: 'plan:1month',
  }),
});

const data = await response.json();
// { success: true, balance: 700 } // новый баланс после покупки
```

## Рефералы

### Получение списка рефералов

```javascript
const response = await fetch(`${API_BASE}/referrals`, {
  headers: {
    'Authorization': `Bearer ${accessToken}`,
  },
});

const data = await response.json();
// { referrals: [...] }
```

### Вывод реферальных средств

```javascript
const response = await fetch(`${API_BASE}/referrals/withdraw`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
  },
});

const data = await response.json();
// { success: true, withdrawn: 500, balance: 1500 }
```

## Обработка ошибок

Все эндпоинты возвращают ошибки в формате:

```javascript
{
  "error": "Описание ошибки"
}
```

Пример обработки:

```javascript
try {
  const response = await fetch(`${API_BASE}/plans/buy`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ planId: 'plan:1month' }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error);
  }

  const data = await response.json();
  console.log('Успешно:', data);
} catch (err) {
  console.error('Ошибка:', err.message);
}
```

## Статус-коды

- `200` - Успешный запрос
- `400` - Неверные данные запроса
- `401` - Не авторизован
- `404` - Не найдено
- `500` - Внутренняя ошибка сервера
