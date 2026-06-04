# CLAUDE.md — working notes for AI sessions

Context and conventions for working in this repo. Read this first.

## What this project is

**Lisa** — a Netflix-styled **long-distance watch-party app**: friends/couples in
different places watch movies *in sync*, with chat, video calls, and movie requests.
The product design lives in `DESIGN.md`; the build plan in `ROADMAP.md`; the original
research notes in `junk/steps/*.md`.

> Note: the repo (`longdistance`) and Django app (`yuzzaz`) keep their original names,
> and many URL route names still carry a `_voima` suffix (e.g. `contact_voima`,
> `journey_voima`, `news_voima`). These are **legacy identifiers — do not rename them**,
> they'd break `{% url %}` reverses and OAuth config. The user-facing brand is "Lisa".

## Stack

- **Django 6.0.5** on **Python 3.14**, venv at `./venv`
- **DB:** SQLite (`db.sqlite3`) for now → Postgres planned (see ROADMAP)
- **Auth:** custom user + Google OAuth via `social_django`
- **Frontend:** server-rendered Django templates + **Tailwind (CDN)** + **Alpine.js** + Font Awesome 6.4 + Toastify
- **Planned real-time:** Django Channels + Redis (chat/sync/signaling), WebRTC (A/V)
- **Planned external API:** TMDb (movie search/posters) — *not* IMDb scraping, *not* torrent sites

## Layout

```
longdistance/        # project config (settings, urls, asgi, wsgi)
yuzzaz/              # the (only) app
  models.py          # CustomUser (email-as-login, telephone, profile_picture)
  views.py forms.py urls.py admin.py tokens.py
  templates/yuzzaz/  # full_base.html (app shell), base copy.html (auth shell),
                     # land.html (Netflix home), login/register/password_reset_*
  templates/partials/
static/images/       # EMPTY in this snapshot (no bg.jpg/fav.png) — degrade gracefully
junk/steps/          # research notes that define the product
```

## Key facts & gotchas

- **Custom user:** `AUTH_USER_MODEL = 'yuzzaz.CustomUser'`. Login is by **email** (the
  `username` field stores the email). Always reference the user via `settings.AUTH_USER_MODEL`.
- **Two base templates:** `full_base.html` = the dark Netflix app shell (nav + footer,
  used by `land.html`); `base copy.html` = the auth shell (centered card on a dark
  backdrop, used by the password-reset pages). `login.html` and `register.html` are
  standalone full pages.
- **`maroon` Tailwind token is aliased to Netflix red** so legacy markup renders red.
- **Email:** Gmail SMTP via `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD` in `.env`;
  `DEFAULT_FROM_EMAIL = EMAIL_HOST_USER`. **`.env` changes need a server restart** —
  Django's autoreloader does not watch `.env`, and `load_dotenv()` won't override vars
  already set in the shell.
- **Secrets:** `.env` (gitignored) holds Google OAuth + Gmail creds. Never print or commit them.

## Commands

```bash
./venv/bin/python manage.py check          # fast sanity check (run after template/settings edits)
./venv/bin/python manage.py runserver      # dev server (restart after .env changes)
./venv/bin/python manage.py makemigrations && ./venv/bin/python manage.py migrate
```

## Conventions when editing

- After editing templates or settings, run `manage.py check`.
- Follow `DESIGN.md` for any UI: dark canvas, single red accent, edge-to-edge rows.
- Keep components resilient to missing images (`static/images/` is empty).
- Don't rename `_voima` routes or the `yuzzaz` app. Replace only **visible** "Voima" text.
- Prefer adding new watch-party features in the existing `yuzzaz` app unless a clean
  split is warranted (a dedicated `party`/`realtime` app may come with Channels).
