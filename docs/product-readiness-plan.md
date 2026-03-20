# План приведения проекта к product-ready состоянию

## Назначение

Этот документ дополняет [`docs/launch-roadmap.md`](launch-roadmap.md).

`launch-roadmap` отвечает за функциональный scope запуска, а этот план фиксирует путь от текущего `dev`-состояния к ветке `main`, пригодной для коммерческой эксплуатации:

- единые пользовательские тексты и локализация
- cleanup и декомпозиция кода
- кодовая документация и актуальные runbook-документы
- тестовое и статическое quality gate покрытие
- обязательные проверки в GitHub Actions
- понятный release-процесс `dev -> main`

## Зафиксированные решения на сейчас

- Для `v1` делаем централизованный только `ru`. Полноценную мультиязычность откладываем на этап после коммерческого запуска.
- Для `web` и `bot` цель первого этапа локализации: убрать хардкод пользовательских строк из кода и собрать их в единый каталог текстов.
- `admin` на первом релизе остается только на `ru` без обязательного полноценного i18n-слоя.
- Для `admin` допустимы захардкоженные русские тексты, но они должны оставаться осмысленными, единообразными и без сырых технических деталей для оператора.

## Переходный режим до жестких quality gate

Пока проект активно меняется, важнее не потерять прогресс и не сломать себе темп разработки.

Поэтому на текущем этапе действуют такие правила:

- локальные коммиты не должны блокироваться линтерами, тестами, pre-commit hook-ами или другими обязательными локальными проверками
- коммитить и пушить в `feature/*` или `dev` можно в любой момент как в безопасную точку сохранения работы
- первые CI-проверки вводятся как advisory и диагностический контур, а не как запрет на каждое промежуточное сохранение
- строгими обязательными checks делаем только merge в `main`, когда команды и baseline уже стабилизированы
- до стабилизации quality-команд не включаем агрессивные пороги coverage и не делаем искусственный переход на новые инструменты только ради процесса

Практический вывод:

- сначала разрешаем себе часто коммитить и пушить
- потом добавляем воспроизводимые команды качества
- и только после этого начинаем делать часть проверок обязательными для merge

## Статус на 2026-03-20

- Фаза 0: `В работе`
- Фаза 1: `В работе`
- Фаза 2: `В работе`
- Фаза 3: `В работе`
- Фаза 4: `В работе`
- Фаза 5: `В работе`
- Фаза 6: `В работе`

Текущий следующий шаг:

1. Завершить и отдельно проверить branch protection / запрет прямого push в GitHub UI, чтобы Phase 0 можно было считать реально закрытой.
2. Решить, когда и как вводить `ruff format --check`: сейчас он затронет большой пласт активных файлов и не подходит как мгновенный blocking gate.
3. Выбрать следующий repo-local приоритет после runbooks: dependency triage, Playwright/component tests или rollout декомпозиции крупных модулей.

## Что видно по репозиторию сейчас

- В проекте уже есть сильная база по продуктовым и инфраструктурным документам: `README`, `docs/launch-roadmap.md`, `docs/launch-progress.md`, `docs/security-checklist.md`, `docs/production-env.md`, `docs/release-checklist.md`, `docs/smoke-checklist.md`, `docs/rollback-checklist.md`, `docs/runbooks/README.md`, `docs/code-documentation.md`, `docs/architecture.md`, `apps/web/FRONTEND_CONTRACT.md`.
- В репозитории теперь есть процессные repo-артефакты: `.github/workflows/ci.yml` и `.github/pull_request_template.md`.
- Для Python уже есть воспроизводимые локальные команды тестов и покрытия: [`scripts/test.sh`](../scripts/test.sh) и [`scripts/coverage.sh`](../scripts/coverage.sh).
- Проверено 2026-03-20: `scripts/test.sh all` проходит локально (`api`: `164` tests, `bot`: `25` tests).
- `web` и `admin` уже собираются локально через `npm run build`, имеют явные `typecheck`, `test` и `lint` контракты.
- В `pyproject.toml` уже добавлен `ruff`, и `uv run --group dev ruff check apps/api apps/bot common scripts` проходит локально; при этом `prettier`, `playwright`, `mypy`, `pre-commit` по-прежнему не обнаружены.
- `uv run --group dev ruff format --check apps/api apps/bot common scripts` пока не проходит: для этого нужен отдельный rollout форматирования, а не мгновенный blocking gate.
- Локализация уже сдвинулась дальше, чем было на старте плана:
  - `bot` использует `translate()` и общий каталог `packages/locales`
  - `web` активно использует [`apps/web/src/lib/i18n.ts`](../apps/web/src/lib/i18n.ts) в [`apps/web/src/app/App.tsx`](../apps/web/src/app/App.tsx) и продуктовых компонентах
  - [`packages/locales/ru/web.json`](../packages/locales/ru/web.json) уже содержит полноценный каталог пользовательских строк
  - в backend появился каталог [`packages/locales/ru/api.json`](../packages/locales/ru/api.json) для backend-facing ошибок и уведомлений
  - `admin` по-прежнему не имеет собственного i18n-слоя, и для `v1` это допустимо
- В кодовой базе все еще есть крупные монолиты, которые повышают стоимость доработок и риск регрессий:
  - [`apps/admin/src/App.tsx`](../apps/admin/src/App.tsx) `8986` строк
  - [`apps/web/src/app/App.tsx`](../apps/web/src/app/App.tsx) `5125` строк
  - [`apps/bot/bot/services/menu_renderer.py`](../apps/bot/bot/services/menu_renderer.py) `1092` строки
  - [`apps/api/app/services/account_linking.py`](../apps/api/app/services/account_linking.py) `1119` строк
- Общий стандарт кодовой документации уже появился в [`docs/code-documentation.md`](./code-documentation.md), а release/smoke/rollback checklist-артефакты и incident runbook-и теперь оформлены отдельными документами.

## Что считаем готовностью к merge в `main`

Перед выходом в `main` проект должен удовлетворять всем пунктам:

- все пользовательские тексты в `web`, `admin`, `bot` и backend-facing ошибках вынесены в централизованный каталог
- UI не показывает сырые технические детали и не светит внутренние исключения пользователю
- ключевые flows покрыты автоматическими проверками: auth, linking, trial, payments, referrals, withdrawals, admin-критика
- merge в `main` идет только через PR с обязательными зелеными checks
- для `api`, `bot`, `web`, `admin` есть понятные команды `lint`, `typecheck`, `test`, `build`
- крупные монолитные файлы декомпозированы до уровня, при котором их реально безопасно сопровождать
- docs не расходятся с кодом, а релизный и операционный процесс зафиксированы в репозитории
- перед релизом закрыт ручной smoke checklist

Уточнение для `v1`:

- обязательная централизация пользовательских текстов относится к `web`, `bot` и пользовательским backend-facing ошибкам
- `admin` в `v1` не блокируется отсутствием полноценной локализации, но блокируется плохими операторскими текстами и утечкой внутренних ошибок

## Источники истины по документации

Чтобы не плодить дубли, после старта этого плана источники истины должны быть такими:

- [`README.md`](../README.md) — быстрый вход, запуск, карта основных документов
- [`docs/launch-roadmap.md`](./launch-roadmap.md) — продуктовый scope запуска
- [`docs/launch-progress.md`](./launch-progress.md) — фактический трекер реализованных фаз
- [`docs/product-readiness-plan.md`](./product-readiness-plan.md) — hardening-план перед `main`
- [`apps/web/FRONTEND_CONTRACT.md`](../apps/web/FRONTEND_CONTRACT.md) — frontend-контракт
- [`docs/production-env.md`](./production-env.md) — env-контракт
- [`docs/release-checklist.md`](./release-checklist.md) — выпуск `dev -> main`
- [`docs/smoke-checklist.md`](./smoke-checklist.md) — ручной smoke
- [`docs/rollback-checklist.md`](./rollback-checklist.md) — rollback ritual
- [`docs/runbooks/README.md`](./runbooks/README.md) — incident response runbooks
- [`docs/security-checklist.md`](./security-checklist.md) — security baseline

Новые одноразовые summary-файлы не создаем. Изменения статуса вносим в существующие документы.

## Фаза 0. Release governance и правила merge

Статус: `В работе`

Проверено 2026-03-20:

- [x] В репозитории добавлены `.github/workflows/ci.yml` и `.github/pull_request_template.md`, фиксирующие базовый процесс проверки и PR.
- [ ] Branch protection и запрет прямого push живут вне репозитория; ruleset `protect-main` уже активен для `main`, bypass list пустой, required checks (`python-quality`, `web-quality`, `admin-quality`) уже выбраны, dry-run PR `dev -> main` подтвердил блокировку merge при падающем CI, но отдельной ручной проверки прямого push в `main` еще не было.
- [x] В репозитории зафиксированы release, smoke и rollback checklists для `dev -> main`.
- [ ] Формат release note и tagging ritual еще не закреплены как обязательный repo-процесс.

Цель: перестать относиться к `dev` как к единственной рабочей ветке без формализованного выхода в `main`.

Сделать:

- защитить `main` от прямых push
- ввести правило: `main` обновляется только через PR из `dev`
- пока проект ведет один разработчик, использовать обязательный self-review через PR перед merge в `main`
- когда появятся другие разработчики, поднять правило до обязательного review минимум от одного человека
- договориться о схеме релизов: минимум `v0.x.y` с git tag и коротким release note
- зафиксировать Definition of Done для PR: код, тесты, docs, changelog-контекст
- довести `pull_request_template.md` до рабочего ритуала использования при каждом `dev -> main`

Рекомендуемый режим для текущего этапа:

- пока проект развивает один разработчик, отдельная ветка `release/*` не обязательна
- достаточно потока `feature/* -> dev -> main`
- `dev` используется как рабочая ветка накопления и безопасного хранения прогресса
- частые коммиты в `feature/*` и `dev` считаются нормой, а не шумом
- merge в `main` делать только после зелёного CI, ручного smoke и короткого self-review через PR
- когда появятся другие разработчики, параллельные релизы или длинная стабилизация, тогда можно вводить `release/*`

Критерий выхода:

- прямой merge в `main` технически невозможен
- у команды есть единый ритуал релиза и rollback-решение

## Фаза 1. Базовый quality gate

Статус: `В работе`

Проверено 2026-03-20:

- [x] Для Python есть воспроизводимые локальные команды тестов и покрытия через `scripts/test.sh` и `scripts/coverage.sh`.
- [x] `scripts/test.sh all` проходит локально после выравнивания тестов под локализованный backend error contract.
- [x] `web` и `admin` успешно собираются локально через `npm run build`.
- [x] Для `web` добавлены `typescript`, `@types/*`, `tsconfig.json` и `typecheck` script; `npm run typecheck` проходит локально.
- [x] Для `admin` добавлен `typecheck` script, и `npm run typecheck` проходит локально.
- [x] В `pyproject.toml` настроен `ruff`, и `uv run --group dev ruff check apps/api apps/bot common scripts` проходит локально.
- [x] В репозитории добавлен минимальный `ci.yml`, который повторяет текущий локальный baseline для Python, `web` и `admin`.
- [x] Для `web` и `admin` добавлены `lint` контракты на ESLint; `npm run lint` проходит локально в обоих приложениях.
- [x] CI-подобный порядок команд подтвержден локально: `uv sync --frozen --group dev`, `npm ci` в `apps/web` и `apps/admin`, затем `lint`, `test`, `typecheck` и `build`.
- [x] Для `web` и `admin` добавлены минимальные `test` контракты на `Vitest`; `npm run test` проходит локально в обоих приложениях.
- [x] Для `python-quality` в GitHub Actions добавлен явный тестовый `DATABASE_URL`; Python-контур больше не зависит от локального `.env` и проходит в чистой копии репозитория.
- [ ] `ruff format --check` пока не готов к роли blocking gate: форматирование затронет большой пласт уже активных файлов.
- [x] Branch protection и обязательность CI на PR в `main` подтверждены dry-run PR: merge блокируется, пока required checks не зелёные.

Цель: сначала сделать проверяемый baseline, а уже потом наращивать требования.

Сделать:

- привязать `ci.yml` к branch protection для PR в `main`
- определить rollout-план для `ruff format`: либо массовая нормализация отдельным коммитом, либо поэтапное выравнивание по каталогам
- держать единые `npm` scripts (`lint`, `test`, `typecheck`, `build`) синхронизированными между `web` и `admin`
- не мигрировать тестовый стек на `pytest` только ради моды; сначала стабилизировать текущий `unittest`-контур
- держать CI-команды воспроизводимыми локально без GitHub Actions-магии

Минимальный обязательный pipeline:

- `python-lint`
- `web-lint`
- `admin-lint`
- `python-tests`
- `web-build`
- `admin-build`
- `web-typecheck`
- `admin-typecheck`

Критерий выхода:

- для каждого приложения есть воспроизводимый набор quality-команд
- локальный и CI-запуск используют один и тот же контракт команд

## Фаза 2. Локализация и все пользовательские тексты

Статус: `В работе`

Проверено 2026-03-20:

- [x] `bot` использует единый каталог переводов и `translate()`.
- [x] `web` использует `t(...)` в основном приложении и продуктовых компонентах.
- [x] В backend появился централизованный каталог `packages/locales/ru/api.json` для пользовательских ошибок и уведомлений.
- [ ] Единый `LocaleProvider` или явный верхнеуровневый слой locale-state в `web` не оформлен.
- [ ] Маппинг `stable error code -> translation key` не доведен до системного контракта: часть endpoint-ов все еще отдает `detail=str(exc)`.
- [ ] Источники locale (`accounts.locale`, `language_code`, browser/session`) не выровнены и не зафиксированы как единый runtime-контракт.
- [ ] Операторские тексты `admin` не проходили отдельную инвентаризацию на единообразие и отсутствие внутренних деталей.

Цель: довести проект хотя бы до состояния "один язык, но все строки централизованы", а не оставлять тексты размазанными по коду.

Сделать:

- провести инвентаризацию всех user-facing строк в `web`, `admin`, `bot`, `api`
- расширить `packages/locales` до понятной структуры: `common`, `web`, `bot`, `admin`, `errors`
- считать первым обязательным этапом не мультиязычность, а externalization всех строк
- внедрить единый `LocaleProvider` или аналогичный слой в `web`
- перевести toast-сообщения, placeholders, empty states, CTA, modal-тексты, legal-заголовки, FAQ и help-сообщения на ключи переводов
- в backend перестать слать сырой русский текст как единственный transport-контракт для ошибок, где это влияет на UI
- для бизнес-ошибок ввести стабильные error codes и маппинг `code -> translation key`
- выровнять источники locale:
  - `accounts.locale`
  - Telegram `language_code`
  - browser/session locale
- договориться о fallback-правиле: пока `ru`, позже можно добавить `en`

Критерий выхода:

- в `web` нет новых хардкод-строк в продуктовых компонентах
- `bot` и `web` используют единый каталог текстов
- сервисные и технические сообщения больше не просачиваются в UI как попало

## Фаза 3. Cleanup, декомпозиция и снижение связности

Статус: `В работе`

Проверено 2026-03-20:

- [x] Из [`apps/admin/src/App.tsx`](../apps/admin/src/App.tsx) вынесен первый набор pure helper-функций в [`apps/admin/src/lib/admin-helpers.ts`](../apps/admin/src/lib/admin-helpers.ts) и покрыт тестами.
- [ ] [`apps/admin/src/App.tsx`](../apps/admin/src/App.tsx) остается монолитом на `8986` строк.
- [ ] [`apps/web/src/app/App.tsx`](../apps/web/src/app/App.tsx) остается монолитом на `5125` строк.
- [ ] [`apps/bot/bot/services/menu_renderer.py`](../apps/bot/bot/services/menu_renderer.py) и [`apps/api/app/services/account_linking.py`](../apps/api/app/services/account_linking.py) по-прежнему требуют предметной декомпозиции.
- [ ] В репозитории не зафиксирован пошаговый план разрезания самых рискованных модулей на поддерживаемые части.

Цель: убрать основные точки, где сопровождение уже стало дорогим и рискованным.

Сделать:

- разрезать [`apps/admin/src/App.tsx`](../apps/admin/src/App.tsx) на feature-модули, экраны и hooks
- разрезать [`apps/web/src/app/App.tsx`](../apps/web/src/app/App.tsx) на routing-shell, data hooks и feature pages
- вынести крупные formatter/helper-блоки из [`apps/bot/bot/services/menu_renderer.py`](../apps/bot/bot/services/menu_renderer.py)
- проверить, где [`apps/api/app/services/account_linking.py`](../apps/api/app/services/account_linking.py) стоит разделить на token flow, merge flow и transport helpers
- убрать legacy или вводящие в заблуждение placeholder-состояния
- зачистить dead code, неиспользуемые helpers и старые альтернативные пути, если они уже не являются production fallback
- зафиксировать архитектурные границы: `service`, `transport`, `schema`, `ui`, `shared`

Практическое правило для этого этапа:

- новые большие фичи не вливать в монолитные файлы
- при каждом крупном изменении уменьшать, а не увеличивать размер самых рискованных модулей

Критерий выхода:

- основные entrypoint-файлы и доменные сервисы разбиты на поддерживаемые части
- чтение и ревью критичных модулей больше не требует навигации по тысячам строк

## Фаза 4. Тесты и измеримый baseline качества

Статус: `В работе`

Проверено 2026-03-20:

- [x] У `api` есть сильный backend integration contour для auth, linking, trial, payments, referrals, withdrawals и admin flow.
- [x] У `bot` есть собственные автотесты на i18n, handlers и menu rendering.
- [x] Для `api` и `bot` есть локальные команды тестов и покрытия.
- [x] Текущий локальный backend baseline подтвержден прогоном `scripts/test.sh all` на 2026-03-20.
- [x] В репозитории добавлен минимальный CI workflow, который гоняет `ruff check`, Python tests, `web` lint/test/typecheck/build и `admin` lint/test/typecheck/build.
- [x] Для `web` и `admin` появился минимальный frontend test contour на `Vitest` для pure utility/runtime logic.
- [x] В репозитории добавлен `Vitest` для `web` и `admin`.
- [ ] В репозитории пока нет `Playwright`.
- [x] Blocking quality checks на PR в `main` подтверждены dry-run PR с required checks `python-quality`, `web-quality` и `admin-quality`.
- [ ] Для `web` и `admin` пока нет компонентных и flow-тестов, которые проверяют UI-сценарии через DOM/browser.
- [ ] Не зафиксированы и не автоматизированы пороги покрытия, которые должны блокировать merge.

Цель: сделать регрессии заметными до merge, а не после.

Сделать:

- сохранить текущие backend integration tests как основу и расширять именно критичные user flows
- довести покрытие backend хотя бы до честного baseline с постепенным повышением порога
- добавить тесты для `withdrawals`, `admin auth`, `admin actions`, `notifications`, `promo/referral edge cases`, если там еще остаются белые пятна
- для `web` и `admin` ввести компонентные и flow-тесты на `Vitest + React Testing Library`
- добавить минимум один browser smoke suite на `Playwright` для:
  - browser auth
  - account linking
  - wallet topup redirect flow
  - withdrawal request flow
- выделить набор блокирующих бизнес-сценариев и гонять их на каждом PR в `main`

Стратегия порогов:

- сначала замерить честный baseline по `api` и `bot`
- первым blocking threshold сделать реалистичный порог, который уже проходит текущая база
- дальше поднимать fail-under поэтапно, а не декларативно ставить `80%` и сразу ломать темп команды

Критерий выхода:

- у `api`, `bot`, `web`, `admin` есть автоматический тестовый контур
- merge не проходит при падении критичных flow-тестов

## Фаза 5. Кодовая документация и эксплуатационные docs

Статус: `В работе`

Проверено 2026-03-20:

- [x] В репозитории появился общий стандарт документации в [`docs/code-documentation.md`](./code-documentation.md).
- [x] Уже есть базовые документы по env, security, architecture, launch scope и frontend contract.
- [x] Release checklist, smoke checklist и rollback checklist зафиксированы в отдельных документах.
- [x] Incident runbook-и по платежам, webhook, Mini App, bot и withdrawals выделены в явный набор документов в `docs/runbooks/`.
- [ ] Нет отдельной ревизии, что [`apps/web/FRONTEND_CONTRACT.md`](../apps/web/FRONTEND_CONTRACT.md) полностью синхронизирован с текущим UI.

Цель: код и docs должны объяснять систему, а не требовать устных знаний.

Сделать:

- ввести краткий стандарт docstring для публичных Python-service функций, endpoint-ов и нестандартных security/payment мест
- не документировать очевидное, но обязательно описывать side effects, идемпотентность, внешние интеграции и доменные инварианты
- добавить короткие `README` в сложные каталоги, если без них вход слишком дорогой
- синхронизировать `apps/web/FRONTEND_CONTRACT.md` с фактическим состоянием UI
- держать release checklist, smoke checklist и rollback checklist синхронизированными с реальным процессом
- держать runbooks по инцидентам синхронизированными с текущим operational flow и лог-контуром

Критерий выхода:

- новый разработчик может понять критичные потоки без экскурсии по истории чата
- операционные действия не хранятся только "в голове"

## Фаза 6. Production hardening и release candidate

Статус: `В работе`

Проверено 2026-03-20:

- [x] В репозитории уже есть [`docs/security-checklist.md`](./security-checklist.md) и [`docs/production-env.md`](./production-env.md).
- [x] В репозитории оформлены [`docs/release-checklist.md`](./release-checklist.md), [`docs/smoke-checklist.md`](./smoke-checklist.md) и [`docs/rollback-checklist.md`](./rollback-checklist.md).
- [ ] `npm ci` сигнализирует о dependency-risk: на 2026-03-20 `apps/web` тянет `6` уязвимостей (`1` moderate, `5` high), `apps/admin` — `1` moderate; нужна отдельная triage-ревизия.
- [ ] Не зафиксирован результат отдельной ревизии логов на утечки токенов, `initData` и платежных секретов.
- [ ] Не подтвержден backup/restore сценарий БД.
- [ ] Не подтверждено фактическое выполнение ручного regression smoke перед релизом по browser, Mini App, bot и admin; пока есть только checklist.
- [ ] Не описан финальный release candidate ritual для `dev -> main` с тегом и коротким release note.

Цель: перед merge в `main` закрыть то, что влияет уже не на красоту кода, а на коммерческую надежность.

Сделать:

- пройти по [`docs/security-checklist.md`](./security-checklist.md) и закрыть обязательные пункты именно по текущему стеку
- проверить логи на отсутствие токенов, `initData`, payment payload secrets и другой чувствительной информации
- проверить backup/restore сценарий для БД
- убедиться, что продовые env-переменные реально соответствуют [`docs/production-env.md`](./production-env.md)
- сделать ручной regression smoke перед релизом по браузеру, Mini App, bot и admin
- для solo-режима достаточно подготовить release candidate в `dev` и открыть PR `dev -> main`
- отдельную ветку `release/*` вводить только если появится длинная стабилизация релиза, параллельная разработка или несколько участников

Критерий выхода:

- `main` содержит только проверенный release candidate
- после merge можно ставить git tag и выкладывать release notes без ручного дорасследования

## Минимальная конфигурация GitHub Actions

Первый разумный набор workflow:

- `ci.yml` на `pull_request` и `push` для `dev` и `main`
- job `python-quality`
- job `web-quality`
- job `admin-quality`

Что должно войти в первую версию:

- `python-quality`:
  - установка `uv`
  - `uv sync --frozen --group dev`
  - `uv run --group dev ruff check apps/api apps/bot common scripts`
  - `uv run --group dev ruff format --check apps/api apps/bot common scripts`
  - `./scripts/test.sh all`
- `web-quality`:
  - `npm ci` в `apps/web`
  - `npm run build`
  - `npm run typecheck`
- `admin-quality`:
  - `npm ci` в `apps/admin`
  - `npm run build`
  - `npm run typecheck`

Как вводим это без вреда для темпа:

- CI не должен мешать локальному `git commit`
- на первом этапе проверки нужны для видимости проблем на `push` и `pull_request`, а не как локальный стоп-кран
- обязательными для веточной защиты делаем только проверки для PR в `main`
- `dev` можно оставлять без branch protection, пока идет активная нормализация проекта
- если какая-то проверка постоянно шумит и не помогает принимать решения, ее не делаем blocking до приведения в порядок

Что можно добавить вторым этапом:

- coverage upload и fail-under
- `Vitest`
- `Playwright`
- PR comment с кратким quality summary

Что не стоит делать в первой итерации:

- собирать слишком тяжелый CI с десятком медленных job, пока локальные команды еще не устоялись
- одновременно внедрять новый test runner, новый linter, новый formatter и новый package manager

## Приоритет внедрения

Если идти прагматично, порядок должен быть таким:

1. Фаза 0 и Фаза 1, чтобы включить merge discipline.
2. Фаза 2, чтобы остановить размножение хардкод-строк.
3. Фаза 3 для самых крупных монолитов.
4. Фаза 4, чтобы критичные потоки начали реально страховаться тестами.
5. Фаза 5 и Фаза 6 перед первым merge в `main`.

Текущий practical next step:

1. Часто коммитить и пушить в `feature/*` или `dev`, не дожидаясь идеального состояния.
2. Поднять базовый `ci.yml`, `Makefile` и документацию без локальных commit-blockers.
3. Сделать блокирующими только PR-проверки для `main`, когда quality-команды реально устоятся.
