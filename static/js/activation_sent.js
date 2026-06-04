// Resend-activation button: 90s cooldown then enable.
(function () {
  let countdown = 90;
  const countdownEl = document.getElementById('countdown');
  const button = document.getElementById('resend-btn');
  if (!countdownEl || !button) return;

  const timer = setInterval(() => {
    countdown--;
    countdownEl.textContent = countdown;
    if (countdown <= 0) {
      clearInterval(timer);
      button.removeAttribute('disabled');
      button.innerHTML = '<i class="fas fa-paper-plane mr-2"></i> Resend Activation Email';
      button.classList.remove('bg-gray-700', 'cursor-not-allowed', 'opacity-75');
      button.classList.add('bg-maroon', 'hover:bg-maroon/90');
    }
  }, 1000);
})();
