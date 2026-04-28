// Offscreen document — relays fetch calls that are blocked by CORS in the service worker.
// The service worker sends { type: "OFFSCREEN_FETCH", url, requestId } and this responds with
// { type: "OFFSCREEN_FETCH_RESULT", requestId, html, status }.

chrome.runtime.onMessage.addListener(
  (msg: { type: string; url?: string; requestId?: string }, _sender, sendResponse) => {
    if (msg.type !== "OFFSCREEN_FETCH" || !msg.url || !msg.requestId) return;

    const { url, requestId } = msg;

    fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
      },
    })
      .then(async (res) => {
        const html = res.ok ? await res.text() : "";
        sendResponse({ requestId, html, status: res.status });
      })
      .catch(() => {
        sendResponse({ requestId, html: "", status: 0 });
      });

    return true; // keep channel open for async sendResponse
  },
);
