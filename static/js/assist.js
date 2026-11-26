// 結果カードの「返信を提案」と「辞書・文法」。どちらもメニューを押したときだけ API を1回呼ぶ（読む側 = 外国語の文を訳したとき）
// 読む側: 原文が自分の言語でない → 原文に返信／原文を解説。自分の言語で入力したとき → 返信は出さず、辞書・文法は相手に言う訳文を解説する

// 外国語の文を読んでいるか（原文が、画面の言語と違うか）
const isReading = () => !!(RESULT && RESULT.src && RESULT.srcLang && RESULT.srcLang !== UI_LANG);

// 外国語の側（返信する相手の文／辞書で調べる文）と、その言語
function foreignSide() {
    if (!RESULT) return { text: '', lang: '' };
    return isReading() ? { text: RESULT.src, lang: RESULT.srcLang } : { text: RESULT.out || '', lang: RESULT.tgt };
}

// 返信の提案は、外国語を読んだときだけ（自分の言語で入力したときは、メニューから隠す）
function syncAssistMenu() {
    document.querySelectorAll('.rc-reply').forEach(b => b.classList.toggle('hidden', !isReading()));
}
document.addEventListener('DOMContentLoaded', syncAssistMenu);

// 別の結果（別の言い方・口調・解説）を出すとき、返信と辞書の枠を閉じる
function hideAssistBoxes(mode) { ['replies-', 'dict-'].forEach(p => { const b = $(p + mode); if (b) b.classList.add('hidden'); }); }

function assistBox(id, hideOthers, mode) {
    const box = $(id + '-' + mode);
    if (!box) return null;
    (hideOthers || []).forEach(p => { const o = $(p + mode); if (o) o.classList.add('hidden'); });
    box.classList.remove('hidden');
    box.replaceChildren();
    const note = document.createElement('p');
    note.className = 'text-xs text-slate-400';
    note.textContent = UI.alts_loading;
    box.appendChild(note);
    return box;
}

async function assistCall(url, payload) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    let data = {};
    try { data = await r.json(); } catch (e) {}
    if (!r.ok) throw new Error(data.error || UI.err_failed);
    return data;
}

function assistError(box, e) {
    const note = document.createElement('p');
    note.className = 'text-xs text-red-300';
    note.textContent = e instanceof TypeError ? UI.err_network : (e.message || UI.err_failed);
    box.replaceChildren(note);
}

function smallBtn(label, onClick) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'as-btn';
    b.textContent = label;
    b.addEventListener('click', () => onClick(b));
    return b;
}

async function copyPlain(text, btn) {
    try { await navigator.clipboard.writeText(text); } catch (e) {
        const t = document.createElement('textarea');
        t.value = text; document.body.appendChild(t); t.select();
        try { document.execCommand('copy'); } catch (e2) {}
        t.remove();
    }
    const old = btn.textContent;
    btn.textContent = UI.copied;
    setTimeout(() => { btn.textContent = old; }, 1500);
}

// ---- 返信を提案: 相手の言語の返信案3つ（意味つき）。コピー・読み上げができる ----
async function suggestReplies(mode, btn) {
    if (!RESULT || !isReading()) return;
    const box = assistBox('replies', ['alts-', 'tones-', 'dict-'], mode);
    if (!box) return;
    if (btn) btn.disabled = true;
    try {
        const data = await assistCall('/api/replies', { text: RESULT.src, lang: RESULT.srcLang, formality: loadSettings().formality });
        if (!Array.isArray(data.replies) || !data.replies.length) throw new Error(UI.err_failed);
        const label = document.createElement('p');
        label.className = 'text-xs font-semibold text-slate-400';
        label.textContent = UI.reply_label;
        box.replaceChildren(label);
        data.replies.forEach(r => {
            const card = document.createElement('div');
            card.className = 'as-card';
            if (r.kind) { const k = document.createElement('span'); k.className = 'as-tag'; k.textContent = r.kind; card.appendChild(k); }
            const t = document.createElement('p'); t.dir = 'auto'; t.className = 'as-main'; t.textContent = r.text; card.appendChild(t);
            if (r.meaning) { const m = document.createElement('p'); m.dir = 'auto'; m.className = 'as-sub'; m.textContent = r.meaning; card.appendChild(m); }
            const row = document.createElement('div');
            row.className = 'as-row';
            row.append(smallBtn(UI.copy_btn, (b) => copyPlain(r.text, b)), smallBtn(UI.speak, () => speak(r.text, codeOf(RESULT.srcLang))));
            card.appendChild(row);
            box.appendChild(card);
        });
    } catch (e) { assistError(box, e); } finally { if (btn) btn.disabled = false; }
}

// ---- 辞書・文法: 大事な単語（読み・品詞・意味・例文・語源）と文法のポイント。単語は単語帳に保存できる ----
async function showDictionary(mode, btn) {
    if (!RESULT) return;
    const side = foreignSide();
    if (!side.text) return;
    const box = assistBox('dict', ['alts-', 'tones-', 'replies-'], mode);
    if (!box) return;
    if (btn) btn.disabled = true;
    try {
        const data = await assistCall('/api/dictionary', { text: side.text.slice(0, 600), lang: side.lang });
        box.replaceChildren();
        (data.words || []).forEach(w => {
            const card = document.createElement('div');
            card.className = 'as-card';
            const head = document.createElement('p');
            head.dir = 'auto'; head.className = 'as-main';
            head.textContent = w.word + (w.reading ? '  [' + w.reading + ']' : '');
            card.appendChild(head);
            const meta = [w.pos, w.meaning].filter(Boolean).join(' · ');
            const m = document.createElement('p'); m.dir = 'auto'; m.className = 'as-sub'; m.textContent = meta; card.appendChild(m);
            if (w.example) { const e = document.createElement('p'); e.dir = 'auto'; e.className = 'as-ex'; e.textContent = w.example; card.appendChild(e); }
            if (w.origin) { const o = document.createElement('p'); o.className = 'as-origin'; o.textContent = UI.dict_origin + ': ' + w.origin; card.appendChild(o); }
            const row = document.createElement('div');
            row.className = 'as-row';
            row.append(
                smallBtn(UI.speak, () => speak(w.word, codeOf(side.lang))),
                smallBtn(UI.vocab_save, (b) => { addVocab({ src: w.word, out: w.meaning, srcLang: side.lang, tgt: UI_LANG, tcode: '', pron: w.reading || '' }); b.textContent = UI.vocab_saved; b.disabled = true; }),
            );
            card.appendChild(row);
            box.appendChild(card);
        });
        if ((data.grammar || []).length) {
            const gh = document.createElement('p'); gh.className = 'text-xs font-semibold text-slate-400'; gh.textContent = UI.dict_grammar; box.appendChild(gh);
            data.grammar.forEach(g => {
                const card = document.createElement('div');
                card.className = 'as-card';
                const p = document.createElement('p'); p.dir = 'auto'; p.className = 'as-main'; p.textContent = g.point; card.appendChild(p);
                const n = document.createElement('p'); n.dir = 'auto'; n.className = 'as-sub'; n.textContent = g.note; card.appendChild(n);
                box.appendChild(card);
            });
        }
        if (!box.childNodes.length) throw new Error(UI.err_failed);
    } catch (e) { assistError(box, e); } finally { if (btn) btn.disabled = false; }
}
