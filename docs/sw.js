// サービスワーカー。HTML とデータは network-first（更新を取りこぼさない）、
// それ以外の静的アセットは cache-first。
// シェルを更新したら CACHE のバージョンを必ず上げること（古いキャッシュを破棄するため）。
const CACHE = "price-monitor-v9";
const SHELL = ["./", "index.html", "manifest.json", "icon-192.png", "icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// ネットワーク優先：取得できたらキャッシュを更新し、オフライン時のみキャッシュへ
function networkFirst(req) {
  return fetch(req)
    .then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => {});
      return res;
    })
    .catch(() => caches.match(req));
}

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  // ページ遷移(HTML)とデータは network-first（古い画面/価格を見せない）
  if (req.mode === "navigate" || url.pathname.endsWith("/") ||
      url.pathname.endsWith("index.html") || url.pathname.includes("/data/")) {
    e.respondWith(networkFirst(req));
    return;
  }
  // それ以外（アイコン等）は cache-first
  e.respondWith(caches.match(req).then((r) => r || fetch(req)));
});

