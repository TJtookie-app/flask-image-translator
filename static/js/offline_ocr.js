// オフラインの文字認識（写真の文字を端末内で読む。v1.12.0 試作）。Tesseract.js 6.0.1（版を固定）を、ダウンロードのボタンを押したときだけ jsdelivr から取る。
// 認識データ（言語ごとに約5〜20MB）は、@tesseract.js-data の 4.0.0_best_int。エンジンと認識データは、sw.js が端末に保存する。写真は、端末の外に出ない。
const OfflineOCR = (function () {
    const BASE = 'https://cdn.jsdelivr.net/npm/';
    const LIB = BASE + 'tesseract.js@6.0.1/dist/tesseract.min.js';
    const dataPath = (code) => BASE + '@tesseract.js-data/' + code + '/4.0.0_best_int';
    // 画面の言語名 → 認識データの名前
    const CODE = {
        'Japanese': 'jpn', 'English': 'eng', 'Chinese (Simplified)': 'chi_sim', 'Chinese (Traditional)': 'chi_tra', 'Korean': 'kor',
        'Spanish': 'spa', 'French': 'fra', 'German': 'deu', 'Italian': 'ita', 'Russian': 'rus', 'Indonesian': 'ind',
    };
    // 言語パックごとに入れる認識データ（英語は、どのパックにも入る。小さい）
    const PACK = { ja: ['jpn', 'eng'], zh: ['chi_sim', 'chi_tra', 'eng'], ko: ['kor', 'eng'], es: ['spa', 'eng'], fr: ['fra', 'eng'], de: ['deu', 'eng'], it: ['ita', 'eng'], ru: ['rus', 'eng'], id: ['ind', 'eng'] };
    const KEY = 'tl_ocr_v1';       // 入れ終えた認識データ: { jpn: 1, ... }（端末のこのブラウザの中だけ）
    const MAXSIDE = 1800;          // 大きすぎる写真は、この長さまで縮める（速さとメモリーのため）
    let loading = null;

    const flags = () => { try { return JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { return {}; } };
    const setFlag = (code, on) => {
        const f = flags(); if (on) f[code] = 1; else delete f[code];
        try { localStorage.setItem(KEY, JSON.stringify(f)); } catch (e) { /* 保存できなくても、使えなくなるだけ */ }
    };
    const supported = () => typeof Worker !== 'undefined' && typeof WebAssembly === 'object';
    const codeFor = (name) => CODE[name] || '';
    const isDownloaded = (code) => !!flags()[code];
    const packReady = (pk) => (PACK[pk] || []).every(isDownloaded);

    function loadLib() {
        if (window.Tesseract) return Promise.resolve(window.Tesseract);
        if (!loading) {
            loading = new Promise((ok, ng) => {
                const s = document.createElement('script');
                s.src = LIB;
                s.onload = () => (window.Tesseract ? ok(window.Tesseract) : ng(new Error('Tesseract not found')));
                s.onerror = () => { loading = null; ng(new Error('engine load failed')); };
                document.head.appendChild(s);
            });
        }
        return loading;
    }

    async function make(code, onRatio) {
        const T = await loadLib();
        return T.createWorker(code, 1, {
            langPath: dataPath(code),
            logger: (m) => { if (onRatio && m && typeof m.progress === 'number') onRatio(m.progress); },
        });
    }

    // 認識データを入れる（認識の準備まで行う。入れ終えたら印を付ける）
    async function download(code, onRatio) {
        const w = await make(code, onRatio);
        try { await w.terminate(); } catch (e) { /* 閉じられなくても続ける */ }
        setFlag(code, true);
    }

    function remove(codes) { codes.forEach((c) => setFlag(c, false)); }

    // 写真（File）を、長いほうが MAXSIDE の canvas にする（img で読むので、写真の向きの情報も反映される）
    function toCanvas(file) {
        return new Promise((ok, ng) => {
            const url = URL.createObjectURL(file), img = new Image();
            img.onload = () => {
                const k = Math.min(1, MAXSIDE / Math.max(img.naturalWidth, img.naturalHeight));
                const c = document.createElement('canvas');
                c.width = Math.max(1, Math.round(img.naturalWidth * k)); c.height = Math.max(1, Math.round(img.naturalHeight * k));
                const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height); g.drawImage(img, 0, 0, c.width, c.height);
                URL.revokeObjectURL(url); ok(c);
            };
            img.onerror = () => { URL.revokeObjectURL(url); ng(new Error('image load failed')); };
            img.src = url;
        });
    }

    // 日本語・中国語は、認識結果の文字の間に入る空白を取る（ハングル・アルファベットは、単語の区切りなので残す）
    const CJK = '\\u3000-\\u9fff\\uff00-\\uffef';
    function clean(text) {
        const t = String(text || '').replace(/\r/g, '').replace(new RegExp('([' + CJK + ']) +(?=[' + CJK + '])', 'g'), '$1');
        return t.split('\n').map((l) => l.trim()).filter(Boolean).join('\n');
    }

    async function recognize(file, code) {
        const canvas = await toCanvas(file);
        const w = await make(code);
        try { const r = await w.recognize(canvas); return clean(r && r.data && r.data.text); }
        finally { try { await w.terminate(); } catch (e) { /* 閉じられなくても続ける */ } }
    }

    return { supported, codeFor, isDownloaded, packReady, download, remove, recognize, clean, PACK, CODE, dataPath, LIB };
})();
