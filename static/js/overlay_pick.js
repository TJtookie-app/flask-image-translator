// 画像の重ね翻訳（2/5）: 文字のまとまりをタップで選ぶ。overlay.js の後に読み込む
// 画像の上に、文字のまとまりごとの枠を出す。タップで選ぶ／外す。選んだ部分だけを、下のパネルに出し、「即翻訳」で画像の上でも訳文に置き換える。
// 選び直しても API は使わない（読み取りのときに、全部の原文と訳文を受け取っている）。

// 選んだ部分（何も選んでいなければ、全部）
function ovPicked(st) {
    if (!st || !st.blocks) return [];
    return st.sel && st.sel.size ? st.blocks.filter((b, i) => st.sel.has(i)) : st.blocks;
}

function pickRender(mode) {
    const st = ovState[mode], el = ovEls(mode);
    if (!st || !el.layer) return;
    el.layer.replaceChildren();
    if (st.imgUrl) {
        st.blocks.forEach((b, i) => {
            const [y0, x0, y1, x1] = b.box;
            const sel = st.sel.has(i), replaced = st.on && sel;
            const d = document.createElement('div');
            d.className = replaced ? 'ov-block ov-picked' : 'ov-pick' + (sel ? ' sel' : '');
            d.dir = 'auto';
            d.style.cssText = `left:${x0 / 10}%;top:${y0 / 10}%;width:${(x1 - x0) / 10}%;height:${(y1 - y0) / 10}%;`;
            d.setAttribute('role', 'button');
            d.setAttribute('aria-pressed', sel ? 'true' : 'false');
            d.tabIndex = 0;
            if (replaced) d.textContent = b.translation;
            d.title = b.text || '';
            d.addEventListener('click', () => ovToggleSel(mode, i));
            d.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); ovToggleSel(mode, i); } });
            el.layer.appendChild(d);
        });
        fitLayer(el.layer);
    }
    renderOvList(mode);
}

function ovToggleSel(mode, i) {
    const st = ovState[mode];
    if (!st) return;
    if (st.sel.has(i)) st.sel.delete(i); else st.sel.add(i);
    ovApply(mode);
}

// すべて選択 ⇄ 選択を解除
function ovSelectAll(mode) {
    const st = ovState[mode];
    if (!st) return;
    st.sel = st.sel.size === st.blocks.length ? new Set() : new Set(st.blocks.map((b, i) => i));
    ovApply(mode);
}

// 即翻訳: 選んだ部分を訳文に置き換える（何も選んでいなければ、全部を選んでから）
function ovToggleOn(mode) {
    const st = ovState[mode];
    if (!st) return;
    if (st.on && st.sel.size) st.on = false;
    else { if (!st.sel.size) st.sel = new Set(st.blocks.map((b, i) => i)); st.on = true; }
    ovApply(mode);
}

function renderOvList(mode) {
    const st = ovState[mode], list = ovEls(mode).list;
    list.replaceChildren();
    if (!st.imgUrl) {
        const note = document.createElement('p');
        note.className = 'text-xs text-slate-400';
        note.textContent = UI.ov_fallback;
        list.appendChild(note);
    }
    ovPicked(st).forEach(b => {
        const d = document.createElement('div');
        d.className = 'ov-entry p-2 rounded-xl bg-slate-950/60 border border-slate-800 space-y-0.5';
        const tr = document.createElement('div');
        tr.dir = 'auto';
        tr.className = 'text-sm text-indigo-100 whitespace-pre-wrap';
        tr.textContent = b.translation;
        d.appendChild(tr);
        if (b.text) {
            const src = document.createElement('div');
            src.dir = 'auto';
            src.className = 'text-xs text-slate-400 whitespace-pre-wrap';
            src.textContent = b.text;
            d.appendChild(src);
        }
        list.appendChild(d);
    });
}

async function ovCopyPicked(mode) {
    const st = ovState[mode], btn = ovEls(mode).copy;
    if (!st) return;
    const text = ovPicked(st).map(b => b.translation).join('\n');
    try { await navigator.clipboard.writeText(text); } catch (e) {
        const t = document.createElement('textarea');
        t.value = text; document.body.appendChild(t); t.select();
        try { document.execCommand('copy'); } catch (e2) {}
        t.remove();
    }
    if (btn) { const old = btn.textContent; btn.textContent = UI.copied || '✓'; setTimeout(() => { btn.textContent = old; }, 1500); }
}
