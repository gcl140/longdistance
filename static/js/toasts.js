// Renders Django flash messages as Toastify toasts. Messages are dropped
// onto window.LISA_MESSAGES by an inline shim in full_base.html.
(function () {
  const COLORS = {
    success: '#16a34a',
    error:   '#E50914',
    warning: '#f59e0b',
    info:    '#2563eb',
  };
  const msgs = window.LISA_MESSAGES || [];
  if (!msgs.length || !window.Toastify) return;
  msgs.forEach((m) => {
    Toastify({
      text: m.text,
      duration: 5000,
      close: true,
      gravity: 'top',
      position: 'right',
      backgroundColor: COLORS[m.tag] || COLORS.info,
    }).showToast();
  });
})();
