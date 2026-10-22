/*
 * Deliberately conservative service worker.
 *
 * Its job is to make Madar installable and to survive a flaky connection —
 * NOT to serve stale application code. Two rules:
 *
 *   1. Navigations are network-first. A new deploy is picked up on the next
 *      load; the cached shell only appears when the network actually fails.
 *   2. Only Vite's content-hashed build assets are cached long-term. Their
 *      filenames change every build, so a stale file can never shadow a new
 *      one.
 *
 * API calls are never cached: attendance, payments and evaluations must always
 * be live, and caching authenticated responses risks showing one user data
 * fetched for another.
 */
const VERSION = "madar-v1";
const SHELL = `${VERSION}-shell`;
const ASSETS = `${VERSION}-assets`;
const OFFLINE_URL = "/";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL).then((c) => c.addAll([OFFLINE_URL, "/manifest.webmanifest"]))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k)),
      ))
      .then(() => self.clients.claim()),
  );
});

const isBuildAsset = (url) =>
  url.origin === self.location.origin && url.pathname.startsWith("/assets/");

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Never touch the API, media streams, or anything cross-origin.
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((res) => {
          // Cache only a healthy, same-origin page: never an error page or a redirect to somewhere else.
          if (res.ok && res.type === "basic" && !res.redirected) {
            const copy = res.clone();
            caches.open(SHELL).then((c) => c.put(OFFLINE_URL, copy)).catch(() => {});
          }
          return res;
        })
        .catch(() => caches.match(OFFLINE_URL).then((r) => r || Response.error())),
    );
    return;
  }

  if (isBuildAsset(url)) {
    event.respondWith(
      caches.match(request).then((hit) => hit || fetch(request).then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(ASSETS).then((c) => c.put(request, copy)).catch(() => {});
        }
        return res;
      })),
    );
  }
});
