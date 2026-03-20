# Release Process

Этот документ фиксирует минимальный ritual выпуска `dev -> main` для solo-режима.

## Базовый поток

1. Все готовые изменения сначала попадают в `dev`.
2. Когда `dev` стал release candidate, открывается PR `dev -> main`.
3. Для этого PR подготавливается release note по шаблону [`docs/releases/TEMPLATE.md`](./releases/TEMPLATE.md).
4. PR проходит self-review, CI и ручной smoke.
5. После merge в `main` создается git tag формата `v0.x.y`.
6. Итоговый release note сохраняется в `docs/releases/v0.x.y.md` и переносится в GitHub Release description, если используется GitHub Release UI.

## Когда открывать PR `dev -> main`

Открываем release PR только когда:

- все обязательные изменения уже в `dev`
- baseline качества зеленый локально и в CI
- нет известных blocker-дефектов для запуска
- release candidate понятен по составу и не требует новых обязательных патчей поверх PR

## Правило по тегам

- Используем формат `v0.x.y`
- `x` увеличиваем при заметном наборе продуктовых изменений или новой фазе готовности
- `y` увеличиваем для фиксов и стабилизационных выпусков в рамках того же функционального набора
- Не создаем tag до merge в `main`
- Один merge в `main` соответствует одному release tag

## Где хранить release notes

- Черновик для релиза готовим по [`docs/releases/TEMPLATE.md`](./releases/TEMPLATE.md)
- Финальный release note храним в `docs/releases/v0.x.y.md`
- Если release note уточнялся после smoke или после merge, в репозитории должен остаться финальный вариант, совпадающий с тем, что опубликовано во внешнем release UI

## Минимальное содержимое release note

- что вошло в релиз
- что изменилось для пользователя или оператора
- какие риски остались
- как релиз проверяли
- что особенно смотреть после выкладки

## Определение готовности release PR

Release PR `dev -> main` считаем готовым к merge, когда:

- заполнен PR template
- заполнен draft release note
- зеленые required checks
- выполнен [`docs/smoke-checklist.md`](./smoke-checklist.md)
- подтвержден rollback path по [`docs/rollback-checklist.md`](./rollback-checklist.md)

## Команды после merge

Пример:

```bash
git checkout main
git pull --ff-only origin main
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0
```

Если используется GitHub Release, тело релиза собираем из `docs/releases/v0.1.0.md`.
