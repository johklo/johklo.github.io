/* 오프라인 실행용 서비스 워커
 *
 * 앱 셸은 미리 받아두고, 문제 데이터(bank/*.json, vault.enc)는 한 번 받으면 캐시에 남긴다.
 * 비행기 모드·지하철에서도 풀 수 있게 하는 것이 목적이다.
 */
const CACHE = 'studyvault-v1';
const SHELL = ['./', './index.html', './manifest.webmanifest', './favicon.svg'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET' || new URL(request.url).origin !== self.location.origin) return;

  const url = new URL(request.url);
  const isVault = /\/vault\.(enc|meta\.json)$/.test(url.pathname);

  // 문서·금고 파일은 네트워크 우선 — 재배포 시 앱과 데이터가 어긋나지 않게 한다.
  // 금고는 솔트·IV 와 암호문이 한 쌍이라 한쪽만 낡으면 복호화가 깨진다.
  if (request.mode === 'navigate' || isVault) {
    event.respondWith(
      fetch(request)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(request, copy));
          }
          return res;
        })
        .catch(() =>
          caches
            .match(request)
            .then((hit) => hit ?? (request.mode === 'navigate' ? caches.match('./index.html') : undefined)),
        ),
    );
    return;
  }

  // 나머지(자산·문제 데이터)는 캐시 우선
  event.respondWith(
    caches.match(request).then(
      (hit) =>
        hit ??
        fetch(request).then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(request, copy));
          }
          return res;
        }),
    ),
  );
});
