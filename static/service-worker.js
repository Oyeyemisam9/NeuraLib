const APP_SHELL_CACHE = 'neuralib-cache-v1';
const MATERIALS_CACHE = 'neuralib-materials-v1';

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(APP_SHELL_CACHE).then(cache => {
      return cache.addAll([
        '/',
        '/static/manifest.json',
        // Add more static files if needed
      ]);
    })
  );
  self.skipWaiting();
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Material files (view/download) use a network-first strategy: always
  // try to get the latest copy, but if the network is unavailable, fall
  // back to whatever was cached the last time it was opened - that's what
  // makes "My Downloads" actually work offline.
  const isMaterialFile = /\/material\/\d+\/(view|download)$/.test(url.pathname);

  if (isMaterialFile) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          const responseClone = response.clone();
          caches.open(MATERIALS_CACHE).then(cache => cache.put(event.request, responseClone));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Everything else: normal cache-first fallback for the app shell.
  event.respondWith(
    caches.match(event.request).then(response => {
      return response || fetch(event.request);
    })
  );
});
