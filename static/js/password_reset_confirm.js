// Show/hide password — called via inline onclick="togglePw(this)".
window.togglePw = function (btn) {
  const input = btn.parentElement.querySelector('input');
  const icon = btn.querySelector('i');
  const show = input.type === 'password';
  input.type = show ? 'text' : 'password';
  icon.classList.toggle('fa-eye', !show);
  icon.classList.toggle('fa-eye-slash', show);
  btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
};
