const CACHE_NAME = "ffl-field-v1";
const SHELL = ["./", "index.html", "styles.css", "app.js"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))).then(() => self.clients.claim()));
});

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok && request.method === "GET") {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (_) {
    return (await caches.match(request)) || new Response(JSON.stringify({ error: "offline" }), { status: 503, headers: { "Content-Type": "application/json" } });
  }
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirst(event.request));
    return;
  }
  if (event.request.method !== "GET") return;
  event.respondWith(caches.match(event.request).then((cached) => cached || networkFirst(event.request)));
});
