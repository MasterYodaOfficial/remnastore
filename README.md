# remnastore

Коммерческий скелет проекта для продажи VPN.

**Состав:**
- `apps/api` — backend на FastAPI (бизнес‑логика, биллинг, интеграции)
- `apps/bot` — Telegram‑бот на aiogram (продажи, поддержка, связь с API)
- `apps/web` — Telegram WebApp на React (витрина, покупка, управление подпиской)
- `packages/shared` — общие схемы и типы между ботом и API
- `ops` — инфраструктура и деплой (docker, конфиги)
- `docs` — документация и решения

**Ключевая идея:** бизнес‑логика и интеграции живут в API, бот и WebApp — тонкие клиенты.

## Быстрый обзор
- `apps/api/app/main.py` — точка входа API
- `apps/bot/bot/main.py` — точка входа бота
- `apps/web/src/app/App.tsx` — точка входа WebApp

## Переменные окружения
См. `.env.example`.

## UV и Docker
- Перед сборкой контейнеров нужен `uv.lock`.
- Создать локально: `UV_CACHE_DIR=.uv-cache uv lock`.
