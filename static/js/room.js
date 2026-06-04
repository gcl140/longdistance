// Watch-party room: synchronized HTML5 player, WebSocket chat/sync, WebRTC face-cam.
// All Django-bound values come from window.LISA_ROOM (set by an inline shim).
(function () {
  const L = window.LISA_ROOM || {};
  const CODE = L.code;
  const CAN_CONTROL = !!L.canControl;
  const SEARCH_URL = L.searchUrl;
  const LIBRARY_URL = L.libraryUrl;
  const REQUEST_URL = L.requestUrl;
  const MSGS_URL = L.msgsUrl;
  const RESUME_POS = L.resumePos || 0;
  // ICE servers for WebRTC. STUN gets peers their public IPs; TURN relays
  // media when direct P2P is blocked (universities, corporate NATs, CGNAT).
  // Free relay courtesy of openrelay.metered.ca — fine for a few users. For
  // production scale, self-host coturn or use Twilio/Cloudflare Calls.
  const STUN = [
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun.cloudflare.com:3478" },
    { urls: "turn:openrelay.metered.ca:80",  username: "openrelayproject", credential: "openrelayproject" },
    { urls: "turn:openrelay.metered.ca:443", username: "openrelayproject", credential: "openrelayproject" },
    { urls: "turn:openrelay.metered.ca:443?transport=tcp", username: "openrelayproject", credential: "openrelayproject" },
  ];

  function csrf() { return document.cookie.match(/csrftoken=([^;]+)/)?.[1] || ""; }
  function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

  const player   = document.getElementById('player');
  const msgBox   = document.getElementById('messages');
  const camStrip = document.getElementById('cam-strip');

  let sock, MYID = null, applying = false, lastUrl = L.videoUrl || "", lastMsgId = 0, hls = null;
  let resumed = false, previewVideo = null, previewBusy = false, previewWant = null;
  // Sync-seek bookkeeping: prevents heartbeat thrashing while a seek is mid-flight.
  let seekingTo = null;        // Target time of the in-flight sync-driven seek, or null.
  let seekStartedAt = 0;       // perf clock when seek began (for safety timeout).
  function fmt(t) {
    if (!isFinite(t) || t < 0) return '0:00';
    t = Math.floor(t);
    const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(s).padStart(2, '0');
  }
  let localStream = null;
  const peers = {};
  const knownPeers = new Set();
  const peerNames = {};
  // Tiles are keyed by USER, not by connection — so reconnects/renegotiations
  // never duplicate a person's tile. peers{} stays keyed per connection.
  const peerUser = {};   // peerId -> userId
  const userPeers = {};  // userId -> Set(peerId)
  const userNames = {};  // userId -> display name

  window.room = function () {
    return {
      tab: 'chat', copied: false, connected: false, syncLabel: '',
      camOn: false, panelOpen: true, movieTitle: L.title || '',
      hasVideo: !!L.hasVideo, videoUnsupported: false,
      searchOpen: false, mode: 'library', q: '', results: [], searchMsg: '',
      libraryResults: [],

      init() {
        window.__room = this;
        connect(); loadHistory(); bindChat(); initPlayer();
        if (CAN_CONTROL) { bindControl(this); this.loadLibrary(); }
        updateCamUI();
      },

      async loadLibrary() {
        try { this.libraryResults = (await (await fetch(LIBRARY_URL)).json()).results || []; } catch (e) {}
      },
      pickLibrary(r) {
        this.movieTitle = r.title + (r.year ? ' (' + r.year + ')' : '');
        this.searchOpen = false;
        setVideo(r.stream_url);
        if (r.subtitle) setSubtitle(r.subtitle);
        sendSync({ video_url: r.stream_url, subtitle: r.subtitle || '', poster: r.poster || '', title: this.movieTitle, position: 0, is_playing: false });
      },
      copyCode() { navigator.clipboard.writeText(location.href); this.copied = true; setTimeout(() => this.copied = false, 1500); },
      loadUrl() {
        const v = document.getElementById('url-input').value.trim();
        if (!v) return;
        setVideo(v); sendSync({ video_url: v, position: 0, is_playing: false });
      },
      async doSearch() {
        this.searchMsg = 'Searching…'; this.results = [];
        try {
          const data = await (await fetch(SEARCH_URL + '?q=' + encodeURIComponent(this.q))).json();
          this.results = data.results || [];
          this.searchMsg = data.error || (this.results.length ? '' : 'No results.');
        } catch (e) { this.searchMsg = 'Search failed.'; }
      },
      pickMovie(r) {
        this.movieTitle = r.title + (r.year ? ' (' + r.year + ')' : '');
        this.searchOpen = false;
        sendSync({ title: this.movieTitle });
      },
      async playFromTmdb(r) {
        try {
          const data = await (await fetch(LIBRARY_URL)).json();
          const lib = (data.results || []).find(x => x.id === r.library_id);
          if (lib) { this.pickLibrary(lib); return; }
        } catch (e) {}
        alert("That movie's in the library but couldn't be loaded — refresh and try again.");
      },
      async requestMovie(r) {
        try {
          const resp = await fetch(REQUEST_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
            body: JSON.stringify({
              tmdb_id: r.id, title: r.title, year: r.year,
              overview: r.overview, poster: r.poster, media_type: r.media_type,
            }),
          });
          const data = await resp.json();
          if (data.in_library) { r.in_library = true; r.library_id = data.library_id; r.playable = true; return; }
          r.voted = true; r.vote_count = data.vote_count;
        } catch (e) { alert('Request failed — try again.'); }
      },
      async toggleCamera() {
        if (this.camOn) { stopCamera(); this.camOn = false; return; }
        try {
          localStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
          addLocalTile();
          this.camOn = true;
          wsSend({ type: 'webrtc', action: 'join', to: null });
          knownPeers.forEach(pid => { if (MYID > pid) makeOffer(pid); });
        } catch (e) { alert('Could not access camera/mic: ' + e.message); }
      },
    };
  };

  /* ---------------- WebSocket ---------------- */
  function connect() {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    sock = new WebSocket(`${scheme}://${location.host}/ws/party/${CODE}/`);
    sock.onopen = () => { window.__room.connected = true; };
    sock.onclose = () => { window.__room.connected = false; setTimeout(connect, 2000); };
    sock.onmessage = (ev) => handle(JSON.parse(ev.data));
  }
  function wsSend(obj) { if (sock && sock.readyState === 1) sock.send(JSON.stringify(obj)); }

  function handle(m) {
    if (m.type === 'welcome') { MYID = m.peer_id; if (CAN_CONTROL) heartbeat(); }
    else if (m.type === 'chat') { if (m.id > lastMsgId) { lastMsgId = m.id; renderMsg(m); if (!m.is_me) playChatDing(); } }
    else if (m.type === 'sync') applySync(m);
    else if (m.type === 'presence') onPresence(m);
    else if (m.type === 'webrtc') onSignal(m);
  }

  /* ---------------- Playback sync ---------------- */
  function isHls(url) { return /\.m3u8(\?|$)/i.test(url || ""); }

  // Point a <video> at a URL. HLS (.m3u8) streams need hls.js on Chrome/Firefox
  // (Safari/iOS play them natively); plain MP4 just sets .src.
  function attachVideo(el, url) {
    if (!url) return;
    if (el === player && hls) { hls.destroy(); hls = null; }  // tear down old stream
    if (isHls(url)) {
      if (el.canPlayType('application/vnd.apple.mpegurl')) {
        el.src = url;                                          // native HLS (Safari)
      } else if (window.Hls && window.Hls.isSupported()) {
        el.removeAttribute('src');                            // hls.js feeds via MSE
        const h = new window.Hls({ enableWorker: true });
        h.loadSource(url);
        h.attachMedia(el);
        if (el === player) hls = h;
      } else {
        el.src = url;                                          // last resort
      }
    } else {
      el.src = url;
    }
  }

  function setVideo(url) {
    if (url && url !== lastUrl) {
      lastUrl = url;
      attachVideo(player, url);
      if (previewVideo && !isHls(url)) previewVideo.src = url;  // thumbs: MP4 only
      resumed = true;
    }
    if (url && window.__room) window.__room.hasVideo = true;
  }
  function setSubtitle(url) {
    if (!url) return;
    let tr = document.getElementById('subtrack');
    if (!tr) {
      tr = document.createElement('track');
      tr.id = 'subtrack'; tr.kind = 'subtitles'; tr.srclang = 'en'; tr.label = 'English'; tr.default = true;
      player.appendChild(tr);
    }
    if (tr.getAttribute('src') !== url) tr.setAttribute('src', url);
    setTimeout(refreshCC, 500);
  }
  function sendSync(partial) { wsSend(Object.assign({ type: 'sync' }, partial)); }
  function bindControl() {
    player.addEventListener('play',  () => { if (!applying) sendSync({ is_playing: true,  position: player.currentTime }); });
    player.addEventListener('pause', () => { if (!applying) sendSync({ is_playing: false, position: player.currentTime }); });
    player.addEventListener('seeked',() => { if (!applying) sendSync({ position: player.currentTime, is_playing: !player.paused }); });
  }
  // Host beats out a sync every 1s while playing — tight enough that guests
  // stay within ~1s of the host even with Cloudflare-Tunnel latency.
  function heartbeat() { setInterval(() => { if (!player.paused) sendSync({ position: player.currentTime, is_playing: true }); }, 1000); }
  function applySync(s) {
    const ctx = window.__room;
    if (s.title) ctx.movieTitle = s.title;
    if (s.video_url) setVideo(s.video_url);
    if (s.subtitle) setSubtitle(s.subtitle);
    if (CAN_CONTROL) { ctx.syncLabel = s.is_playing ? 'playing' : 'paused'; return; }
    if (!lastUrl) return;  // nothing loaded yet (player.src is empty for HLS/MSE)
    applying = true;

    // If a sync-driven seek is still in flight, skip new nudges. Without this,
    // the 1s heartbeat keeps cancelling the in-flight buffer fetch and the
    // guest never lands on the host's position (the "different scenes" bug).
    // Safety: release the lock after 6s in case `seeked` never fires.
    const seekStuck = seekingTo != null && (performance.now() - seekStartedAt) > 6000;
    if (seekingTo != null && !seekStuck) { applying = false; return; }
    if (seekStuck) seekingTo = null;

    if (s.position != null) {
      const drift = s.position - player.currentTime;
      if (Math.abs(drift) > 10) {
        // Late join / huge jump: pause, seek, wait for `seeked` to fire,
        // then resume. Stops the 1s-heartbeat thrash on big gaps.
        seekingTo = s.position; seekStartedAt = performance.now();
        const wasPlaying = s.is_playing !== false;
        player.pause();
        player.currentTime = s.position;
        ctx.syncLabel = 'buffering…';
        const onSeeked = () => {
          player.removeEventListener('seeked', onSeeked);
          seekingTo = null;
          if (wasPlaying) player.play().catch(() => {});
        };
        player.addEventListener('seeked', onSeeked);
      } else if (Math.abs(drift) > 1.5) {
        // Mid-drift hard correction — still gated so we don't restack seeks.
        seekingTo = s.position; seekStartedAt = performance.now();
        player.currentTime = s.position;
        player.playbackRate = 1.0;
        const onSeeked = () => {
          player.removeEventListener('seeked', onSeeked);
          seekingTo = null;
        };
        player.addEventListener('seeked', onSeeked);
      } else if (Math.abs(drift) > 0.3) {
        // 0.3s–1.5s: smooth catch-up via playback rate, no seek.
        player.playbackRate = drift > 0 ? 1.05 : 0.97;
      } else {
        player.playbackRate = 1.0;
      }
      ctx.syncLabel = seekingTo != null ? 'buffering…' : (Math.abs(drift) < 0.3 ? 'in sync' : 'syncing…');
    }
    if (s.is_playing === true && player.paused && seekingTo == null) {
      player.play().catch(() => {});
    }
    if (s.is_playing === false && !player.paused) player.pause();
    applying = false;
  }

  /* ---------------- Chat ---------------- */
  async function loadHistory() {
    try {
      const data = await (await fetch(MSGS_URL)).json();
      (data.messages || []).forEach(m => { renderMsg(m); lastMsgId = Math.max(lastMsgId, m.id); });
    } catch (e) {}
  }
  function renderMsg(m) {
    const wrap = document.createElement('div');
    wrap.className = 'flex flex-col ' + (m.is_me ? 'items-end' : 'items-start');
    wrap.innerHTML = `<div class="max-w-[80%] ${m.is_me ? 'bg-netflix-red' : 'bg-white/10'} rounded-2xl px-3 py-2">
        ${m.is_me ? '' : `<div class="text-[11px] text-white/60 mb-0.5">${esc(m.sender)}</div>`}
        <div class="text-sm break-words">${esc(m.message)}</div></div>
        <span class="text-[10px] text-white/30 mt-0.5">${m.at}</span>`;
    const atBottom = msgBox.scrollHeight - msgBox.scrollTop - msgBox.clientHeight < 90;
    msgBox.appendChild(wrap);
    if (atBottom || m.is_me) msgBox.scrollTop = msgBox.scrollHeight;
  }
  function playChatDing() {
    const a = document.getElementById('notif-ding');
    if (!a) return;
    try { a.currentTime = 0; a.play().catch(() => {}); } catch (e) {}
  }
  function bindChat() {
    document.getElementById('chat-form').addEventListener('submit', (e) => {
      e.preventDefault();
      const input = document.getElementById('chat-input');
      const text = input.value.trim(); if (!text) return;
      input.value = '';
      wsSend({ type: 'chat', message: text });
    });
  }

  /* ---------------- WebRTC (face-cam) ----------------
     Connections are per-peer (channel), but tiles are per-USER so the same
     person never gets duplicate tiles across reconnects/renegotiations. */
  function recordPeer(peerId, userId, name) {
    if (userId !== undefined && userId !== null) {
      peerUser[peerId] = userId;
      (userPeers[userId] = userPeers[userId] || new Set()).add(peerId);
      if (name) userNames[userId] = name;
    }
    if (name) peerNames[peerId] = name;
  }
  // A DOM-safe tile key per user (channel names contain '.!' etc.).
  function tileKeyForPeer(peerId) {
    const uid = peerUser[peerId];
    return uid !== undefined && uid !== null ? 'u' + uid : 'p' + peerId.replace(/[^a-zA-Z0-9_-]/g, '');
  }
  function nameForKey(key, isLocal) {
    if (isLocal) return 'You';
    if (key.charAt(0) === 'u') return userNames[key.slice(1)] || 'Guest';
    return 'Guest';
  }
  function camTile(key, isLocal) {
    let wrap = document.getElementById('camwrap-' + key);
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.id = 'camwrap-' + key;
      wrap.className = 'relative rounded-lg overflow-hidden bg-black aspect-video group ' +
                      (isLocal ? 'ring-2 ring-netflix-red' : 'ring-1 ring-white/15');
      const v = document.createElement('video');
      v.id = 'cam-' + key; v.autoplay = true; v.playsInline = true; if (isLocal) v.muted = true;
      v.className = 'w-full h-full object-cover';
      const ph = document.createElement('div');
      ph.id = 'ph-' + key;
      ph.className = 'absolute inset-0 flex flex-col items-center justify-center bg-netflix-dark hidden';
      ph.innerHTML = '<i class="fas fa-video-slash text-white/40 text-xl mb-1"></i><span class="ph-name text-[10px] text-white/60 px-1 text-center"></span>';
      ph.querySelector('.ph-name').textContent = nameForKey(key, isLocal);
      const label = document.createElement('span');
      label.id = 'lbl-' + key;
      label.className = 'absolute bottom-1 left-1 text-[10px] bg-black/70 px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition pointer-events-none';
      label.textContent = nameForKey(key, isLocal);
      wrap.appendChild(v); wrap.appendChild(ph); wrap.appendChild(label);
      camStrip.appendChild(wrap);
      updateCamUI();
    }
    return document.getElementById('cam-' + key);
  }
  function updateTileName(key) {
    const nm = nameForKey(key, false);
    const l = document.getElementById('lbl-' + key); if (l) l.textContent = nm;
    const ph = document.getElementById('ph-' + key); if (ph) ph.querySelector('.ph-name').textContent = nm;
  }
  function addLocalTile() { camTile('local', true).srcObject = localStream; }
  function setTileStream(peerId, stream) {
    const key = tileKeyForPeer(peerId);
    const v = camTile(key, false);
    v.srcObject = stream; v.classList.remove('hidden');
    document.getElementById('ph-' + key)?.classList.add('hidden');
    updateTileName(key);
  }
  function showCamOff(peerId) {
    const key = tileKeyForPeer(peerId);
    camTile(key, false);
    document.getElementById('cam-' + key)?.classList.add('hidden');
    document.getElementById('ph-' + key)?.classList.remove('hidden');
    updateTileName(key);
  }
  function removeTileKey(key) { document.getElementById('camwrap-' + key)?.remove(); updateCamUI(); }
  function updateCamUI() {
    const empty = document.getElementById('cam-empty');
    if (empty) empty.style.display = camStrip.children.length ? 'none' : 'block';
  }
  // Drop one connection; only remove the user's tile when they have no live peers left.
  function dropPeer(peerId) {
    knownPeers.delete(peerId);
    if (peers[peerId]) { peers[peerId].close(); delete peers[peerId]; }
    const uid = peerUser[peerId];
    delete peerUser[peerId];
    if (uid !== undefined && userPeers[uid]) {
      userPeers[uid].delete(peerId);
      if (userPeers[uid].size === 0) { delete userPeers[uid]; removeTileKey('u' + uid); }
    } else {
      removeTileKey(tileKeyForPeer(peerId));
    }
  }

  function freshPC(peerId) {
    if (peers[peerId]) { peers[peerId].close(); }
    const pc = new RTCPeerConnection({ iceServers: STUN });
    if (localStream) {
      localStream.getTracks().forEach(t => pc.addTrack(t, localStream));
    } else {
      pc.addTransceiver('video', { direction: 'recvonly' });
      pc.addTransceiver('audio', { direction: 'recvonly' });
    }
    pc.onicecandidate = (e) => { if (e.candidate) wsSend({ type: 'webrtc', action: 'ice', to: peerId, signal: e.candidate }); };
    pc.ontrack = (e) => setTileStream(peerId, e.streams[0]);
    peers[peerId] = pc;
    return pc;
  }
  async function makeOffer(peerId) {
    const pc = freshPC(peerId);
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    wsSend({ type: 'webrtc', action: 'offer', to: peerId, signal: offer });
  }

  function onPresence(m) {
    recordPeer(m.peer_id, m.user_id, m.display);
    if (m.event === 'join') {
      knownPeers.add(m.peer_id);
      if (localStream) {
        if (MYID > m.peer_id) makeOffer(m.peer_id);
        else wsSend({ type: 'webrtc', action: 'join', to: m.peer_id });
      }
    } else if (m.event === 'leave') {
      dropPeer(m.peer_id);
    }
  }
  async function onSignal(m) {
    const from = m.from;
    recordPeer(from, m.from_user_id, m.from_user);  // know the user before any tile is made
    if (m.action === 'join') {
      knownPeers.add(from);
      if (MYID > from) makeOffer(from);
      else wsSend({ type: 'webrtc', action: 'join', to: from });
    } else if (m.action === 'offer') {
      const pc = freshPC(from);
      await pc.setRemoteDescription(m.signal);
      const ans = await pc.createAnswer();
      await pc.setLocalDescription(ans);
      wsSend({ type: 'webrtc', action: 'answer', to: from, signal: ans });
    } else if (m.action === 'answer') {
      await peers[from]?.setRemoteDescription(m.signal);
    } else if (m.action === 'ice') {
      try { await peers[from]?.addIceCandidate(m.signal); } catch (e) {}
    } else if (m.action === 'camoff') {
      showCamOff(from);
    }
  }
  function stopCamera() {
    localStream?.getTracks().forEach(t => t.stop());
    localStream = null;
    document.getElementById('camwrap-local')?.remove();
    updateCamUI();
    wsSend({ type: 'webrtc', action: 'camoff', to: null });
  }

  /* ---------------- Custom controls + hover thumbnails ---------------- */
  function refreshCC() {
    const btnCC = document.getElementById('btn-cc'); if (!btnCC) return;
    const tt = player.textTracks;
    if (tt && tt.length) {
      btnCC.classList.remove('hidden');
      if (tt[0].mode === 'disabled') tt[0].mode = 'showing';
      btnCC.classList.toggle('text-netflix-red', tt[0].mode === 'showing');
    }
  }

  function ensurePreview() {
    if (isHls(lastUrl)) return null;  // hover-scrub thumbnails aren't worth an extra HLS pipeline
    if (!previewVideo) {
      previewVideo = document.createElement('video');
      previewVideo.muted = true; previewVideo.preload = 'auto'; previewVideo.playsInline = true;
      previewVideo.addEventListener('seeked', () => {
        const c = document.getElementById('thumb');
        try { c.getContext('2d').drawImage(previewVideo, 0, 0, c.width, c.height); c.style.display = 'block'; }
        catch (e) { c.style.display = 'none'; }
        previewBusy = false;
        if (previewWant != null) { const t = previewWant; previewWant = null; seekPreview(t); }
      });
    }
    if (player.src && previewVideo.src !== player.src) previewVideo.src = player.src;
    return previewVideo;
  }
  function seekPreview(t) {
    const pv = ensurePreview();
    if (!pv) return;  // HLS / no preview pipeline
    if (previewBusy) { previewWant = t; return; }
    previewBusy = true;
    try { pv.currentTime = t; } catch (e) { previewBusy = false; }
  }

  function initPlayer() {
    const wrap = document.getElementById('player-wrap');
    const elPlayed = document.getElementById('played'), elBuf = document.getElementById('buffered'),
          elScrub = document.getElementById('scrubber'), elTimeline = document.getElementById('timeline'),
          elCur = document.getElementById('time-cur'), elDur = document.getElementById('time-dur'),
          elPreview = document.getElementById('preview'), elThumbTime = document.getElementById('thumb-time'),
          btnPlay = document.getElementById('btn-play'), btnMute = document.getElementById('btn-mute'),
          btnFull = document.getElementById('btn-full'), btnCC = document.getElementById('btn-cc');

    player.addEventListener('loadedmetadata', () => {
      elDur.textContent = fmt(player.duration);
      if (!resumed && RESUME_POS > 1) { try { player.currentTime = RESUME_POS; } catch (e) {} }
      resumed = true;
      refreshCC();
    });
    const evalVideo = () => {
      if (!window.__room) return;
      if (player.videoWidth > 0) { window.__room.videoUnsupported = false; return; }
      if (player.readyState >= 2 && player.currentTime > 1.2 && player.videoWidth === 0) {
        window.__room.videoUnsupported = true;
      }
    };
    player.addEventListener('loadedmetadata', evalVideo);
    player.addEventListener('loadeddata', evalVideo);
    player.addEventListener('playing', evalVideo);
    player.addEventListener('timeupdate', evalVideo);
    player.addEventListener('timeupdate', () => {
      const d = player.duration || 0, pct = d ? player.currentTime / d * 100 : 0;
      elPlayed.style.width = pct + '%'; elScrub.style.left = pct + '%';
      elCur.textContent = fmt(player.currentTime);
    });
    player.addEventListener('progress', () => {
      if (player.buffered.length && player.duration)
        elBuf.style.width = (player.buffered.end(player.buffered.length - 1) / player.duration * 100) + '%';
    });
    const bigPlay = document.getElementById('big-play'),
          btnBack = document.getElementById('btn-back'), btnFwd = document.getElementById('btn-fwd');
    function setPlayIcons() {
      const icon = player.paused ? 'fa-play' : 'fa-pause';
      if (btnPlay) btnPlay.innerHTML = `<i class="fas ${icon}"></i>`;
      if (bigPlay) bigPlay.innerHTML = `<i class="fas ${icon}"></i>`;
    }
    player.addEventListener('play', setPlayIcons);
    player.addEventListener('pause', setPlayIcons);

    function togglePlay() { player.paused ? player.play() : player.pause(); }
    function skip(sec) { if (player.duration) player.currentTime = Math.min(player.duration, Math.max(0, player.currentTime + sec)); }
    function toggleFull() {
      if (document.fullscreenElement) document.exitFullscreen();
      else (wrap.requestFullscreen ? wrap.requestFullscreen() : player.requestFullscreen())?.catch?.(() => {});
    }
    function toggleMute() {
      player.muted = !player.muted;
      btnMute.innerHTML = player.muted ? '<i class="fas fa-volume-xmark"></i>' : '<i class="fas fa-volume-high"></i>';
    }
    function toggleCC() {
      const tt = player.textTracks[0]; if (!tt) return;
      tt.mode = (tt.mode === 'showing') ? 'hidden' : 'showing';
      btnCC.classList.toggle('text-netflix-red', tt.mode === 'showing');
    }

    if (btnPlay) btnPlay.addEventListener('click', togglePlay);
    if (bigPlay) bigPlay.addEventListener('click', togglePlay);
    if (btnBack) btnBack.addEventListener('click', () => skip(-10));
    if (btnFwd)  btnFwd.addEventListener('click', () => skip(10));
    btnMute.addEventListener('click', toggleMute);
    btnFull.addEventListener('click', toggleFull);
    btnCC.addEventListener('click', toggleCC);

    if (player.textTracks && player.textTracks.addEventListener) player.textTracks.addEventListener('addtrack', refreshCC);
    [300, 1000, 2500].forEach(ms => setTimeout(refreshCC, ms));

    document.addEventListener('keydown', (e) => {
      const tag = (e.target.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || e.target.isContentEditable) return;
      if (!window.__room || !window.__room.hasVideo) return;
      switch (e.key) {
        case ' ': case 'k': if (CAN_CONTROL) { e.preventDefault(); togglePlay(); } break;
        case 'ArrowRight': if (CAN_CONTROL) { e.preventDefault(); skip(10); } break;
        case 'ArrowLeft':  if (CAN_CONTROL) { e.preventDefault(); skip(-10); } break;
        case 'f': case 'F': e.preventDefault(); toggleFull(); break;
        case 'm': case 'M': toggleMute(); break;
      }
    });

    function pctAt(clientX) { const r = elTimeline.getBoundingClientRect(); return Math.min(1, Math.max(0, (clientX - r.left) / r.width)); }
    elTimeline.addEventListener('mousemove', (e) => {
      if (!player.duration) return;
      const p = pctAt(e.clientX), t = p * player.duration;
      elPreview.style.left = (p * elTimeline.clientWidth) + 'px';
      elThumbTime.textContent = fmt(t);
      elPreview.classList.remove('hidden'); elPreview.classList.add('flex');
      seekPreview(t);
    });
    elTimeline.addEventListener('mouseleave', () => { elPreview.classList.add('hidden'); elPreview.classList.remove('flex'); });
    // Click-to-seek is gated on CAN_CONTROL — the host is authoritative.
    if (CAN_CONTROL) {
      elTimeline.addEventListener('click', (e) => { if (player.duration) player.currentTime = pctAt(e.clientX) * player.duration; });
    }

    // If the room already has a video, attach it. HLS must go through hls.js
    // (the template can't set a working .m3u8 src on Chrome); MP4 keeps the
    // template-set src. Done here (not via setVideo) so `resumed` stays false
    // and the loadedmetadata handler can still seek to RESUME_POS.
    if (lastUrl && isHls(lastUrl)) attachVideo(player, lastUrl);
    if (lastUrl) ensurePreview();
  }
})();
