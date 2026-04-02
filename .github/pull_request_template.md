## Что изменено

- Что именно изменилось?
- Зачем это было нужно?

## Проверки

- [ ] `./scripts/test.sh all`
- [ ] `uv run --group dev ruff check apps/api apps/bot common scripts`
- [ ] `uv run --group dev ruff format --check apps/api apps/bot common scripts`
- [ ] `npm run lint` в `apps/web`
- [ ] `npm run test` в `apps/web`
- [ ] `npm run test:e2e` в `apps/web`, если менялся auth/UI/browser flow
- [ ] `npm run typecheck` в `apps/web`
- [ ] `npm run build` в `apps/web`
- [ ] `npm run lint` в `apps/admin`
- [ ] `npm run test` в `apps/admin`
- [ ] `npm run test:e2e` в `apps/admin`, если менялся auth/UI/browser flow
- [ ] `npm run typecheck` в `apps/admin`
- [ ] `npm run build` в `apps/admin`

## Влияние

- [ ] Есть миграции БД
- [ ] Есть новые или измененные env-переменные
- [ ] Изменился API или frontend-контракт
- [ ] Документация обновлена

## Интерфейс

- [ ] Изменений в UI нет
- [ ] Скриншоты приложены
- [ ] Ручной smoke пройден

## Релиз

- [ ] Это не релизный PR `dev -> main`
- [ ] Для `dev -> main` подготовлена заметка к релизу
- [ ] Для `dev -> main` зафиксирован планируемый тег `v0.x.y`
