# Release Checklist

Этот чеклист фиксирует минимальный ritual для выпуска `dev -> main`.

## Перед PR `dev -> main`

- [ ] Все нужные изменения уже в `dev`, новых обязательных патчей поверх релиз-кандидата не осталось
- [ ] Пройден локальный baseline:
  - [ ] `./scripts/test.sh all`
  - [ ] `uv run --group dev ruff check apps/api apps/bot common scripts`
  - [ ] `npm run lint` в `apps/web`
  - [ ] `npm run test` в `apps/web`
  - [ ] `npm run typecheck` в `apps/web`
  - [ ] `npm run build` в `apps/web`
  - [ ] `npm run lint` в `apps/admin`
  - [ ] `npm run test` в `apps/admin`
  - [ ] `npm run typecheck` в `apps/admin`
  - [ ] `npm run build` в `apps/admin`
- [ ] PR template заполнен полностью
- [ ] Изменения в `.env.example`, [`docs/production-env.md`](./production-env.md) и других контрактных docs синхронизированы
- [ ] Миграции просмотрены отдельно: понятен порядок применения и риск rollback
- [ ] Подготовлен короткий release note: что изменилось, что может пойти не так, как проверяли

## Перед merge в `main`

- [ ] CI на PR зелёный
- [ ] Выполнен [`docs/smoke-checklist.md`](./smoke-checklist.md) на актуальном release candidate
- [ ] Проверены security-sensitive изменения через [`docs/security-checklist.md`](./security-checklist.md), если они затрагивались
- [ ] Подтвержден plan B через [`docs/rollback-checklist.md`](./rollback-checklist.md)

## После merge в `main`

- [ ] Создан git tag формата `v0.x.y`
- [ ] Release note сохранен рядом с tag/release
- [ ] После выкладки просмотрены логи `api`, `bot`, `worker`, `notifications-worker`
- [ ] Проверены платежи, webhook и уведомления на отсутствие новых ошибок
- [ ] Отмечены follow-up задачи, которые не блокируют релиз, но должны быть доведены отдельно
