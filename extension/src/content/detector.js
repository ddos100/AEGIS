/**
 * AEGIS content script — detects AI browser extensions by DOM injection signatures.
 *
 * AI extensions typically inject identifiable DOM nodes (shadow roots, classes,
 * data attributes). We scan for known signatures both on initial load and via
 * MutationObserver to catch late injections.
 */

const SIGNATURES = [
  { id: 'grammarly',  selector: '[data-grammarly-shadow-root]',           catalogue_id: 'grammarly' },
  { id: 'compose_ai', selector: '.compose-ai-btn, [data-compose-ai]',     catalogue_id: 'compose-ai' },
  { id: 'sider',      selector: '#sider-extension-root',                  catalogue_id: 'sider' },
  { id: 'monica',     selector: '#monica-extension-host, .monica-ai',     catalogue_id: 'monica' },
  { id: 'merlin',     selector: '#merlin-extension-root',                 catalogue_id: 'merlin' },
  { id: 'jasper',     selector: '.jasper-extension-root',                 catalogue_id: 'jasper' },
];

const seen = new Set();

function scan() {
  for (const sig of SIGNATURES) {
    if (seen.has(sig.id)) continue;
    if (document.querySelector(sig.selector)) {
      seen.add(sig.id);
      chrome.runtime.sendMessage({
        type: 'aegis.ai_extension_dom_detected',
        catalogue_id: sig.catalogue_id,
        signature_id: sig.id,
        url_host: location.host,
        occurred_at: new Date().toISOString(),
      }).catch(() => { /* extension context invalidated — ignore */ });
    }
  }
}

scan();
const observer = new MutationObserver(scan);
observer.observe(document.documentElement, { childList: true, subtree: true });
// Stop observing after 30s — extensions that inject later are rare and we don't want overhead.
setTimeout(() => observer.disconnect(), 30_000);
