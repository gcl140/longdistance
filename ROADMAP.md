# Lisa — Build Roadmap

The plan to get from "Netflix-styled shell + auth" to "two people watching a movie
together in sync, with chat and a face-cam." Phases are ordered so each one is usable on
its own and de-risks the next. Derived from the research in `junk/steps/`.

**North-star MVP:** _Gift invites Bo → they join a room → pick a movie → it plays in sync
for both → they chat → (later) see each other's faces._

---

## Phase 0 — Foundations ✅ (done)
- Netflix UI: home/billboard/rows, nav, footer
- Auth: login, register, password reset, activation email, Google OAuth
- Brand rename Voima → Lisa
- These docs (DESIGN / CLAUDE / README / ROADMAP)

## Phase 1 — Data backbone ✅ (done)
Stand up the watch-party models (the "minimum viable schema" from `simplemodels.md`).
- `Contact` (friends), `WatchParty` (room + access code), `WatchPartyMember`,
  `VideoSession` (current video state), `PartyInvite`, `PartyMessage`
- Admin registration + migrations
- Basic pages: create a party, list my parties, party detail (static shell)
- **Deliverable:** you can create a room and see it in the DB/admin.
- **No real-time yet** — purely models + CRUD + templates.

## Phase 1.5 — Full UI + HTTP-polling realtime ✅ (done)
Built the entire product UI and a working (polling-based) realtime layer so the app is
usable end-to-end *before* Channels:
- Dashboard (auth vs. anon), nav wired to real routes
- Parties: my-parties, create, join-by-code, **watch room** (player + sync + chat + people + invite)
- Friends: add/remove/favorite, party invites accept/decline
- Host-authoritative playback sync + chat via JSON endpoints polled every ~2s
- **Polling is a stand-in** — Phase 2 swaps it for WebSockets with no UI changes.

## Phase 2 — Real-time over WebSockets ✅ (done)
- `channels` + `daphne` + `channels-redis`; ASGI routing; `PartyConsumer` per room
- Chat + play/pause/seek pushed instantly over WS (in-memory layer in dev, Redis in prod)
- Verified live: connect, welcome, chat broadcast, host→guest sync, control gate, persistence

## Phase 3b — Player polish ✅ (done)
- Custom video controls (play/seek/volume/fullscreen/CC) with a **hover-thumbnail scrubber**
- **Resume**: seeks to `VideoSession.current_position` on (re)join
- **Subtitles**: WebVTT `<track>` + CC button; subtitle synced over WS
- **Range-aware media serving** (`catalog/media_serve.py`) so seeking large files works
  (Django's default serve ignores `Range` → seeking hung). Prod: serve media via Nginx.
- Face-cam fixed to be bidirectional (higher-id peer always offers); "You"/name hover labels;
  cameras live in the top of the right panel; panel has a collapse/expand arrow.

## Phase 3 — Synchronized playback (the core magic)
Reuse the Phase 2 socket to carry playback control, not just chat.
- HTML5 `<video>` player in the room (start with a static/sample MP4 or HLS URL)
- Broadcast `play` / `pause` / `seek` + periodic host `sync` with drift correction
  (ignore <0.5s, jump on >2s) per `instr.md`
- Host vs. member roles; `VideoSession` persists position so latecomers join at the right spot
- Subtitles via local `.vtt` `<track>`; sync only `subtitle_change` events (`subtitles.md`)
- **Deliverable:** one person hits play/seek, everyone's video follows.

## Phase 4 — Movie catalog ✅ (done)
- `catalog` app: TMDb search proxy + trending endpoint (key in `.env`, graceful without)
- **`Movie` model** — uploaded `video_file` OR external `video_url`, poster (upload or TMDb URL), tmdb_id
- **Upload dashboard** (staff-only) with TMDb autofill; **library** browse page; admin
- "Watch together" on a library movie spins up a party preloaded with the real video
- In-room picker has a **My Library** tab (loads real playable files) + TMDb tab (title only)
- Media served via `MEDIA_URL`/`MEDIA_ROOT` (dev); production source = self-hosted media API
- **Still TODO (Phase 4b):** `MovieRequest` + voting for unavailable titles (`movierequest.md`)

## Phase 5 — Presence, invites & notifications
- Online/last-seen presence in rooms; "X joined" events
- Invite friends to a party; accept/decline
- `Notification` model (generic FK) + real-time badge updates over the existing socket
- **Deliverable:** invite a friend, they get a live notification and can join.

## Phase 6 — Video calls (face-cam) ✅ (done, 1:1)
- WebRTC peer connection with **Channels as the signaling server** (join/offer/answer/ICE)
- Face-cam tiles overlaid on the player, camera toggle, auto-connect on join, cleanup on leave
- Public STUN; **TURN needed for strict NATs in prod** (see DEPLOY.md)

## Phase 7 — Productionize & deploy ✅ (config done)
- Env-driven `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`
- SQLite (dev) ↔ **PostgreSQL** (set `POSTGRES_DB`); Redis channel layer via `REDIS_URL`
- `requirements.txt`, `.env.example`, **`DEPLOY.md`** (Daphne + Cloudflare Tunnel + systemd)
- **Still TODO:** actually provision the PC/tunnel; error pages

## Calendar & scheduling ✅ (done)
- `WatchParty.scheduled_for`; create-party form takes an optional date/time
- `schedule` app: month-grid **calendar** of your hosted/joined/invited movie nights + upcoming list
- **`.ics`**: per-party "Add to Calendar" download + a tokened **subscribe feed** for
  Google/Apple/Outlook (`calendar.md` Options 1 & 2). Verified end-to-end.

---

## Sequencing rationale
1. **Models before behavior** — everything hangs off the schema, so Phase 1 unblocks all.
2. **Chat before sync** — same socket plumbing, but chat is trivial to verify; it proves
   Channels/Redis works before we layer on the trickier drift-corrected sync.
3. **Sync before calls** — synchronized playback is the product's reason to exist; WebRTC
   is the hardest piece and is additive, so it comes after the core works.
4. **Deploy last** — keep iterating locally; ship once there's something worth reaching.

## Decisions (resolved 2026-06-02)
- **Video source:** a **self-hosted media API on a home-PC server** (Phase 7's old-PC box,
  brought forward conceptually). `VideoSession.video_url` points at that API. Phase 3 can
  still start against a sample/placeholder URL until the media API is live.
- **Video calls:** **1:1 only** for now (the long-distance-couple case). No group calls yet.
- **App structure:** **separate Django apps**, not everything in `yuzzaz`.
  - `friends` — Contact / friendships
  - `parties` — WatchParty, WatchPartyMember, VideoSession, PartyInvite, PartyMessage
  - (later) `catalog` — movies + MovieRequest (Phase 4), `notifications` (Phase 5)
  - `yuzzaz` keeps the CustomUser + auth (not worth a risky migration to move it).
