# Broadcasts V1 Contract

## Goal

`broadcasts` is a separate admin domain for mass campaigns. It is not mixed with event-based `notifications`.

V1 covers:
- draft creation and editing from admin UI
- audience estimation before launch
- shared content contract for `in_app` and `telegram`
- future-safe schema for scheduler, worker and delivery stats

V1 does not yet cover:
- scheduled launch
- actual fan-out delivery worker
- test send
- pause/resume

## Domain Model

### `broadcasts`

One campaign draft or launched campaign.

Core fields:
- `name`: internal campaign name for operators
- `title`: user-visible title, used in in-app notifications and Telegram header
- `body_html`: Telegram-compatible HTML subset shared by both channels
- `content_type`: `text` or `photo`
- `image_url`: required for `photo`
- `channels`: any of `in_app`, `telegram`
- `buttons`: up to 3 URL buttons for Telegram
- `audience`: current audience rule
- `status`: `draft`, `scheduled`, `running`, `paused`, `completed`, `failed`, `cancelled`

Operational fields:
- `estimated_total_accounts`
- `estimated_in_app_recipients`
- `estimated_telegram_recipients`
- `scheduled_at`, `launched_at`, `completed_at`, `cancelled_at`
- `last_error`

### `broadcast_deliveries`

Per-account per-channel delivery row for launched campaigns.

V1 creates the table now so the worker can use it later.

## Content Contract

Canonical text format: Telegram HTML subset.

Allowed tags in V1:
- `b`, `strong`
- `i`, `em`
- `u`, `ins`
- `s`, `strike`, `del`
- `code`
- `pre`
- `blockquote`
- `tg-spoiler`
- `a href="..."`

Notes:
- emoji are stored as plain Unicode
- arbitrary HTML is not allowed
- buttons are stored separately from `body_html`
- V1 buttons are URL-only, no callback buttons yet

## Audience Contract

`audience.segment` values:
- `all`
- `active`
- `with_telegram`
- `paid`
- `expired`

`audience.exclude_blocked`:
- defaults to `true`
- blocked accounts should be excluded from most campaigns

At draft stage the audience is dynamic and used only for estimates.
At launch stage the worker must create an immutable recipient snapshot.

## API Contract

Admin endpoints:
- `GET /api/v1/admin/broadcasts`
- `POST /api/v1/admin/broadcasts`
- `GET /api/v1/admin/broadcasts/{broadcast_id}`
- `PUT /api/v1/admin/broadcasts/{broadcast_id}`

Create/update payload:
- `name`
- `title`
- `body_html`
- `content_type`
- `image_url`
- `channels`
- `buttons`
- `audience`

Responses include:
- normalized broadcast payload
- current status
- audience estimates per channel
- timestamps and creator/updater ids

## Delivery Strategy

When launch is implemented:
- `in_app` delivery should fan out into regular `notifications`
- `telegram` delivery should use a dedicated `broadcast worker`
- each recipient/channel should be tracked in `broadcast_deliveries`
- launch should snapshot the audience at that moment

## Admin UX Contract

V1 admin screen must provide:
- campaign list
- draft editor
- channel selection
- audience selector
- Telegram URL buttons editor
- visual preview for `telegram` and `in_app`
- live recipient estimates

Future admin UX:
- send test
- send now / schedule
- pause / resume
- progress stats and failure drill-down
