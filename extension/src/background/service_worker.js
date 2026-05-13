/**
 * AEGIS Chrome MV3 service worker.
 *
 * Lifecycle:
 *   onInstalled → ensureSettings → enroll → refreshCatalogue → enumerateExtensions
 *   onAlarm('flush')             → POST /v1/extension/events
 *   onAlarm('refresh_catalogue') → GET  /v1/extension/catalogue (if version changed)
 *   onAlarm('rescan_extensions') → enumerate AI browser extensions
 *
 * Privacy:
 *   - Only hostname and timestamp leave the device. Full URLs, query strings,
 *     and request bodies are never sent.
 *   - Device fingerprint is a random UUID generated on first install, NOT a
 *     hardware identifier.
 */

const DEFAULT_CONFIG = {
  apiUrl:           'http://localhost:8000/v1',
  flushIntervalMin: 0.5,           // 30s
  catalogueMin:    60 * 24,        // 24h
  rescanExtMin:    60,             // 1h
  maxBatchSize:    100,
};

let domainMap = new Map();
let extensionMap = new Map();
let eventBuffer = [];

// ---------- bootstrap ----------

chrome.runtime.onInstalled.addListener(async () => {
  await bootstrap('install');
});

chrome.runtime.onStartup.addListener(async () => {
  await bootstrap('startup');
});

async function bootstrap(reason) {
  await ensureSettings();
  try {
    await enrollIfNeeded();
    await refreshCatalogue(/*force*/ true);
    await enumerateExtensions();
  } catch (err) {
    console.warn('[AEGIS] bootstrap error', reason, err);
  }
  chrome.alarms.create('flush',             { periodInMinutes: DEFAULT_CONFIG.flushIntervalMin });
  chrome.alarms.create('refresh_catalogue', { periodInMinutes: DEFAULT_CONFIG.catalogueMin });
  chrome.alarms.create('rescan_extensions', { periodInMinutes: DEFAULT_CONFIG.rescanExtMin });
}

// ---------- settings ----------

async function getConfig() {
  const stored = await chrome.storage.local.get([
    'aegisApiUrl', 'aegisApiKey', 'aegisDeviceId',
    'aegisDeviceFingerprint', 'aegisTenantId', 'aegisCatalogueVersion',
  ]);
  return { ...DEFAULT_CONFIG, ...stored };
}

async function ensureSettings() {
  const cfg = await getConfig();
  if (!cfg.aegisDeviceFingerprint) {
    const fp = crypto.randomUUID();
    await chrome.storage.local.set({ aegisDeviceFingerprint: fp });
  }
}

async function enrollIfNeeded() {
  const cfg = await getConfig();
  if (cfg.aegisDeviceId) return;     // already enrolled
  if (!cfg.aegisTenantId || !cfg.aegisApiKey) {
    console.warn('[AEGIS] enrollment skipped — set aegisTenantId + aegisApiKey via the Options page.');
    return;
  }
  const resp = await fetch(`${cfg.aegisApiUrl}/extension/enroll?tenant_id=${cfg.aegisTenantId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Ingest-Key': cfg.aegisApiKey },
    body: JSON.stringify({
      device_fingerprint: cfg.aegisDeviceFingerprint,
      hostname: globalThis.navigator?.userAgentData?.platform || 'unknown',
      browser_version: navigator.userAgent,
      extension_version: chrome.runtime.getManifest().version,
      os_platform: (await chrome.runtime.getPlatformInfo()).os,
    }),
  });
  if (!resp.ok) {
    console.warn('[AEGIS] enroll failed', resp.status, await resp.text());
    return;
  }
  const { device_id, catalogue_version } = await resp.json();
  await chrome.storage.local.set({ aegisDeviceId: device_id, aegisCatalogueVersion: catalogue_version });
}

// ---------- catalogue ----------

async function refreshCatalogue(force = false) {
  const cfg = await getConfig();
  try {
    const resp = await fetch(`${cfg.aegisApiUrl}/extension/catalogue`, {
      headers: cfg.aegisApiKey ? { 'X-Ingest-Key': cfg.aegisApiKey } : {},
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const { version, domains = {}, extensions = {} } = await resp.json();
    if (!force && version === cfg.aegisCatalogueVersion) return;
    domainMap    = new Map(Object.entries(domains));
    extensionMap = new Map(Object.entries(extensions));
    await chrome.storage.local.set({ aegisCatalogueVersion: version, aegisCatalogueAt: Date.now() });
  } catch (err) {
    // Embedded fallback so the extension is functional even with no API.
    if (domainMap.size === 0) {
      domainMap = new Map(Object.entries({
        'chat.openai.com':       'openai-chatgpt',
        'chatgpt.com':           'openai-chatgpt',
        'claude.ai':             'anthropic-claude-sonnet',
        'gemini.google.com':     'google-gemini',
        'copilot.microsoft.com': 'microsoft-copilot',
        'www.perplexity.ai':     'perplexity',
        'huggingface.co':        'huggingface-hub',
        'sora.openai.com':       'openai-sora',
        'chat.mistral.ai':       'mistral',
        'grok.com':              'xai-grok',
      }));
    }
    console.warn('[AEGIS] catalogue refresh failed — using last known map', err);
  }
}

async function enumerateExtensions() {
  try {
    const extensions = await chrome.management.getAll();
    const matches = extensions
      .filter((e) => e.type === 'extension' && extensionMap.has(e.id))
      .map((e) => ({
        type: 'ai_extension_detected',
        catalogue_id: extensionMap.get(e.id),
        extension_id: e.id,
        occurred_at: new Date().toISOString(),
        extra: { name: e.name, version: e.version, enabled: e.enabled },
      }));
    eventBuffer.push(...matches);
  } catch (err) {
    console.warn('[AEGIS] enumerateExtensions failed', err);
  }
}

// ---------- tab monitoring ----------

chrome.tabs.onUpdated.addListener((_tabId, info, tab) => {
  if (info.status !== 'complete' || !tab.url) return;
  try {
    const url = new URL(tab.url);
    const catalogueId = domainMap.get(url.hostname.toLowerCase());
    if (!catalogueId) return;
    eventBuffer.push({
      type: 'ai_web_app_visit',
      catalogue_id: catalogueId,
      domain: url.hostname.toLowerCase(),
      occurred_at: new Date().toISOString(),
    });
    if (eventBuffer.length >= DEFAULT_CONFIG.maxBatchSize) flushEvents();
  } catch { /* invalid URL */ }
});

// ---------- alarms ----------

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if      (alarm.name === 'flush')             await flushEvents();
  else if (alarm.name === 'refresh_catalogue') await refreshCatalogue(false);
  else if (alarm.name === 'rescan_extensions') await enumerateExtensions();
});

// ---------- flush ----------

async function flushEvents() {
  if (eventBuffer.length === 0) return;
  const cfg = await getConfig();
  if (!cfg.aegisDeviceId || !cfg.aegisApiKey || !cfg.aegisTenantId) return;

  const batch = eventBuffer.splice(0, DEFAULT_CONFIG.maxBatchSize);
  try {
    const resp = await fetch(`${cfg.aegisApiUrl}/extension/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Ingest-Key': cfg.aegisApiKey },
      body: JSON.stringify({
        device_id: cfg.aegisDeviceId,
        tenant_id: cfg.aegisTenantId,
        events: batch,
      }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  } catch (err) {
    eventBuffer = batch.concat(eventBuffer);   // re-queue
    console.warn('[AEGIS] flush failed, re-queued', err);
  }
}

// ---------- content script bridge ----------

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === 'aegis.status') {
    (async () => {
      const cfg = await getConfig();
      sendResponse({
        bufferLength: eventBuffer.length,
        domains:    domainMap.size,
        extensions: extensionMap.size,
        enrolled:   !!cfg.aegisDeviceId,
        apiUrl:     cfg.aegisApiUrl,
      });
    })();
    return true;
  }
  if (msg?.type === 'aegis.ai_extension_dom_detected') {
    eventBuffer.push({
      type: 'ai_extension_dom_detected',
      catalogue_id: msg.catalogue_id,
      occurred_at: msg.occurred_at,
      extra: { url_host: msg.url_host, signature_id: msg.signature_id },
    });
  }
  return false;
});
