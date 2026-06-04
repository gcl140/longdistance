// Upload page: TMDb autofill panel.
// Django URLs come from window.LISA_UPLOAD.
(function () {
  window.uploadForm = function () {
    const C = window.LISA_UPLOAD || {};
    return {
      tmdbOpen: false, q: '', results: [], msg: '',
      async search() {
        this.msg = 'Searching…'; this.results = [];
        try {
          const d = await (await fetch(C.searchUrl + '?q=' + encodeURIComponent(this.q))).json();
          this.results = d.results || [];
          this.msg = d.error || (this.results.length ? '' : 'No results.');
        } catch (e) { this.msg = 'Search failed.'; }
      },
      pick(r) {
        this.$refs.title.value = r.title;
        this.$refs.year.value = r.year || '';
        this.$refs.tmdb.value = r.id || '';
        this.$refs.poster.value = r.poster || '';
        this.$refs.description.value = r.overview || '';
        this.tmdbOpen = false;
      },
    };
  };
})();
