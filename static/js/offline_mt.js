// オフライン翻訳（試作）: 画面側の入り口。重い処理は offline_mt_worker.js（別スレッド）で行う
const OfflineMT = (function () {
    const WORKER_URL = (document.currentScript && document.currentScript.src || '').replace('offline_mt.js', 'offline_mt_worker.js');
    const MODELS = {
        'ja-en': 'Xenova/opus-mt-ja-en', 'en-ja': 'Xenova/opus-mt-en-jap',
        'zh-en': 'Xenova/opus-mt-zh-en', 'en-zh': 'Xenova/opus-mt-en-zh', 'ko-en': 'Xenova/opus-mt-ko-en',
    };
    const NEED = ['encoder_model_quantized.onnx', 'decoder_model_merged_quantized.onnx'];   // 保存されていれば「ダウンロード済み」
    let worker = null, seq = 0, onLog = null, lastErr = '';
    const waits = new Map();
    const logs = [];

    function log(text) {
        const d = new Date();
        const p = (n) => String(n).padStart(2, '0');
        logs.push(p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds()) + ' ' + text);
        if (logs.length > 80) logs.shift();
        if (onLog) onLog(logs.slice());
    }

    function supported() {
        return typeof Worker !== 'undefined' && typeof WebAssembly === 'object' && 'caches' in window && !!WORKER_URL;
    }

    function failAll(message) {
        waits.forEach((w) => w.rej(new Error(message)));
        waits.clear();
        worker = null;   // 次の呼び出しで作り直す
    }

    function ensureWorker() {
        if (worker) return worker;
        worker = new Worker(WORKER_URL, { type: 'module' });
        worker.onmessage = (e) => {
            const m = e.data || {};
            if (m.type === 'log') { log(m.text); return; }
            const w = waits.get(m.id);
            if (!w) return;
            if (m.type === 'progress') { if (w.onProgress) w.onProgress(m); return; }
            waits.delete(m.id);
            if (m.type === 'error') { lastErr = m.message; log('エラー: ' + m.message); w.rej(new Error(m.message)); }
            else w.res(m);
        };
        worker.onerror = (e) => {
            const msg = (e && e.message) || 'ワーカーを開始できませんでした';
            lastErr = msg; log('ワーカーのエラー: ' + msg); failAll(msg);
        };
        return worker;
    }

    function call(type, payload, onProgress) {
        return new Promise((res, rej) => {
            const id = ++seq;
            waits.set(id, { res, rej, onProgress });
            try { ensureWorker().postMessage(Object.assign({ id, type, offline: navigator.onLine === false }, payload)); }
            catch (e) { waits.delete(id); rej(e); }
        });
    }

    // 端末に保存されたモデルのファイル（Transformers.js が Cache API に入れる）を、キャッシュ全体から探す
    async function stored(pair) {
        const found = [];
        if (!('caches' in window)) return found;
        for (const name of await caches.keys()) {
            if (name.startsWith('tookie-')) continue;
            const c = await caches.open(name);
            for (const req of await c.keys()) {
                if (req.url.includes('/' + MODELS[pair] + '/')) found.push({ cache: name, req });
            }
        }
        return found;
    }

    async function isDownloaded(pair) {
        const urls = (await stored(pair)).map((f) => f.req.url);
        return NEED.every((n) => urls.some((u) => u.endsWith(n)));
    }

    // 進み具合は、ファイルごとの値を足し合わせて、全体の割合（0〜1）にする
    async function download(pair, onRatio) {
        const files = {};
        const t = performance.now();
        log('ダウンロード開始: ' + pair);
        try {
            if (navigator.storage && navigator.storage.persist) {
                log('保存の保護を依頼: ' + ((await navigator.storage.persist()) ? '許可' : '許可されず（容量不足のとき消えることがあります）'));
            }
        } catch (e) { /* 依頼できない端末は、そのまま */ }
        await call('load', { pair }, (p) => {
            files[p.file] = { loaded: p.loaded, total: p.total };
            let l = 0, tt = 0;
            for (const k in files) { l += files[k].loaded; tt += files[k].total; }
            if (onRatio && tt) onRatio(Math.min(1, l / tt));
        });
        log('ダウンロード完了: ' + pair + ' (' + Math.round((performance.now() - t) / 1000) + '秒)');
    }

    async function translate(pair, text, prefix) { return (await call('translate', { pair, text, prefix: prefix || '' })).text; }

    async function remove(pair) {
        await call('drop', { pair }).catch(() => {});
        for (const f of await stored(pair)) await (await caches.open(f.cache)).delete(f.req);
        log('削除しました: ' + pair);
    }

    // うまくいかないときに、そのまま送ってもらえる環境の情報
    async function envText() {
        const out = ['UA: ' + navigator.userAgent.replace(/\s+/g, ' ').slice(0, 140), 'online: ' + navigator.onLine,
            'Worker/WASM/caches: ' + [typeof Worker !== 'undefined', typeof WebAssembly === 'object', 'caches' in window].join('/')];
        try {
            const e = await navigator.storage.estimate();
            out.push('storage: ' + Math.round((e.usage || 0) / 1048576) + 'MB / ' + Math.round((e.quota || 0) / 1048576) + 'MB');
            out.push('persisted: ' + (await navigator.storage.persisted()));
        } catch (e) { out.push('storage: 不明'); }
        if (lastErr) out.push('last error: ' + lastErr);
        return out.join('\n');
    }

    return { supported, isDownloaded, PAIRS: Object.keys(MODELS), download, translate, remove, envText, setLogger(fn) { onLog = fn; fn(logs.slice()); } };
})();
