/* TOOKIE Service Worker — 版が変わるたびに新しいキャッシュを作り、古いものは消す */
const VERSION = {{ version|tojson }};
const CACHE = 'tookie-' + VERSION;
const MODE_CACHE = 'tookie-mode';        // スタート画面で選んだ接続モード（online / offline）。ページ側が書き込む
const MODE_URL = '/__net_mode';
const OFFLINE_URL = '/offline';
const OMT_CACHE = 'tookie-omt';          // オフライン翻訳（試作）の翻訳エンジン。版が変わっても消さない（モデルは 'transformers-cache'）
const OMT_HOST = 'cdn.jsdelivr.net';
const OMT_PATHS = ['/npm/@huggingface/transformers@', '/npm/onnxruntime-web@'];
const PRECACHE = {{ precache|tojson }};   // Tailwind・FontAwesome も static/vendor/ に同梱しているので、ここに入る（V13: 外部の読み込みはなくなった）

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const c = await caches.open(CACHE);
    // 1つ取れなくても全体を失敗させない
    await Promise.allSettled([OFFLINE_URL, ...PRECACHE].map((u) => c.add(new Request(u, { cache: 'reload' }))));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keep = [CACHE, MODE_CACHE, OMT_CACHE, 'transformers-cache'];   // 以前の外部ファイル用のキャッシュ（tookie-runtime-v1）は、ここで消える。オフライン翻訳のエンジンとモデルは残す
    for (const k of await caches.keys()) if (!keep.includes(k)) await caches.delete(k);
    await self.clients.claim();
  })());
});

async function netMode() {
  try {
    const hit = await (await caches.open(MODE_CACHE)).match(MODE_URL);
    return hit && (await hit.text()) === 'offline' ? 'offline' : 'online';
  } catch (e) { return 'online'; }
}

// 最新があれば取る（2.5秒まで）。取れなければ端末に保存してあるオフライン画面
async function offlinePage() {
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 2500);
    const res = await fetch(OFFLINE_URL, { signal: ctl.signal, credentials: 'same-origin' });
    clearTimeout(t);
    if (res && res.ok) { (await caches.open(CACHE)).put(OFFLINE_URL, res.clone()); return res; }
  } catch (e) {}
  const cached = await caches.match(OFFLINE_URL);
  return cached || new Response('Offline', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}

// 画面の読み込み。オンラインモードでは、通信できているかぎり何も差し替えない。
// ただし「/」を新しく開こうとして通信エラー（電波なし・機内モード）になったときだけは、ブラウザのエラーではなく、保存済みのオフライン画面を出す（v1.10.2）。
// オフラインモードのときは、「/」でオフライン画面を出し、通信に失敗した画面もオフライン画面にする
async function navigate(req) {
  const u = new URL(req.url);
  if ((await netMode()) !== 'offline') {
    if (req.method === 'GET' && u.origin === location.origin && u.pathname === '/') {
      try { return await fetch(req); } catch (e) { return offlinePage(); }
    }
    return fetch(req);
  }
  if (req.method === 'GET' && u.origin === location.origin && u.pathname === '/') return offlinePage();
  try {
    return await fetch(req);
  } catch (e) {
    return offlinePage();
  }
}

async function cacheFirst(req) {
  const hit = await caches.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res && res.ok) (await caches.open(CACHE)).put(req, res.clone());
  return res;
}

// 翻訳エンジン（ダウンロードのときに1回取得）: 保存があればそれを使い、なければ取りに行って保存する
async function engineCache(req) {
  const c = await caches.open(OMT_CACHE);
  const hit = await c.match(req);
  if (hit) return hit;
  const res = await fetch(req);
  if (res && res.ok) c.put(req, res.clone());
  return res;
}

async function networkFirstUpdate(req) {
  try {
    const res = await fetch(req);
    if (res && res.ok) (await caches.open(CACHE)).put(OFFLINE_URL, res.clone());
    return res;
  } catch (e) {
    const hit = await caches.match(OFFLINE_URL);
    if (hit) return hit;
    throw e;
  }
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.mode === 'navigate') {
    // /offline そのものを開いたときは最新を取りに行き、だめなら保存コピー
    const u = new URL(req.url);
    if (u.origin === location.origin && u.pathname === OFFLINE_URL && req.method === 'GET') {
      event.respondWith(networkFirstUpdate(req));
    } else {
      event.respondWith(navigate(req));
    }
    return;
  }
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin === location.origin) {
    if (url.pathname.startsWith('/static/')) event.respondWith(cacheFirst(req));
    else if (url.pathname === OFFLINE_URL) event.respondWith(networkFirstUpdate(req));
    return;   // API などはそのままネットワークへ
  }
  if (url.hostname === OMT_HOST && OMT_PATHS.some((p) => url.pathname.startsWith(p))) event.respondWith(engineCache(req));
});
