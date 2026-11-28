// オフライン翻訳（試作）のワーカー。画面とは別のスレッドで動かし、翻訳中も画面が固まらないようにする。
// 翻訳エンジン（Transformers.js）は、最初の「ダウンロード」「翻訳」のときだけ読み込む。
// 使うのは、日本語⇄英語のモデル Opus-MT（量子化版）。1方向あたり約100MB。
const LIB = 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.5.2';
const MODELS = { 'ja-en': 'Xenova/opus-mt-ja-en', 'en-ja': 'Xenova/opus-mt-en-jap' };
let lib = null;
const pipes = {};
const post = (m) => self.postMessage(m);
const ms = (t) => Math.round(performance.now() - t) + 'ms';

async function getLib(id, offline) {
    if (!lib) {
        const t = performance.now();
        post({ id, type: 'log', text: '翻訳エンジンを読み込み中…' });
        lib = await import(LIB);
        lib.env.allowLocalModels = false;
        lib.env.useBrowserCache = true;
        try { lib.env.backends.onnx.wasm.numThreads = 1; } catch (e) { /* 設定できない版は、そのまま */ }
        post({ id, type: 'log', text: '翻訳エンジン: 読み込み完了 (' + ms(t) + ')' });
    }
    lib.env.allowRemoteModels = !offline;   // 圏外のときは、端末に保存したファイルだけを使う（通信を試みない）
    return lib;
}

async function load(id, pair, offline) {
    if (pipes[pair]) return pipes[pair];
    if (!MODELS[pair]) throw new Error('未対応の組み合わせ: ' + pair);
    const L = await getLib(id, offline);
    const t = performance.now();
    post({ id, type: 'log', text: 'モデルを準備中: ' + MODELS[pair] });
    pipes[pair] = await L.pipeline('translation', MODELS[pair], {
        dtype: 'q8',
        device: 'wasm',
        progress_callback: (p) => {
            if (p && p.file && typeof p.loaded === 'number' && p.total) post({ id, type: 'progress', file: p.file, loaded: p.loaded, total: p.total });
        },
    });
    post({ id, type: 'log', text: 'モデルの準備完了 (' + ms(t) + ')' });
    return pipes[pair];
}

// 1文ずつ訳す（Opus-MT は、短い文のほうが精度が出る）。行の区切りは残す
function pieces(line) {
    return line.match(/.+?(?:[。！？!?]+|\.(?=\s|$)|$)\s*/g) || [line];
}

async function translate(id, pair, text, offline) {
    const pipe = await load(id, pair, offline);
    const join = pair === 'en-ja' ? '' : ' ';
    const t = performance.now();
    const lines = [];
    for (const line of String(text).split('\n')) {
        if (!line.trim()) { lines.push(''); continue; }
        const out = [];
        for (const s of pieces(line)) {
            if (!s.trim()) continue;
            const r = await pipe(s.trim(), { max_new_tokens: 256 });
            out.push((r && r[0] && r[0].translation_text) || '');
        }
        lines.push(out.join(join).trim());
    }
    post({ id, type: 'log', text: '翻訳 (' + ms(t) + ')' });
    return lines.join('\n');
}

self.onmessage = async (e) => {
    const m = e.data || {};
    try {
        if (m.type === 'load') { await load(m.id, m.pair, m.offline); post({ id: m.id, type: 'done' }); }
        else if (m.type === 'translate') { post({ id: m.id, type: 'done', text: await translate(m.id, m.pair, m.text, m.offline) }); }
        else if (m.type === 'drop') { delete pipes[m.pair]; post({ id: m.id, type: 'done' }); }
    } catch (err) {
        post({ id: m.id, type: 'error', message: String((err && err.message) || err) });
    }
};
