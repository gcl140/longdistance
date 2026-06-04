// Friend-search type-ahead. Mounted via x-data="friendSearch()".
// Django URLs come from window.LISA_FRIENDS (set by an inline shim).
(function () {
  window.friendSearch = function () {
    const C = window.LISA_FRIENDS || {};
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
})();
