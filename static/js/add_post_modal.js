// Add-post modal: attachment-type toggler + file-name preview.

// Called via inline onclick="toggleAttachment('image')" — must stay on window.
window.toggleAttachment = function (type) {
  document.getElementById('link-field').classList.add('hidden');
  document.getElementById('image-field').classList.add('hidden');
  document.getElementById('video-field').classList.add('hidden');
  document.getElementById('doc-field').classList.add('hidden');

  const fileUploadFields = document.getElementById('file-upload-fields');

  if (type === 'link') {
    document.getElementById('link-field').classList.toggle('hidden');
    fileUploadFields.classList.add('hidden');
  } else {
    fileUploadFields.classList.remove('hidden');
    document.getElementById(`${type}-field`).classList.toggle('hidden');
  }

  if (type !== 'image') {
    document.getElementById('image-upload').value = '';
    document.getElementById('image-filename').textContent = 'No file selected';
  }
  if (type !== 'video') {
    document.getElementById('video-upload').value = '';
    document.getElementById('video-filename').textContent = 'No file selected';
  }
  if (type !== 'doc') {
    document.getElementById('docs-upload').value = '';
    document.getElementById('docs-filename').textContent = 'No file selected';
  }
};

document.getElementById('image-upload')?.addEventListener('change', function (e) {
  const fileName = e.target.files[0]?.name || 'No file selected';
  document.getElementById('image-filename').textContent = fileName;
});
document.getElementById('video-upload')?.addEventListener('change', function (e) {
  const fileName = e.target.files[0]?.name || 'No file selected';
  document.getElementById('video-filename').textContent = fileName;
});
document.getElementById('docs-upload')?.addEventListener('change', function (e) {
  const fileName = e.target.files[0]?.name || 'No file selected';
  document.getElementById('docs-filename').textContent = fileName;
});
