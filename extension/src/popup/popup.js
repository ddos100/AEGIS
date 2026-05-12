// AEGIS popup — fetches live status from the background service worker.
chrome.runtime.sendMessage({ type: 'aegis.status' }, (status) => {
  if (!status) return;
  document.getElementById('buffer').textContent     = status.bufferLength ?? '—';
  document.getElementById('domains').textContent    = status.domains      ?? '—';
  document.getElementById('extensions').textContent = status.extensions   ?? '—';
});
