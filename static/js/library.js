// Library page: TMDb autocomplete + request flow + transcode poll.
// Django URLs and the seeded quota flag come from window.LISA_LIBRARY.
(function () {
  function csrf() {
    return document.cookie.match(/csrftoken=([^;]+)/)?.[1] || "";
  }
  function quotaToast(msg) {
    if (window.Toastify) Toastify({
      text: msg, backgroundColor: '#E50914', duration: 5000,
      gravity: 'top', position: 'right', close: true,
    }).showToast();
  }

  window.movieSearch = function () {
    const C = window.LISA_LIBRARY || {};
    return {
      q: '', page: 1, totalPages: 1, results: [], loading: false,
      open: false, msg: '', timer: null, poll: null,
      quotaBlocked: !!C.quotaBlocked,

      onType() { clearTimeout(this.timer); this.timer = setTimeout(() => this.run(true), 300); },

      async run(reset) {
        if (reset) { this.page = 1; this.results = []; }
        if (!this.q.trim()) { this.open = false; this.msg = ''; return; }
        this.loading = true; this.open = true;
        try {
          const d = await (await fetch(C.searchUrl + '?q=' + encodeURIComponent(this.q) + '&page=' + this.page)).json();
          this.totalPages = d.total_pages || 1;
          this.results = reset ? (d.results || []) : this.results.concat(d.results || []);
          this.msg = d.error || (this.results.length ? '' : 'No results.');
          if (d.quota) this.quotaBlocked = !!d.quota.blocked;
        } catch (e) { this.msg = 'Search failed.'; }
        this.loading = false;
        this.ensurePoll();
      },

      more() { if (this.page < this.totalPages) { this.page++; this.run(false); } },

      async requestMovie(r) {
        if (this.quotaBlocked && !r.request_status) {
          quotaToast('Server full — enough movie requests from you.');
          return;
        }
        r._submitting = true;
        try {
          const resp = await fetch(C.requestUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
            body: JSON.stringify({
              tmdb_id: r.id, media_type: r.media_type, title: r.title,
              year: r.year, poster: r.poster, overview: r.overview,
            }),
          });
          const res = await resp.json().catch(() => ({}));
          if (res.quota) this.quotaBlocked = !!res.quota.blocked;
          if (resp.status === 403 || res.error === 'quota_exceeded') {
            this.quotaBlocked = true;
            quotaToast(res.message || 'Server full.');
          } else if (res.in_library) {
            r.in_library = true; r.library_id = res.library_id;
          } else {
            r.request_status = res.status || 'pending';
            r.vote_count = res.vote_count;
            r.voted = true;
          }
        } catch (e) {}
        r._submitting = false;
        this.ensurePoll();
      },

      ensurePoll() {
        if (this.poll) return;
        this.poll = setInterval(() => this.refreshStates(), 6000);
      },
      async refreshStates() {
        const ids = this.results
          .filter(r => !r.in_library && (r.request_status === 'pending' || r.request_status === 'approved'))
          .map(r => r.id);
        if (!ids.length) { clearInterval(this.poll); this.poll = null; return; }
        try {
          const d = await (await fetch(C.stateUrl + '?ids=' + ids.join(','))).json();
          const states = d.states || {};
          this.results.forEach(r => {
            const s = states[r.id];
            if (!s) return;
            if (s.in_library) {
              r.in_library = true; r.library_id = s.library_id; r.playable = s.playable;
            } else if (s.request_status) {
              r.request_status = s.request_status;
            }
          });
        } catch (e) {}
      },
    };
  };

  // Reload the page when any background transcode finishes.
  (function () {
    const C = window.LISA_LIBRARY || {};
    const pending = document.querySelectorAll('[data-processing]');
    if (!pending.length || !C.statusUrlTmpl) return;
    const timer = setInterval(async () => {
      let anyStillProcessing = false;
      for (const el of pending) {
        const id = el.getAttribute('data-processing');
        try {
          const s = await (await fetch(C.statusUrlTmpl.replace('/0/', '/' + id + '/'))).json();
          if (s.status === 'processing') anyStillProcessing = true;
          else { clearInterval(timer); location.reload(); return; }
        } catch (e) { anyStillProcessing = true; }
      }
      if (!anyStillProcessing) { clearInterval(timer); location.reload(); }
    }, 5000);
  })();
})();
