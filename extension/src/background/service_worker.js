/**
 * AEGIS Chrome MV3 service worker.
 *
 * Responsibilities:
 *   1. Match visited tab hostnames against the cached AI service catalogue.
 *   2. Enumerate installed extensions (chrome.management) and flag AI ones.
 *   3. Batch events and POST to the AEGIS API on a 30s flush cycle.
 *   4. Refresh the catalogue cache every 24h via chrome.alarms.
 *
 * Privacy: only hostname + timestamp are reported, never full URLs.
 */

const CONFIG = {
  apiUrl:           'http://localhost:8000/v1',  // overridden via storage settings
  catalogueRefresh: 24 * 60 * 60 * 1000,         // 24h
  flushIntervalMs:  30 * 1000,                   // 30s
  maxBatchSize:     100,
};

let domainMap = new Map();      // domain -> catalogue_id
let extensionMap = new Map();   // extension id -> catalogue_id
let eventBuffer = [];

// ---------- bootstrap ----------
chrome.runtime.onInstalled.addListener(async () => {
  await ensureSettings();
  await refreshCatalogue();
  await enumerateExtensions();
  chrome.alarms.create('flush',             { periodInMinutes: 0.5 });
  chrome.alarms.create('refresh_catalogue', { periodInMinutes: 60 * 24 });
  chrome.alarms.create('rescan_extensions', { periodInMinutes: 60 });
});

chrome.runtime.onStartup.addListener(async () => {
  await ensureSettings();
  await refreshCatalogue();
  await enumerateExtensions();
});

// ---------- helpers ----------
async function ensureSettings() {
  const stored = await chrome.storage.local.get(['aegisApiUrl', 'aegisApiKey', 'aegisDeviceId']);
  if (!stored.aegisDeviceId) {
    const deviceId = crypto.randomUUID();
    await chrome.storage.local.set({ aegisDeviceId: deviceId });
  }
  if (stored.aegisApiUrl) CONFIG.apiUrl = stored.aegisApiUrl;
}

async function refreshCatalogue() {
  try {
    const resp = await fetch(`${CONFIG.apiUrl}/extension/catalogue`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const { domains = {}, extensions = {} } = await resp.json();
    domainMap = new Map(Object.entries(domains));
    extensionMap = new Map(Object.entries(extensions));
    await chrome.storage.local.set({ aegisCatalogueAt: Date.now() });
  } catch (err) {
    // Fall back to an embedded minimal seed so the extension is useful pre-API.
    domainMap = new Map(Object.entries({
      'chat.openai.com':       'openai-chatgpt',
      'chatgpt.com':           'openai-chatgpt',
      'claude.ai':             'anthropic-claude',
      'gemini.google.com':     'google-gemini',
      'copilot.microsoft.com': 'microsoft-copilot',
      'www.perplexity.ai':     'perplexity',
      'poe.com':               'poe',
      'huggingface.co':        'huggingface',
    }));
    console.warn('[AEGIS] catalogue refresh failed — using embedded seed', err);
  }
}

async function enumerateExtensions() {
  try {
    const extensions = await chrome.management.getAll();
    const aiOnes = extensions
      .filter((e) => e.type === 'extension' && extensionMap.has(e.id))
      .map((e) => ({
        type:         'ai_extension_detected',
        catalogue_id: extensionMap.get(e.id),
        extension_id: e.id,
        name:         e.name,
        version:      e.version,
        enabled:      e.enabled,
        occurred_at:  new Date().toISOString(),
      }));
    eventBuffer.push(...aiOnes);
  } catch (err) {
    console.warn('[AEGIS] enumerateExtensions failed', err);
  }
}

// ---------- tab monitoring ----------
chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
  if (info.status !== 'complete' || !tab.url) return;
  try {
    const url = new URL(tab.url);
    const catalogueId = domainMap.get(url.hostname);
    if (!catalogueId) return;
    eventBuffer.push({
      type:         'ai_web_app_visit',
      catalogue_id: catalogueId,
      domain:       url.hostname,
      occurred_at:  new Date().toISOString(),
    });
    if (eventBuffer.length >= CONFIG.maxBatchSize) flushEvents();
  } catch {
    /* invalid URL — ignore */
  }
});

// ---------- alarms ----------
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'flush')             await flushEvents();
  else if (alarm.name === 'refresh_catalogue') await refreshCatalogue();
  else if (alarm.name === 'rescan_extensions') await enumerateExtensions();
});

async function flushEvents() {
  if (eventBuffer.length === 0) return;
  const batch = eventBuffer.splice(0, CONFIG.maxBatchSize);
  const { aegisApiKey, aegisDeviceId } = await chrome.storage.local.get(['aegisApiKey', 'aegisDeviceId']);
  try {
    await fetch(`${CONFIG.apiUrl}/extension/events`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(aegisApiKey ? { 'X-Ingest-Key': aegisApiKey } : {}),
      },
      body: JSON.stringify({ device_id: aegisDeviceId, events: batch }),
    });
  } catch (err) {
    // Re-queue on failure (head of buffer).
    eventBuffer = batch.concat(eventBuffer);
    console.warn('[AEGIS] flush failed, re-queued', err);
  }
}

// expose for popup
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === 'aegis.status') {
    sendResponse({
      bufferLength: eventBuffer.length,
      domains: domainMap.size,
      extensions: extensionMap.size,
    });
  }
  return true;
});
