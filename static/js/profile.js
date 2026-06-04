// Live preview of the chosen profile picture before upload.
document.getElementById('id_profile_picture')?.addEventListener('change', function (e) {
  const f = e.target.files[0]; if (!f) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    const img = document.getElementById('pic-preview');
    const letter = document.getElementById('pic-preview-letter');
    if (img) img.src = ev.target.result;
    else if (letter) {
      const wrap = letter.parentElement;
      wrap.innerHTML = `<img id="pic-preview" src="${ev.target.result}" class="w-full h-full object-cover">`;
    }
  };
  reader.readAsDataURL(f);
});
