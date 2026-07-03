# CLAUDE.md — telegram/

Scoped guidance for `telegram/` (the aiogram 3 bot). See the repo-root `CLAUDE.md`
for the big picture.

## What this is

The Telegram **bot** (aiogram 3): start handler, the webhook setup, and localized message
templates. It is a **repo-root package**, NOT under `backend/` — the backend image build context
is `../backend`, so this package is **mounted read-only** into the api/worker/beat containers at
`/app/telegram`. The bot imports `app.core.config.settings` (the backend package is on the path
inside those containers).

There is **no separate bot container** (DEC-bot-webhook-no-separate-container): the aiogram webhook
is served by the FastAPI **api** service. `app/main.py`'s lifespan calls `telegram.bot.setup_webhook()`
on startup when `PUBLIC_WEBAPP_URL` is set.

## Layout

| Path | Role |
|------|------|
| `bot.py` | `bot`/`dp` aiogram singletons, `setup_webhook()`, `load_template()`, `web_app_keyboard()`. |
| `handlers/start.py` | `start_router` — the `/start` handler. |
| `templates/{ru,uz,tr}/` | Message templates (`start.txt`, `status_change.txt`). |

## Notes specific to this package

- **Import-safe**: aiogram `Bot`/`Dispatcher` are constructed at import but open no socket, so
  importing `telegram.bot` under pytest does not hit the network. Network I/O only happens in
  `setup_webhook()` / send calls.
- `setup_webhook()` **no-ops when `PUBLIC_WEBAPP_URL` is empty** so dev/CI never call Telegram.
  Webhook URL = `${PUBLIC_API_URL or PUBLIC_WEBAPP_URL}/api/v1/telegram/webhook/${WEBHOOK_SECRET}`
  (the webhook lives on the API domain, `api.ai-imex.com`); the WebApp button points at
  `${PUBLIC_WEBAPP_URL}/` (the Web App is served at the root of `ai-imex.com`).
- **Never log `WEBHOOK_SECRET`** — `setup_webhook` logs a masked URL only (CR-03).
- **Templates**: `load_template(lang, name)` falls back to `ru` when a lang dir is missing. Add new
  templates to all of `ru`/`uz`/`tr`.
- The webhook **route** lives in the backend (`app/api/telegram_webhook.py`); outbound status-change
  notifications are sent from the Celery `notify` tasks. This package supplies the bot client + templates.
