// Friend-search type-ahead + cancel-pending-request helper.
// Django URLs come from window.LISA_FRIENDS (set by an inline shim).
(function () {
  const C = window.LISA_FRIENDS || {};

  function csrf() {
    return document.cookie.match(/csrftoken=([^;]+)/)?.[1] || "";
  }
  function toast(text, ok) {
    if (window.Toastify) Toastify({
      text: text, duration: 4000, close: true, gravity: 'top', position: 'right',
      backgroundColor: ok === false ? '#E50914' : '#16a34a',
    }).showToast();
  }

  window.friendSearch = function () {
    return {
      q: '', results: [], msg: '', open: false, picked: null,
      async search() {
        this.picked = null;
        const q = this.q.trim();
        if (q.length < 2) { this.results = []; this.msg = ''; this.open = true; return; }
        try {
          const d = await (await fetch(C.searchUrl + '?q=' + encodeURIComponent(q))).json();
          this.results = d.results || [];
          this.msg = this.results.length ? '' : 'No matching users.';
          this.open = true;
        } catch (e) { this.msg = 'Search failed.'; }
      },
      pick(r) {
        this.picked = r;
        this.q = r.email;
        this.open = false;
      },
    };
  };

  // Withdraw a pending request the user sent. Hides the row on success.
  window.cancelFriendRequest = async function (frId, removeSelector) {
    if (!confirm('Cancel this request?')) return;
    try {
      const url = C.cancelUrlTmpl.replace('/0/', '/' + frId + '/');
      const res = await fetch(url, { method: 'POST', headers: { 'X-CSRFToken': csrf() } });
      const d = await res.json().catch(() => ({}));
      if (!res.ok || !d.ok) { toast('Could not cancel request.', false); return; }
      toast(d.message || 'Cancelled.', true);
      if (removeSelector) document.querySelector(removeSelector)?.remove();
    } catch (e) { toast('Network error.', false); }
  };
})();
