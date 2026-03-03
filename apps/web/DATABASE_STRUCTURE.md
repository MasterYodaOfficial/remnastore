# Структура базы данных (KV Store)

Приложение использует Key-Value хранилище Supabase для хранения всех данных.

## Ключи и их структура

### 1. Пользователи

**Ключ:** `user:{userId}`

**Структура:**
```typescript
{
  id: string;              // ID пользователя из Supabase Auth
  name: string;            // Имя пользователя
  email: string;           // Email
  telegramId?: number;     // ID Telegram (если вход через Telegram)
  balance: number;         // Баланс в рублях
  referralCode: string;    // Реферальный код (REF + первые 8 символов userId)
  referralsCount: number;  // Количество приглашенных рефералов
  earnings: number;        // Заработок с реферальной программы
  hasUsedTrial: boolean;   // Использован ли пробный период
}
```

**Пример:**
```javascript
await kv.get('user:550e8400-e29b-41d4-a716-446655440000');
// Returns: { id: '550e...', name: 'Иван', balance: 1000, ... }
```

---

### 2. Подписки

**Ключ:** `subscription:{userId}`

**Структура:**
```typescript
{
  userId: string;       // ID пользователя
  isActive: boolean;    // Активна ли подписка
  startDate: string;    // Дата начала (ISO string)
  endDate: string;      // Дата окончания (ISO string)
  planId?: string;      // ID тарифного плана (если не пробный)
  isTrial: boolean;     // Пробная ли подписка
}
```

**Пример:**
```javascript
await kv.get('subscription:550e8400-e29b-41d4-a716-446655440000');
// Returns: { userId: '550e...', isActive: true, endDate: '2026-04-03T...', ... }
```

---

### 3. Тарифные планы

**Ключ:** `plan:{planId}`

**Структура:**
```typescript
{
  id: string;           // Уникальный ID плана (например: 'plan:1month')
  name: string;         // Название плана
  price: number;        // Цена в рублях
  duration: number;     // Длительность в днях
  features: string[];   // Список возможностей
  popular?: boolean;    // Популярный ли план
}
```

**Пример:**
```javascript
await kv.get('plan:1month');
// Returns: { id: 'plan:1month', name: '1 месяц', price: 299, duration: 30, ... }
```

**Получение всех планов:**
```javascript
const plans = await kv.getByPrefix('plan:');
// Returns: [{ id: 'plan:1month', ... }, { id: 'plan:3months', ... }, ...]
```

---

### 4. Рефералы

**Ключ:** `referral:{referrerId}:{referralId}`

**Структура:**
```typescript
{
  id: string;              // Уникальный ID реферала
  referrerId: string;      // ID пригласившего
  referralId: string;      // ID приглашенного
  name: string;            // Имя приглашенного
  date: string;            // Дата регистрации (ISO string)
  earned: number;          // Заработано с этого реферала
  status: 'active' | 'pending';  // Статус реферала
}
```

**Пример:**
```javascript
await kv.getByPrefix('referral:550e8400-e29b-41d4-a716-446655440000:');
// Returns: [{ id: '...', name: 'Петр', earned: 59.8, status: 'active' }, ...]
```

---

## Операции с базой данных

### Получение одного значения
```javascript
const user = await kv.get('user:123');
```

### Сохранение значения
```javascript
await kv.set('user:123', { id: '123', name: 'Test', balance: 0 });
```

### Получение всех значений с префиксом
```javascript
const plans = await kv.getByPrefix('plan:');
```

### Получение нескольких значений
```javascript
const values = await kv.mget(['user:123', 'subscription:123']);
```

### Сохранение нескольких значений
```javascript
await kv.mset([
  ['user:123', userData],
  ['subscription:123', subscriptionData],
]);
```

### Удаление значения
```javascript
await kv.del('subscription:123');
```

---

## Примечания

1. **Автоматическая инициализация:** При первом запуске сервер автоматически создаст дефолтные тарифные планы, если они отсутствуют.

2. **Реферальный код:** Генерируется автоматически при создании пользователя как `REF + первые 8 символов userId в верхнем регистре`.

3. **Баланс и заработок:** Храним отдельно баланс пользователя и его заработок с реферальной программы. При выводе средств earnings переносится в balance.

4. **Подписки:** Каждый пользователь может иметь только одну активную подписку. При покупке новой подписки старая перезаписывается.

5. **Пробный период:** Каждый пользователь может активировать пробный период только один раз (проверка через `hasUsedTrial`).

---

## Расширение структуры

Для добавления новых сущностей следуйте паттерну:
- Используйте префиксы для группировки данных
- Храните связи через составные ключи (например, `referral:{userId}:{referralId}`)
- Используйте `getByPrefix` для получения всех связанных записей
