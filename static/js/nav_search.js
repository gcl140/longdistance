// Global nav search — Alpine factory mounted in full_base.html.
// Reads URLs from window.LISA (set by an inline bootstrap so {% url %} stays
// in the template) and the seed quotaBlocked from a data attribute.
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

  window.navSearch = function () {
    const C = window.LISA || {};
    return {
      open: false, q: '', page: 1, totalPages: 1, results: [],
      loading: false, msg: '', timer: null, poll: null,
      quotaBlocked: !!C.quotaBlocked,

      toggle() {
        this.open = !this.open;
        if (this.open) this.$nextTick(() => this.$refs.input && this.$refs.input.focus());
      },
      onType() {
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.run(true), 300);
      },
      async run(reset) {
        if (reset) { this.page = 1; this.results = []; }
        if (!this.q.trim()) { this.msg = ''; this.results = []; return; }
        this.loading = true;
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

      // Flip pending/approved requests to "Watch" once fulfilled, in the background.
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
})();
