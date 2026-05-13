// AEGIS popup — live status from the background service worker.
chrome.runtime.sendMessage({ type: 'aegis.status' }, (status) => {
  if (!status) return;
  document.getElementById('buffer').textContent     = status.bufferLength ?? '—';
  document.getElementById('domains').textContent    = status.domains      ?? '—';
  document.getElementById('extensions').textContent = status.extensions   ?? '—';
  document.getElementById('apiUrl').textContent     = status.apiUrl       ?? '—';
  document.getElementById('enrolled').textContent   = status.enrolled ? 'Yes' : 'No';
  if (!status.enrolled) document.getElementById('dot').classList.add('off');
});

document.getElementById('optionsBtn').addEventListener('click', () => {
  chrome.runtime.openOptionsPage();
});
