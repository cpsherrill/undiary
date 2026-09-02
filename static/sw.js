/* Undiary service worker. Static assets cache as they are seen. Page
   navigations race the network against a short timer: a warm server
   wins invisibly; a cold start serves the branded loading shell,
   which fetches the real page and becomes it. */

const CACHE = "undiary-v3";
const COLD_MS = 450;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.add("/loading"))
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
    event.respondWith(
      (() => {
        const network = fetch(request);
        const timer = new Promise((resolve) =>
          setTimeout(() => resolve(null), COLD_MS)
        );
        return Promise.race([network.catch(() => null), timer]).then(
          (response) =>
            response ||
            caches.match("/loading").then((shell) => shell || network)
        );
      })()
    );
  }
});
