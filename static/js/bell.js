// Notification bell + live WebSocket + friend-request response handler.
// Django URLs come from window.LISA_BELL.
(function () {
  const C = window.LISA_BELL || {};

  function getCookie(name) {
    const m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  function toast(text, ok) {
    if (window.Toastify) Toastify({
      text: text, duration: 4000, close: true, gravity: 'top', position: 'right',
      backgroundColor: ok === false ? '#E50914' : '#16a34a',
    }).showToast();
  }
  window.lisaCsrf = () => getCookie('csrftoken');

  function playDing() {
    const a = document.getElementById('notif-ding');
    if (!a) return;
    try { a.currentTime = 0; a.play().catch(() => {}); } catch (e) {}
  }

  // Presence dots
  const onlineSet = new Set();
  function applyDot(uid, online) {
    document.querySelectorAll('[data-presence-user="' + uid + '"]').forEach(el => {
      el.classList.toggle('bg-green-400', online);
      el.classList.toggle('bg-white/30', !online);
      el.title = online ? 'Online' : 'Offline';
    });
  }
  window.lisaApplyPresence = applyDot;
  window.lisaIsOnline = (uid) => onlineSet.has(Number(uid));
  function setPresence(uid, online) {
    uid = Number(uid);
    if (online) onlineSet.add(uid); else onlineSet.delete(uid);
    applyDot(uid, online);
  }
  fetch(C.presenceUrl).then(r => r.json()).then(d => {
    (d.online || []).forEach(uid => setPresence(uid, true));
  }).catch(() => {});

  // Shared Alpine store for the bell + socket
  document.addEventListener('alpine:init', () => {
    Alpine.store('notif', {
      unread: 0, items: [], open: false, modal: null,
      receive(n) {
        this.items.unshift(n);
        if (this.items.length > 50) this.items.pop();
        if (!n.is_read) this.unread++;
      },
      removeByRequest(frId) {
        const idx = this.items.findIndex(x => x.data && x.data.friend_request_id === frId);
        if (idx !== -1) {
          if (!this.items[idx].is_read && this.unread > 0) this.unread--;
          this.items.splice(idx, 1);
        }
        this.modal = null;
      },
    });
  });

  // Friend-request response (used by bell modal + friends page)
  window.respondFriendRequest = async function (frId, action, removeSelector) {
    try {
      const url = C.respondRequestUrlTmpl
        .replace('/0/', '/' + frId + '/').replace('ACTION', action);
      const res = await fetch(url, { method: 'POST', headers: { 'X-CSRFToken': window.lisaCsrf() } });
      const d = await res.json();
      if (!res.ok || !d.ok) { toast('Could not respond to request.', false); return; }
      toast(d.message || 'Done.', true);
      if (window.Alpine && Alpine.store('notif')) Alpine.store('notif').removeByRequest(frId);
      if (removeSelector) {
        if (action === 'accept') { location.reload(); return; }
        const el = document.querySelector(removeSelector);
        if (el) el.remove();
      }
    } catch (e) { toast('Network error.', false); }
  };

  // WebSocket: notifications + presence (auto-reconnect with backoff)
  let sock = null, backoff = 1000;
  function connect() {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    sock = new WebSocket(scheme + '://' + location.host + '/ws/notifications/');
    sock.onopen = () => { backoff = 1000; };
    sock.onmessage = (e) => {
      let msg; try { msg = JSON.parse(e.data); } catch (_) { return; }
      if (msg.type === 'notify' && msg.notification) {
        const store = window.Alpine && Alpine.store('notif');
        if (store) store.receive(msg.notification);
        playDing();
        toast(msg.notification.title, true);
      } else if (msg.type === 'presence') {
        setPresence(msg.user_id, !!msg.online);
      }
    };
    sock.onclose = () => {
      setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, 15000);
    };
    sock.onerror = () => { try { sock.close(); } catch (_) {} };
  }
  connect();
})();

// Alpine factory for the bell dropdown
window.notifBell = function () {
  const C = window.LISA_BELL || {};
  return {
    open: false,
    init() {
      fetch(C.feedUrl).then(r => r.json()).then(d => {
        const store = this.$store.notif;
        store.items = d.results || [];
        store.unread = d.unread || 0;
      }).catch(() => {});
    },
    toggle() { this.open = !this.open; },
    async markAllRead() {
      try {
        await fetch(C.markAllReadUrl, {
          method: 'POST', headers: { 'X-CSRFToken': window.lisaCsrf() },
        });
      } catch (e) {}
      this.$store.notif.unread = 0;
      this.$store.notif.items.forEach(n => n.is_read = true);
    },
    onItem(n) {
      if (n.kind === 'friend_request' && n.data && n.data.friend_request_id) {
        this.$store.notif.modal = { title: n.title, fr_id: n.data.friend_request_id };
        this.open = false;
        return;
      }
      if (!n.is_read) {
        n.is_read = true;
        if (this.$store.notif.unread > 0) this.$store.notif.unread--;
        fetch(C.markReadUrlTmpl.replace('/0/', '/' + n.id + '/'),
          { method: 'POST', headers: { 'X-CSRFToken': window.lisaCsrf() } }).catch(() => {});
      }
      if (n.url) window.location.href = n.url;
    },
  };
};
