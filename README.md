# Lisa 🎬

**Watch movies together, from anywhere.** Lisa is a Netflix-styled watch-party app for
long-distance friends and couples — synchronized playback, live chat, video calls, and a
shared movie wishlist, all in one dark, cinematic interface.

> Built with Django. Designed to feel like Netflix, behave like a cinema you share with
> someone far away.

## Features

**Now**
- 🎨 Netflix-style home, browse rows, and billboard hero
- 🔐 Email + Google sign-in, registration, password reset (with show/hide password)
- 📧 Account activation email

**Planned** (see [`ROADMAP.md`](ROADMAP.md))
- 👥 Friends / contacts and party invites
- 🛋️ Watch parties — synchronized play / pause / seek across viewers
- 💬 Real-time chat in the room
- 📹 Face-cam video calls while you watch (WebRTC)
- 🔎 Movie search & posters via TMDb, plus "request a movie" with voting
- 🔔 Real-time notifications · 📅 schedule movie nights (.ics)

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Django 6 · Python 3.14 |
| Auth | Custom email-login user · Google OAuth (`social_django`) |
| Frontend | Django templates · Tailwind (CDN) · Alpine.js · Font Awesome |
| Database | SQLite (dev) → PostgreSQL (planned) |
| Real-time | Django Channels + Redis (planned) |
| Media/AV | HLS/HTTP video · WebRTC for calls (planned) |
| Metadata | TMDb API (planned) |
| Hosting | Self-host (old PC) behind Cloudflare Tunnel (planned) |

**Core architecture rule:** video and control are separate channels. The movie streams
over HTTP/HLS/WebRTC; WebSockets carry only tiny JSON control messages (`{"type":"play","time":120.5}`).

## Quickstart

```bash
# 1. Activate the bundled virtualenv (or create your own)
source venv/bin/activate

# 2. Configure secrets
cp .env.example .env   # then fill in the values (see below)

# 3. Migrate and run
python manage.py migrate
python manage.py runserver
# → http://127.0.0.1:8000/home/
```

### Environment variables (`.env`)

```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
EMAIL_HOST_USER=you@gmail.com          # Gmail address
EMAIL_HOST_PASSWORD=xxxxxxxxxxxxxxxx   # Gmail App Password (16 chars, not your login pw)
```

> ⚠️ After editing `.env`, **restart the dev server** — Django does not auto-reload on `.env` changes.

## Project docs

- [`DESIGN.md`](DESIGN.md) — the visual design system
- [`ROADMAP.md`](ROADMAP.md) — phased build plan
- [`CLAUDE.md`](CLAUDE.md) — conventions & gotchas for contributors / AI sessions
- [`junk/steps/`](junk/steps/) — original research notes behind the architecture

## Status

Early development. The UI shell and auth flow are in place; the watch-party engine is next.
