// Landing/home page: trending billboard + clickable row.
// Django-bound values come from window.LISA_LAND.
(function () {
  function csrf() {
    return document.cookie.match(/csrftoken=([^;]+)/)?.[1] || "";
  }

  window.home = function () {
    const C = window.LISA_LAND || {};
    return {
      isAuth: !!C.isAuth,
      trending: [], feat: {},
      async load() {
        try {
          const d = await (await fetch(C.trendingUrl)).json();
          this.trending = d.results || [];
          if (this.trending.length) this.feat = this.trending[0];
        } catch (e) {}
      },
      pick(m) {
        // In the library → rich DB modal. Otherwise open the live TMDb detail modal.
        if (m.in_library && m.library_id) { openMovie(m.library_id); }
        else if (window.openTmdb) { openTmdb(m.id, m.media_type); }
        else { this.request(m); }
      },
      async request(m) {
        if (!this.isAuth) { location.href = C.loginUrl; return; }
        try {
          const r = await (await fetch(C.requestUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf() },
            body: JSON.stringify({
              tmdb_id: m.id, media_type: m.media_type, title: m.title,
              year: m.year, poster: m.poster, overview: m.overview,
            }),
          })).json();
          if (r.in_library) { m.in_library = true; m.library_id = r.library_id; }
          else { m.request_status = r.status; m.vote_count = r.vote_count; m.voted = true; }
        } catch (e) {}
      },
    };
  };
})();
