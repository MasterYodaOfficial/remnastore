# API

`apps/api` — backend проекта на `FastAPI`.

Отвечает за:

- аккаунты и авторизацию
- баланс, рефералов и выводы
- платежи и webhook
- подписки и интеграцию с `Remnawave`
- bootstrap для `web` и `admin`

Основной docker-сервис: `api`  
Health endpoint: `GET /api/v1/health`
