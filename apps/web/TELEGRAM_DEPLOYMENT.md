# Развертывание в Telegram WebApp

Пошаговая инструкция по подключению приложения к Telegram боту.

## Шаг 1: Создание бота

1. Откройте [@BotFather](https://t.me/botfather) в Telegram
2. Отправьте команду `/newbot`
3. Введите имя для вашего бота (например: "VPN Service Bot")
4. Введите username (например: "vpn_service_bot")
5. Сохраните полученный токен бота

## Шаг 2: Создание Web App

1. В чате с BotFather отправьте `/newapp`
2. Выберите вашего бота из списка
3. Введите название приложения (например: "VPN Service")
4. Введите описание (например: "Управление VPN подписками")
5. Загрузите иконку (512x512 пикселей, PNG/JPG)
6. Загрузите GIF-анимацию (опционально)
7. **Важно:** Введите URL вашего приложения:
   - Для продакшена: `https://your-domain.com`
   - Для разработки: используйте ngrok или похожий сервис
8. Выберите Short name (например: "vpnservice")
9. Подтвердите создание

## Шаг 3: Настройка бота

### Создание кнопки для запуска Web App

1. В BotFather отправьте `/mybots`
2. Выберите вашего бота
3. Выберите "Edit Bot" → "Edit Commands"
4. Добавьте команду:
   ```
   start - Открыть VPN сервис
   ```

### Альтернатива: Меню с кнопкой

Создайте файл с командами бота (необязательно):

```
start - Открыть VPN сервис
help - Помощь
support - Связаться с поддержкой
```

## Шаг 4: Добавление кнопки Web App в бота

Вы можете добавить кнопку WebApp несколькими способами:

### Вариант 1: Inline кнопка

Создайте простой скрипт бота (используя библиотеку для Telegram Bot API):

```javascript
// Пример на Node.js с библиотекой node-telegram-bot-api
const TelegramBot = require('node-telegram-bot-api');

const token = 'YOUR_BOT_TOKEN';
const webAppUrl = 'https://your-domain.com';

const bot = new TelegramBot(token, { polling: true });

bot.onText(/\/start/, (msg) => {
  const chatId = msg.chat.id;
  
  bot.sendMessage(chatId, 'Добро пожаловать в VPN Service! 🚀', {
    reply_markup: {
      inline_keyboard: [[
        {
          text: '🔐 Открыть VPN сервис',
          web_app: { url: webAppUrl }
        }
      ]]
    }
  });
});
```

### Вариант 2: Кнопка в клавиатуре

```javascript
bot.onText(/\/start/, (msg) => {
  const chatId = msg.chat.id;
  
  bot.sendMessage(chatId, 'Управляйте VPN подписками:', {
    reply_markup: {
      keyboard: [[
        {
          text: '🔐 VPN Сервис',
          web_app: { url: webAppUrl }
        }
      ]],
      resize_keyboard: true
    }
  });
});
```

### Вариант 3: Кнопка меню

1. В BotFather отправьте `/mybots`
2. Выберите бота → "Bot Settings" → "Menu Button"
3. Введите текст: "VPN Сервис"
4. Введите URL вашего приложения

## Шаг 5: Тестирование

1. Найдите вашего бота в Telegram по username
2. Нажмите "Start"
3. Нажмите на кнопку Web App
4. Приложение должно открыться и автоматически авторизовать вас

## Особенности Telegram WebApp

### Telegram Theme

Приложение автоматически адаптируется под тему Telegram:
- Светлая тема: белый фон
- Темная тема: темный фон

Цвета берутся из переменных Telegram WebApp API:
```javascript
window.Telegram.WebApp.themeParams
```

### Доступные данные пользователя

При запуске из Telegram доступны:
```javascript
const tg = window.Telegram.WebApp;
const user = tg.initDataUnsafe.user;
// {
//   id: 123456789,
//   first_name: "Иван",
//   last_name: "Иванов",
//   username: "ivan",
//   language_code: "ru"
// }
```

### Функции WebApp

```javascript
const tg = window.Telegram.WebApp;

// Расширить приложение на весь экран
tg.expand();

// Показать кнопку "Назад"
tg.BackButton.show();
tg.BackButton.onClick(() => {
  // Обработка нажатия
});

// Показать главную кнопку
tg.MainButton.setText('Купить подписку');
tg.MainButton.show();
tg.MainButton.onClick(() => {
  // Обработка нажатия
});

// Закрыть WebApp
tg.close();

// Haptic feedback
tg.HapticFeedback.impactOccurred('medium');
```

## Шаг 6: Продакшен

### Для продакшена рекомендуется:

1. **HTTPS обязателен** - Telegram WebApp работает только через HTTPS
2. **Использовать свой домен** - для профессионального вида
3. **Настроить CSP заголовки** - для безопасности
4. **Минимизировать и оптимизировать** - для быстрой загрузки
5. **Настроить мониторинг** - для отслеживания ошибок

### Проверка перед запуском:

- [ ] HTTPS настроен
- [ ] Бот создан и токен сохранен
- [ ] Web App создан и URL настроен
- [ ] Кнопка запуска добавлена
- [ ] Приложение тестируется в Telegram
- [ ] OAuth провайдеры настроены (для браузера)
- [ ] Supabase проект настроен

## Поддержка и отладка

### Как проверить логи:

1. Откройте приложение в Telegram
2. Подключите телефон к компьютеру
3. Используйте Remote Debugging:
   - iOS: Safari → Develop
   - Android: Chrome → chrome://inspect

### Частые проблемы:

**Проблема:** WebApp не открывается
- **Решение:** Проверьте, что URL указан правильно и доступен по HTTPS

**Проблема:** Авторизация не работает
- **Решение:** Проверьте initData и убедитесь, что скрипт Telegram загружен

**Проблема:** Темная тема не работает
- **Решение:** Проверьте CSS переменные и colorScheme в Telegram

## Полезные ссылки

- [Telegram WebApp Documentation](https://core.telegram.org/bots/webapps)
- [BotFather](https://t.me/botfather)
- [Telegram Bot API](https://core.telegram.org/bots/api)
