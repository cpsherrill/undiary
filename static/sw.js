/* Undiary service worker: install-grade. Static assets cache as they
   are seen; page navigations go to the network and fall back to the
   offline page. The offline capture queue is a later milestone. */

const CACHE = "undiary-v2";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.add("/offline"))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin === location.origin && url.pathname.startsWith("/static/")) {
    // Stale-while-revalidate: answer from cache for speed, refresh
    // behind, so even an unhashed asset can never fossilize.
    event.respondWith(
      caches.open(CACHE).then((cache) =>
        cache.match(request).then((hit) => {
          const refresh = fetch(request)
            .then((response) => {
              if (response.ok) cache.put(request, response.clone());
              return response;
            })
            .catch(() => hit);
          return hit || refresh;
        })
      )
    );
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/offline")));
  }
});
