# Release Checklist

Этот чеклист фиксирует минимальный ritual для выпуска `dev -> main`.

Связанные документы:

- [`docs/release-process.md`](./release-process.md)
- [`docs/releases/TEMPLATE.md`](./releases/TEMPLATE.md)
- [`docs/smoke-checklist.md`](./smoke-checklist.md)
- [`docs/rollback-checklist.md`](./rollback-checklist.md)

## Перед PR `dev -> main`

- [ ] Все нужные изменения уже в `dev`, новых обязательных патчей поверх релиз-кандидата не осталось
- [ ] Пройден локальный baseline:
  - [ ] `./scripts/test.sh all`
  - [ ] `uv run --group dev ruff check apps/api apps/bot common scripts`
  - [ ] `uv run --group dev ruff format --check apps/api apps/bot common scripts`
  - [ ] `npm run lint` в `apps/web`
  - [ ] `npm run test` в `apps/web`
  - [ ] `npm run test:e2e` в `apps/web`
  - [ ] `npm run typecheck` в `apps/web`
  - [ ] `npm run build` в `apps/web`
  - [ ] `npm run lint` в `apps/admin`
  - [ ] `npm run test` в `apps/admin`
  - [ ] `npm run test:e2e` в `apps/admin`
  - [ ] `npm run typecheck` в `apps/admin`
  - [ ] `npm run build` в `apps/admin`
- [ ] PR template заполнен полностью
- [ ] Изменения в `.env.example`, [`docs/production-env.md`](./production-env.md) и других контрактных docs синхронизированы
- [ ] Миграции просмотрены отдельно: понятен порядок применения и риск rollback
- [ ] Подготовлен короткий release note по [`docs/releases/TEMPLATE.md`](./releases/TEMPLATE.md)
- [ ] Для релиза выбран плановый tag формата `v0.x.y`

## Перед merge в `main`

- [ ] CI на PR зелёный, включая `Playwright` browser smoke внутри `web-quality` и `admin-quality`
- [ ] Выполнен [`docs/smoke-checklist.md`](./smoke-checklist.md) на актуальном release candidate
- [ ] Проверены security-sensitive изменения через [`docs/security-checklist.md`](./security-checklist.md), если они затрагивались
- [ ] Подтвержден plan B через [`docs/rollback-checklist.md`](./rollback-checklist.md)
- [ ] Release note и planned tag упомянуты прямо в PR `dev -> main`

## После merge в `main`

- [ ] Создан git tag формата `v0.x.y`
- [ ] Финальный release note сохранен в `docs/releases/v0.x.y.md`
- [ ] Если используется GitHub Release UI, описание релиза синхронизировано с `docs/releases/v0.x.y.md`
- [ ] После выкладки просмотрены логи `api`, `bot`, `worker`, `notifications-worker`
- [ ] Проверены платежи, webhook и уведомления на отсутствие новых ошибок
- [ ] Отмечены follow-up задачи, которые не блокируют релиз, но должны быть доведены отдельно
