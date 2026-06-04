# Deploying Lisa (self-host on an old PC + Cloudflare Tunnel)

The plan from `junk/steps/pc.md` + `cloudfare.md`: run the app on a home PC, expose it
through a Cloudflare Tunnel (no port-forwarding, free TLS), keep Postgres private.

```
Browser ──https──> Cloudflare ──tunnel──> Old PC
                                           ├── Daphne (ASGI: HTTP + WebSockets)
                                           ├── Redis        (channel layer)
                                           └── PostgreSQL   (private, localhost only)
```

Lisa is an **ASGI** app (Channels/WebSockets) — it must run under **Daphne/Uvicorn**, not
plain WSGI/gunicorn-sync.

---

## 1. Server prerequisites (Ubuntu)

```bash
sudo apt update
sudo apt install -y python3-venv postgresql redis-server
```

## 2. App setup

```bash
git clone <your-repo> lisa && cd lisa
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then edit (see below)
```

### `.env` for production
```
DJANGO_SECRET_KEY=<long random string>
DEBUG=False
ALLOWED_HOSTS=lisa.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://lisa.yourdomain.com
REDIS_URL=redis://127.0.0.1:6379/0
POSTGRES_DB=lisa
POSTGRES_USER=lisa
POSTGRES_PASSWORD=<db password>
POSTGRES_HOST=127.0.0.1
# + GOOGLE_*, EMAIL_*, TMDB_API_KEY
```

## 3. Database

```bash
sudo -u postgres psql -c "CREATE DATABASE lisa;"
sudo -u postgres psql -c "CREATE USER lisa WITH PASSWORD '<db password>';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE lisa TO lisa;"

python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

> **Never expose Postgres to the internet** — keep `POSTGRES_HOST=127.0.0.1`. Only the app talks to it.

## 4. Run the ASGI server (Daphne)

```bash
daphne -b 0.0.0.0 -p 8000 longdistance.asgi:application
```

Make it a service so it restarts on boot/crash — `/etc/systemd/system/lisa.service`:

```ini
[Unit]
Description=Lisa ASGI
After=network.target redis-server.service postgresql.service

[Service]
WorkingDirectory=/home/youruser/lisa
EnvironmentFile=/home/youruser/lisa/.env
ExecStart=/home/youruser/lisa/venv/bin/daphne -b 127.0.0.1 -p 8000 longdistance.asgi:application
Restart=always
User=youruser

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now lisa
```

## 5. Cloudflare Tunnel

```bash
# install cloudflared, then:
cloudflared tunnel login
cloudflared tunnel create lisa
cloudflared tunnel route dns lisa lisa.yourdomain.com
```

`~/.cloudflared/config.yml`:
```yaml
tunnel: <TUNNEL_ID>
credentials-file: /home/youruser/.cloudflared/<TUNNEL_ID>.json
ingress:
  - hostname: lisa.yourdomain.com
    service: http://127.0.0.1:8000
  - service: http_404
```

```bash
sudo cloudflared service install   # run the tunnel as a service
```

Cloudflare proxies WebSockets automatically, so `wss://` for the watch-room socket works
with no extra config. Visitors hit `https://lisa.yourdomain.com`; the tunnel forwards to
Daphne on the PC.

---

## Production checklist
- [ ] `DEBUG=False`, real `DJANGO_SECRET_KEY`, correct `ALLOWED_HOSTS` + `CSRF_TRUSTED_ORIGINS`
- [ ] Redis running and `REDIS_URL` set (so sync/chat work across multiple workers)
- [ ] Postgres bound to localhost only; app uses it (`POSTGRES_DB` set)
- [ ] `collectstatic` run; static files served (Cloudflare caches them)
- [ ] Google OAuth redirect URIs updated to the public domain
- [ ] **WebRTC note:** the face-cam uses a public STUN server. On strict/symmetric NATs a
      **TURN** server is needed for the video to connect — add one (e.g. coturn or a hosted
      TURN) to `STUN` in `room.html` when you productionize calls.
- [ ] Home upload bandwidth is your ceiling — fine for control messages + a 1:1 cam; heavy
      video should be served from a CDN/dedicated host, not the home connection.
