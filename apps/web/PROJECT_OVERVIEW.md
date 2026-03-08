# Обзор frontend-части

## Назначение

`apps/web` - это пользовательский клиент RemnaStore для:
- мобильного браузера
- десктопного браузера
- Telegram Mini App

Он не должен содержать критичную бизнес-логику денег, подписок или рефералов. Эти решения принимает backend в `apps/api`.

## Текущее состояние

### Уже реализовано
- базовый app shell
- login через браузер и Telegram Mini App
- связка browser и Telegram аккаунтов
- адаптация под светлую и темную тему
- мобильный layout с фиксированными header/footer
- отображение профиля, тарифов, настроек и реферального раздела

### Еще в работе
- полный платежный flow
- реальные backend-данные по рефералке без placeholder-состояний
- история операций и уведомления
- UI заявок на вывод
- FAQ и policy pages

## Ключевые экраны

- `App.tsx` - корневой контейнер и orchestration клиентских сценариев
- `LoginPage.tsx` - вход и возврат из OAuth flow
- `Header.tsx` - верхняя панель профиля и баланса
- `BottomNav.tsx` - нижняя навигация
- `PlansPage.tsx` - тарифы и покупка
- `ReferralPage.tsx` - раздел рефералов
- `SettingsPage.tsx` - настройки, тема и связка аккаунтов
- `TopUpModal.tsx` - сценарий пополнения

## Документы, на которые стоит ориентироваться

- [`../../README.md`](../../README.md)
- [`../../docs/account-linking.md`](../../docs/account-linking.md)
- [`../../docs/launch-roadmap.md`](../../docs/launch-roadmap.md)
- [`../../docs/launch-progress.md`](../../docs/launch-progress.md)

## Что не считать источником истины

Старые документы про `Supabase Edge Functions`, `KV Store` и демо-платежи можно использовать только как исторический контекст. Для текущей разработки источником истины являются код `apps/api`, `apps/web` и документы в `docs/`.
