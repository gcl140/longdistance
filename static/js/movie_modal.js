// Reusable movie-detail modal (Alpine factory).
// window.openMovie(id) loads a library movie; window.openTmdb(tid, mt) loads a TMDb-only title.
(function () {
  function csrf() {
    return document.cookie.match(/csrftoken=([^;]+)/)?.[1] || "";
  }

  window.movieModal = function () {
    const C = window.LISA_MODAL || {};
    return {
      show: false, loading: false, error: false, errMsg: '',
      lastId: null, lastTmdb: null, trailerOpen: false, d: {},

      async open(id) {
        if (id === undefined || id === null || id === '' || Number.isNaN(Number(id))) {
          console.warn('[movie modal] ignored openMovie with invalid id:', id, new Error().stack);
          return;
        }
        this.lastId = id; this.d = {}; this.error = false; this.errMsg = '';
        this.trailerOpen = false; this.loading = true; this.show = true;
        const url = C.detailUrlTmpl.replace('/0/', '/' + id + '/');
        try {
          const res = await fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' });
          if (!res.ok) throw new Error('HTTP ' + res.status + ' for ' + url);
          const ct = res.headers.get('content-type') || '';
          if (!ct.includes('application/json')) throw new Error('Non-JSON (login redirect?) for ' + url);
          this.d = await res.json();
        } catch (e) {
          this.errMsg = (e && e.message) ? e.message : String(e);
          console.error('[movie modal] detail load failed:', e);
          this.error = true;
        }
        this.loading = false;
      },

      async openTmdb(tid, mt) {
        if (tid === undefined || tid === null || tid === '' || Number.isNaN(Number(tid))) {
          console.warn('[movie modal] ignored openTmdb with invalid id:', tid);
          return;
        }
        this.lastTmdb = { id: tid, mt: mt || 'movie' }; this.lastId = null;
        this.d = {}; this.error = false; this.errMsg = '';
        this.trailerOpen = false; this.loading = true; this.show = true;
        const url = C.tmdbUrlTmpl.replace('/0/', '/' + tid + '/') + '?media_type=' + (mt || 'movie');
        try {
          const res = await fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' });
          if (!res.ok) throw new Error('HTTP ' + res.status + ' for ' + url);
          this.d = await res.json();
        } catch (e) {
          this.errMsg = (e && e.message) ? e.message : String(e);
          this.error = true;
        }
        this.loading = false;
      },

      async requestThis() {
        const d = this.d;
        if (!d.tmdb_id) return;
        d.request_status = 'pending';
        try {
          const res = await (await fetch(C.requestUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
            body: JSON.stringify({
              tmdb_id: d.tmdb_id, media_type: d.media_type, title: d.title,
              year: d.year, poster: d.poster, overview: d.overview,
            }),
          })).json();
          if (res.in_library) {
            d.in_library = true; d.library_id = res.library_id;
            d.id = res.library_id; d.playable = true;
          } else { d.request_status = res.status || 'pending'; }
        } catch (e) { d.request_status = null; }
      },

      retry() {
        if (this.lastTmdb) this.openTmdb(this.lastTmdb.id, this.lastTmdb.mt);
        else this.open(this.lastId);
      },
      watchUrl(id) { return C.watchUrlTmpl.replace('/0/', '/' + id + '/'); },
      roomUrl(code) { return C.roomUrlTmpl.replace('CODE', code); },
    };
  };
})();
