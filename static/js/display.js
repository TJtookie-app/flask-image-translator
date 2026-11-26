// 大きく表示（相手に見せる）と「別の言い方」
let bigEl = null;

function fitBigText(box, text) {
    let lo = 16, hi = 240;
    const room = box.clientHeight || window.innerHeight * 0.6;
    while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        text.style.fontSize = mid + 'px';
        if (text.scrollHeight <= room && text.scrollWidth <= box.clientWidth + 1) lo = mid; else hi = mid - 1;
    }
    text.style.fontSize = lo + 'px';
}

function closeBig() {
    if (bigEl) { bigEl.remove(); bigEl = null; }
    document.removeEventListener('keydown', bigKey);
}
function bigKey(ev) { if (ev.key === 'Escape') closeBig(); }

function showBig(text, pron, dir) {
    if (!text) return;
    closeBig();
    const ov = document.createElement('div');
    ov.className = 'big-overlay';
    ov.setAttribute('role', 'dialog');
    ov.addEventListener('click', closeBig);

    const x = document.createElement('button');
    x.type = 'button';
    x.className = 'big-close';
    x.setAttribute('aria-label', UI.big_close);
    x.textContent = '✕';
    x.addEventListener('click', ev => { ev.stopPropagation(); closeBig(); });

    const box = document.createElement('div');
    box.className = 'big-box';
    const t = document.createElement('div');
    t.className = 'big-text';
    t.dir = dir || 'auto';
    t.textContent = text;
    box.appendChild(t);
    ov.append(x, box);
    if (pron) {
        const p = document.createElement('div');
        p.className = 'big-pron';
        p.dir = 'auto';
        p.textContent = pron;
        ov.appendChild(p);
    }
    document.body.appendChild(ov);
    bigEl = ov;
    document.addEventListener('keydown', bigKey);
    fitBigText(box, t);
}

function showBigResult(mode) {
    const el = $('resultText-' + mode);
    if (!el) return;
    const pr = $('pron-' + mode);
    showBig(el.innerText, pr && !pr.classList.contains('hidden') ? pr.innerText : '', 'auto');
}

// ---- 別の言い方 ----
async function showAlternatives(mode, btn) {
    if (typeof hideAssistBoxes === 'function') hideAssistBoxes(mode);
    const box = $('alts-' + mode), el = $('resultText-' + mode);
    if (!box || !el || !RESULT) return;
    const icon = btn && btn.querySelector('i');
    box.classList.remove('hidden');
    box.replaceChildren();
    const note = document.createElement('p');
    note.className = 'text-xs text-slate-400';
    note.textContent = UI.alts_loading;
    box.appendChild(note);
    if (btn) btn.disabled = true;
    try {
        const r = await fetch('/api/alternatives', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: RESULT.src || RESULT.out,
                translation: el.innerText,
                source: langByName(RESULT.srcLang) ? RESULT.srcLang : 'Auto',
                target: RESULT.tgt,
                formality: loadSettings().formality,
            }),
        });
        let data = {};
        try { data = await r.json(); } catch (e) {}
        if (!r.ok || !data.alternatives) throw new Error(data.error || UI.err_failed);
        const label = document.createElement('p');
        label.className = 'text-xs font-semibold text-slate-400';
        label.textContent = UI.alts_label;
        box.replaceChildren(label);
        data.alternatives.forEach(alt => {
            const b = document.createElement('button');
            b.type = 'button';
            b.dir = 'auto';
            b.className = 'alt-chip w-full text-left text-sm px-3 py-2 rounded-xl border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-slate-100 whitespace-pre-wrap transition';
            b.textContent = alt;
            b.addEventListener('click', () => useAlternative(mode, alt));
            box.appendChild(b);
        });
    } catch (e) {
        note.textContent = e instanceof TypeError ? UI.err_network : (e.message || UI.err_failed);
        note.className = 'text-xs text-red-300';
        box.replaceChildren(note);
    } finally {
        if (btn) btn.disabled = false;
    }
}

// 訳を、選んだ言い方に置き換える（読み方は、新しい訳に合わないので消す）。履歴も同じ内容にする
function useAlternative(mode, alt) {
    const el = $('resultText-' + mode);
    if (!el || !RESULT) return;
    el.textContent = alt;
    RESULT.out = alt;
    RESULT.pron = '';
    const pr = $('pron-' + mode);
    if (pr) { pr.textContent = ''; pr.classList.add('hidden'); }
    if (currentEntryId) updateHistory(currentEntryId, x => { x.out = alt; x.pron = ''; });
    ['alts-', 'tones-'].forEach(p => { const b = $(p + mode); if (b) b.classList.add('hidden'); });
}

// ---- 口調を変える: 1回の呼び出しで、丁寧・標準・くだけたの3つを受け取り、選んだものに置き換える ----
async function showTones(mode, btn) {
    if (typeof hideAssistBoxes === 'function') hideAssistBoxes(mode);
    const box = $('tones-' + mode), el = $('resultText-' + mode);
    if (!box || !el || !RESULT) return;
    const alts = $('alts-' + mode);
    if (alts) alts.classList.add('hidden');
    box.classList.remove('hidden');
    box.replaceChildren();
    const note = document.createElement('p');
    note.className = 'text-xs text-slate-400';
    note.textContent = UI.alts_loading;
    box.appendChild(note);
    if (btn) btn.disabled = true;
    try {
        const r = await fetch('/api/tones', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: RESULT.src || RESULT.out,
                translation: el.innerText,
                source: langByName(RESULT.srcLang) ? RESULT.srcLang : 'Auto',
                target: RESULT.tgt,
            }),
        });
        let data = {};
        try { data = await r.json(); } catch (e) {}
        if (!r.ok || !data.tones) throw new Error(data.error || UI.err_failed);
        const label = document.createElement('p');
        label.className = 'text-xs font-semibold text-slate-400';
        label.textContent = UI.tone_label;
        box.replaceChildren(label);
        [['formal', UI.formality_formal], ['neutral', UI.tone_neutral], ['casual', UI.formality_casual]].forEach(([k, name]) => {
            const text = data.tones[k];
            if (!text) return;
            const b = document.createElement('button');
            b.type = 'button';
            b.className = 'tone-chip w-full text-left text-sm px-3 py-2 rounded-xl border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-slate-100 transition';
            const tag = document.createElement('span');
            tag.className = 'block text-xs font-semibold text-indigo-300 mb-0.5';
            tag.textContent = name;
            const body = document.createElement('span');
            body.dir = 'auto';
            body.className = 'block whitespace-pre-wrap';
            body.textContent = text;
            b.append(tag, body);
            b.addEventListener('click', () => useAlternative(mode, text));
            box.appendChild(b);
        });
    } catch (e) {
        note.textContent = e instanceof TypeError ? UI.err_network : (e.message || UI.err_failed);
        note.className = 'text-xs text-red-300';
        box.replaceChildren(note);
    } finally {
        if (btn) btn.disabled = false;
    }
}

// ---- 要約（長文のときだけボタンが出る。押したときだけ API を呼ぶ）----
async function summarizeResult(mode, btn) {
    const box = $('summary-' + mode);
    if (!box || !RESULT) return;
    box.classList.remove('hidden');
    box.textContent = UI.alts_loading;
    if (btn) btn.disabled = true;
    try {
        const r = await fetch('/api/summarize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: RESULT.src || '' }),
        });
        let data = {};
        try { data = await r.json(); } catch (e) {}
        if (!r.ok || !data.summary) throw new Error(data.error || UI.err_failed);
        const label = document.createElement('p');
        label.className = 'text-xs font-semibold text-indigo-300 mb-1';
        label.textContent = UI.summary_label;
        const body = document.createElement('div');
        body.textContent = data.summary;
        box.replaceChildren(label, body);
    } catch (e) {
        box.textContent = e instanceof TypeError ? UI.err_network : (e.message || UI.err_failed);
        box.classList.add('text-red-300');
    } finally {
        if (btn) btn.disabled = false;
    }
}

// ---- 結果の「🌐 言語」バッジ: 「Español（スペイン語）」のように、その言語自身の名前＋いまの画面の言語での名前にする ----
function intlTag(code) {
    code = String(code || '');
    if (code === 'zh-CN' || code === 'zh-SG') return 'zh-Hans';
    if (code === 'zh-TW' || code === 'zh-HK') return 'zh-Hant';
    const p = code.split('-')[0];
    return p === 'nb' ? 'no' : p;
}

function localizeLangBadges() {
    let names = null;
    try { names = new Intl.DisplayNames([intlTag(codeOf(UI_LANG)) || 'en'], { type: 'language' }); } catch (e) { return; }   // 古いブラウザは、サーバーが出した表示のまま
    const wide = /^(ja|zh)/i.test(codeOf(UI_LANG) || '');
    document.querySelectorAll('.lang-badge[data-lang-tag]').forEach(el => {
        const tag = el.dataset.langTag, native = el.dataset.langNative || '';
        if (!tag) return;
        let local = '';
        try { local = names.of(tag) || ''; } catch (e) {}
        if (!local || local === tag) return;   // 名前が分からない（対応外のコード）ときは、そのまま
        const text = native && native.toLowerCase() !== local.toLowerCase() ? (wide ? native + '（' + local + '）' : native + ' (' + local + ')') : (native || local);
        const t = el.querySelector('.lang-badge-text');
        if (t) t.textContent = text;
    });
}
document.addEventListener('DOMContentLoaded', localizeLangBadges);
