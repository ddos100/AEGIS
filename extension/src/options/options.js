// AEGIS Options page — read/write storage settings, then trigger re-enrollment.

const el = (id) => document.getElementById(id);

async function load() {
  const cfg = await chrome.storage.local.get(['aegisApiUrl', 'aegisTenantId', 'aegisApiKey']);
  el('apiUrl').value   = cfg.aegisApiUrl   || 'http://localhost:8000/v1';
  el('tenantId').value = cfg.aegisTenantId || '';
  el('apiKey').value   = cfg.aegisApiKey   || '';
}

async function save() {
  const status = el('status');
  status.className = '';
  status.textContent = 'Saving…';
  try {
    await chrome.storage.local.set({
      aegisApiUrl:   el('apiUrl').value.trim().replace(/\/$/, ''),
      aegisTenantId: el('tenantId').value.trim(),
      aegisApiKey:   el('apiKey').value.trim(),
      // Reset device_id so the service worker re-enrolls with the new credentials.
      aegisDeviceId: null,
    });
    status.textContent = 'Saved. The extension will re-enroll on the next event cycle.';
  } catch (err) {
    status.className = 'error';
    status.textContent = `Failed: ${err}`;
  }
}

document.addEventListener('DOMContentLoaded', load);
document.getElementById('save').addEventListener('click', save);
