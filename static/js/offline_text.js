// 圏外のテキスト翻訳（v1.10.0）: まず翻訳メモリー（以前オンラインで訳した文）、なければ端末内の AI（日本語⇄英語）。
// 通常の画面では、圏外（navigator.onLine が false）のときだけ、「テキスト」の翻訳ボタンをここに切り替える。
const OfflineText = (function () {
    const JA = /[぀-ヿ㐀-鿿]/;
    const PAIRS = {
        'ja-en': { from: 'Japanese', to: 'English', tcode: 'en-US', sep: ' ' },
        'en-ja': { from: 'English', to: 'Japanese', tcode: 'ja-JP', sep: '' },
    };
    const PIECES = /.+?(?:[。！？!?]+|\.(?=\s|$)|$)\s*/g;     // offline_mt_worker.js の文の区切りと同じ

    // 翻訳先と文から、使える方向を決める（日本語⇄英語だけ。ほかは null）
    function pairFor(text, tgt) {
        if (tgt === 'English' && JA.test(text)) return 'ja-en';
        if (tgt === 'Japanese' && !JA.test(text)) return 'en-ja';
        return null;
    }

    // 1文ずつ: メモリー（同じ文）→ 端末内の AI。戻り: { out, mem: メモリーから出した文の数, ai: AI で訳した文の数 }
    async function byModel(text, pair) {
        const p = PAIRS[pair];
        let mem = 0, ai = 0;
        const lines = [];
        for (const line of text.split('\n')) {
            if (!line.trim()) { lines.push(''); continue; }
            const parts = [];
            for (const piece of (line.match(PIECES) || [line])) {
                const s = piece.trim();
                if (!s) continue;
                const hit = tmFind(s, p.to, true);
                if (hit) { parts.push(hit.out); mem++; continue; }
                parts.push(await OfflineMT.translate(pair, s)); ai++;
            }
            lines.push(parts.join(p.sep));
        }
        return { out: lines.join('\n'), mem, ai };
    }

    // text を訳す。戻り: { out, via: 'memory'|'similar'|'mixed'|'model', from? } か、{ error: 'nopair'|'nomodel'|'unsupported' }
    async function translate(text, tgt, pairHint) {
        text = String(text || '').trim();
        const hit = tmFind(text, tgt);
        if (hit) return { out: hit.out, via: hit.kind === 'exact' ? 'memory' : 'similar', from: hit.src };
        const pair = pairHint || pairFor(text, tgt);
        if (!pair) return { error: 'nopair' };
        if (typeof OfflineMT === 'undefined' || !OfflineMT.supported()) return { error: 'unsupported' };
        if (!(await OfflineMT.isDownloaded(pair).catch(() => false))) return { error: 'nomodel' };
        const r = await byModel(text, pair);
        return { out: r.out, via: !r.ai ? 'memory' : (r.mem ? 'mixed' : 'model'), pair };
    }

    function viaText(r) {
        if (r.via === 'similar') return UI.lo_via_similar.replace('{s}', r.from || '');
        return UI['lo_via_' + r.via] || '';
    }

    return { translate, pairFor, viaText, PAIRS };
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
        let r;
        try { r = await OfflineText.translate(text, TARGET_LANG); } catch (e) { r = { error: 'failed' }; }
        if (btn) btn.disabled = false;
        if (r.error) { msg.textContent = UI['lo_msg_' + r.error] || UI.lo_msg_failed; msg.classList.remove('hidden'); return; }
        $o('local-out').textContent = r.out;
        $o('local-via').textContent = OfflineText.viaText(r);
        card.classList.remove('hidden');
        addHistory({ mode: 'text', src: text, out: r.out, srcLang: '', tgt: TARGET_LANG, tcode: codeOf(TARGET_LANG), pron: '', offline: true });
    }, true);
    document.addEventListener('click', (ev) => {
        const b = ev.target.closest && ev.target.closest('[data-local]');
        if (!b) return;
        const text = $o('local-out').textContent;
        if (b.dataset.local === 'speak') speak(text, codeOf(TARGET_LANG));
        else if (navigator.clipboard) navigator.clipboard.writeText(text).catch(() => {});
    });
})();
