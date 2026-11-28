// 圏外のテキスト翻訳（v1.10.0、v1.11.0 で中国語・韓国語を追加）: まず翻訳メモリー（以前オンラインで訳した文）、なければ端末内の AI。
// 通常の画面では、圏外（navigator.onLine が false）のときだけ、「テキスト」の翻訳ボタンをここに切り替える。
const OfflineText = (function () {
    // 端末内の AI（Opus-MT）は「英語を軸にした」モデル。英語と他の言語の間は直接、他の言語どうしは英語を経由して訳す
    const LANG = {
        'Japanese': { code: 'ja' }, 'English': { code: 'en' }, 'Korean': { code: 'ko' },
        'Chinese (Simplified)': { code: 'zh', tok: '>>cmn_Hans<<' }, 'Chinese (Traditional)': { code: 'zh', tok: '>>cmn_Hant<<' },
    };
    const NAMES = Object.keys(LANG);
    const HAVE = ['ja-en', 'en-ja', 'zh-en', 'en-zh', 'ko-en'];          // 使えるモデル（英語 → 韓国語は、使えるモデルが見つかっていない）
    const KANA = /[\u3040-\u30ff]/, HANGUL = /[\u1100-\u11ff\uac00-\ud7af]/, HAN = /[\u3400-\u9fff]/, LATIN = /[A-Za-z]/;
    const PIECES = /.+?(?:[。！？!?]+|\.(?=\s|$)|$)\s*/g;     // offline_mt_worker.js の文の区切りと同じ

    // 訳す手順（モデルの並び）。使えない組み合わせは null。例: ja→zh = [ja-en, en-zh（>>cmn_Hans<<）]
    function route(from, to) {
        const f = LANG[from], t = LANG[to];
        if (!f || !t || f.code === t.code) return null;
        const leg = (a, b) => (HAVE.indexOf(a.code + '-' + b.code) >= 0 ? { pair: a.code + '-' + b.code, prefix: b.tok || '' } : null);
        const en = LANG.English;
        if (f.code === 'en' || t.code === 'en') { const one = leg(f, t); return one ? [one] : null; }
        const a = leg(f, en), b = leg(en, t);
        return a && b ? [a, b] : null;
    }

    // 文の文字から、言語を決める（かな→日本語、ハングル→韓国語、漢字だけ→preferHan、アルファベット→英語）。決められなければ null
    function detect(text, preferHan) {
        if (HANGUL.test(text)) return 'Korean';
        if (KANA.test(text)) return 'Japanese';
        if (HAN.test(text)) return preferHan || 'Chinese (Simplified)';
        return LATIN.test(text) ? 'English' : null;
    }

    const joiner = (to) => (LANG[to] && (LANG[to].code === 'ja' || LANG[to].code === 'zh') ? '' : ' ');

    // 1文ずつ: メモリー（同じ文）→ 端末内の AI（手順の順に、全文を1つのモデルで訳してから、次のモデルへ。モデルの入れ替えを減らす）
    async function byModel(text, steps, to) {
        const sentences = [];                               // 文: { s, out } 。改行は { nl: true }
        text.split('\n').forEach((line, i) => {
            if (i) sentences.push({ nl: true });
            for (const piece of (line.match(PIECES) || [line])) {
                const s = piece.trim();
                if (s) sentences.push({ s, out: '' });
            }
        });
        let mem = 0;
        const todo = [];
        for (const x of sentences) {
            if (x.nl) continue;
            const hit = tmFind(x.s, to, true);
            if (hit) { x.out = hit.out; mem++; } else todo.push(x);
        }
        for (const x of todo) x.cur = x.s;
        for (const st of steps) for (const x of todo) x.cur = await OfflineMT.translate(st.pair, x.cur, st.prefix);
        for (const x of todo) x.out = x.cur;
        const sep = joiner(to), lines = [[]];
        for (const x of sentences) { if (x.nl) lines.push([]); else lines[lines.length - 1].push(x.out); }
        return { out: lines.map((l) => l.join(sep)).join('\n'), mem, ai: todo.length };
    }

    // text を from → to に訳す。戻り: { out, via: 'memory'|'similar'|'mixed'|'model'|'pivot', from? } か、
    // { error: 'nopair'|'nomodel'|'unsupported', missing?: [使えていないモデル] }
    async function translate(text, to, from) {
        text = String(text || '').trim();
        const hit = tmFind(text, to);
        if (hit) return { out: hit.out, via: hit.kind === 'exact' ? 'memory' : 'similar', from: hit.src };
        const steps = from ? route(from, to) : null;
        if (!steps) return { error: 'nopair' };
        if (typeof OfflineMT === 'undefined' || !OfflineMT.supported()) return { error: 'unsupported' };
        const missing = [];
        for (const st of steps) if (!(await OfflineMT.isDownloaded(st.pair).catch(() => false))) missing.push(st.pair);
        if (missing.length) return { error: 'nomodel', missing };
        const r = await byModel(text, steps, to);
        return { out: r.out, via: !r.ai ? 'memory' : (r.mem ? 'mixed' : (steps.length > 1 ? 'pivot' : 'model')) };
    }

    function viaText(r) {
        if (r.via === 'similar') return UI.lo_via_similar.replace('{s}', r.from || '');
        return UI['lo_via_' + r.via] || '';
    }

    // 「足りないモデル: 中国語 → 英語、…」（設定のラベルと同じ名前）
    const missingText = (list) => (list && list.length ? ' ' + UI.ot_missing.replace('{m}', list.map((p) => UI['omt_' + p.replace('-', '_')] || p).join('、')) : '');

    return { translate, route, detect, viaText, missingText, NAMES, LANG, HAVE };
})();

// ---- 通常の画面の「テキスト」: 圏外のときだけ、サーバーに送らずここで訳す ----
(function () {
    const $o = (id) => document.getElementById(id);
    document.addEventListener('submit', async (ev) => {
        const form = ev.target;
        if (!form || !form.closest || !form.closest('#tab-text') || !$o('local-result') || navigator.onLine !== false) return;
        ev.preventDefault(); ev.stopImmediatePropagation();
        const ta = form.querySelector('textarea');
        const text = (ta ? ta.value : '').trim();
        const msg = $o('local-msg'), card = $o('local-result'), btn = form.querySelector('button[type=submit]');
        if (!text) return;
        msg.classList.add('hidden'); card.classList.add('hidden');
        if (btn) btn.disabled = true;
        // 入れた文の言語: 文字から決める。漢字だけのときは、翻訳元に選んである言語（日本語・中国語）、なければ、翻訳先と別のほう
        const chosen = (typeof SOURCE_CODE === 'string' && SOURCE_CODE) ? LANGS.find((l) => l.code === SOURCE_CODE) : null;
        const han = chosen && /^(Japanese|Chinese)/.test(chosen.name) ? chosen.name : (TARGET_LANG === 'Japanese' ? 'Chinese (Simplified)' : 'Japanese');
        const from = OfflineText.detect(text, han) || '';
        let r;
        try { r = await OfflineText.translate(text, TARGET_LANG, from); } catch (e) { r = { error: 'failed' }; }
        if (btn) btn.disabled = false;
        if (r.error) { msg.textContent = (UI['lo_msg_' + r.error] || UI.lo_msg_failed) + OfflineText.missingText(r.missing); msg.classList.remove('hidden'); return; }
        $o('local-out').textContent = r.out;
        $o('local-via').textContent = OfflineText.viaText(r);
        card.classList.remove('hidden');
        addHistory({ mode: 'text', src: text, out: r.out, srcLang: from, tgt: TARGET_LANG, tcode: codeOf(TARGET_LANG), pron: '', offline: true });
    }, true);
    document.addEventListener('click', (ev) => {
        const b = ev.target.closest && ev.target.closest('[data-local]');
        if (!b) return;
        const text = $o('local-out').textContent;
        if (b.dataset.local === 'speak') speak(text, codeOf(TARGET_LANG));
        else if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {});
    });
})();
