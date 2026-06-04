// Create-party form: live-filtering library picker.
// Django URLs come from window.LISA_PARTIES_CREATE.
(function () {
  window.createForm = function () {
    const C = window.LISA_PARTIES_CREATE || {};
    return {
      movies: [], q: '', open: false, selected: null,
      async load() {
        try { this.movies = (await (await fetch(C.libraryUrl)).json()).results || []; } catch (e) {}
      },
      filtered() {
        const t = this.q.trim().toLowerCase();
        if (!t) return this.movies.slice(0, 30);
        return this.movies.filter(m => (m.title || '').toLowerCase().includes(t)).slice(0, 30);
      },
      choose(m) { this.selected = m; this.open = false; },
    };
  };
})();
