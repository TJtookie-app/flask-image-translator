// PDF 翻訳（数ページずつ送る）。進捗バーを出し、終わったら履歴にも残す
let pdfAbort = null;
const PDF_HIST_MAX = 4800;   // 履歴1件に残す訳文の長さ（バックアップの読み込み上限 5000 字に収める）

function pageCard(p) {
    const card = document.createElement('div');
    card.className = 'p-3 rounded-2xl bg-indigo-950/40 border border-indigo-800/60 space-y-1.5';
    const head = document.createElement('div');
    head.className = 'flex items-center justify-between gap-2';
    const t = document.createElement('span');
    t.className = 'text-xs font-bold text-indigo-400 uppercase tracking-wider';
    t.textContent = UI.pdf_page + ' ' + p.page;
    const row = document.createElement('div');
    row.className = 'flex gap-1';
    const body = document.createElement('div');
    body.dir = 'auto';
    body.className = 'text-sm text-indigo-100 whitespace-pre-wrap break-words leading-relaxed';
    body.textContent = p.translation || '—';
    row.append(
        iconBtn('fa-solid fa-expand', UI.big_show, () => showBig(p.translation, '', 'auto')),
        iconBtn('fa-solid fa-copy', UI.copy_btn, async () => { try { await navigator.clipboard.writeText(p.translation); } catch (e) {} }),
    );
    head.append(t, row);
    card.append(head, body);
    return card;
}

// 進捗バー。最初のページが返るまで（全体のページ数が分かるまで）は、動き続ける表示にする
function makeProgressBar() {
    const track = document.createElement('div');
    track.className = 'pbar ind';
    track.setAttribute('role', 'progressbar');
    track.setAttribute('aria-valuemin', '0');
    track.setAttribute('aria-valuemax', '100');
    const fill = document.createElement('div');
    fill.className = 'pbar-fill';
    track.appendChild(fill);
    return {
        el: track,
        set(pct) {
            track.classList.remove('ind');
            fill.style.width = pct + '%';
            track.setAttribute('aria-valuenow', String(Math.round(pct)));
        },
        state(s) {   // done / error / stopped
            track.classList.remove('ind');
            track.classList.add('pbar-' + s);
            if (!fill.style.width) fill.style.width = s === 'error' ? '100%' : '0%';
        },
    };
}

// 翻訳できたぶんを履歴に残す（長い PDF は先頭だけ。元のファイル名とページ数が分かるようにする）
function savePdfHistory(file, texts) {
    if (!texts.length || typeof addHistory !== 'function') return;
    let out = texts.join('\n\n');
    if (out.length > PDF_HIST_MAX) out = out.slice(0, PDF_HIST_MAX) + '…';
    addHistory({
        mode: 'pdf',
        src: '📄 ' + (file.name || 'PDF') + ' (' + fmt(UI.pdf_hist_pages, { n: texts.length }) + ')',
        out, srcLang: '', tgt: TARGET_LANG, tcode: codeOf(TARGET_LANG), pron: '',
    });
}

async function runPdf(file) {
    if (pdfAbort) pdfAbort.abort();
    const ctl = pdfAbort = new AbortController();
    const box = $('pdf-result');
    box.classList.remove('hidden');
    box.replaceChildren();

    const bar = document.createElement('div');
    bar.className = 'flex items-center justify-between gap-2 text-xs text-slate-300';
    const status = document.createElement('span');
    status.setAttribute('role', 'status');
    const stop = document.createElement('button');
    stop.type = 'button';
    stop.className = 'px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700';
    stop.textContent = UI.pdf_cancel;
    stop.onclick = () => ctl.abort();
    bar.append(status, stop);
    const pbar = makeProgressBar();
    const cards = document.createElement('div');
    cards.className = 'space-y-2';
    box.append(bar, pbar.el, cards);

    const texts = [];
    let start = 1, limit = null, total = null;
    status.textContent = UI.translating;
    try {
        while (limit === null || start <= limit) {
            const fd = new FormData();
            fd.append('file', file);
            fd.append('target', TARGET_LANG);
            fd.append('start', String(start));
            fd.append('end', String(start + 2));
            fd.append('formality', loadSettings().formality);
            const r = await fetch('/api/translate-pdf', { method: 'POST', body: fd, signal: ctl.signal });
            let data = {};
            try { data = await r.json(); } catch (e) {}
            if (!r.ok || !data.pages) throw new Error(data.error || UI.err_failed);
            total = data.total; limit = data.limit;
            data.pages.forEach(p => { cards.appendChild(pageCard(p)); texts.push(p.translation); });
            start += 3;
            const pct = Math.min(100, texts.length / limit * 100);
            pbar.set(pct);
            if (start <= limit) status.textContent = fmt(UI.pdf_progress, { p: start, n: limit }) + ' (' + Math.round(pct) + '%)';
        }
        pbar.set(100);
        pbar.state('done');
        status.textContent = fmt(UI.pdf_done, { n: texts.length });
        stop.remove();
        const all = iconBtn('fa-solid fa-copy', UI.pdf_copy_all, async () => { try { await navigator.clipboard.writeText(texts.join('\n\n')); } catch (e) {} });
        all.className = 'px-3 h-10 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs transition';
        all.append(' ' + UI.pdf_copy_all);
        bar.appendChild(all);
        if (total > limit) {
            const n = document.createElement('p');
            n.className = 'text-xs text-amber-200';
            n.textContent = fmt(UI.pdf_truncated, { m: limit });
            box.appendChild(n);
        }
    } catch (e) {
        stop.remove();
        if (e && e.name === 'AbortError') { pbar.state('stopped'); status.textContent = UI.pdf_cancel; }
        else {
            pbar.state('error');
            status.textContent = e instanceof TypeError ? UI.err_network : (e.message || UI.err_failed);
            status.classList.add('text-red-300');
        }
    } finally {
        savePdfHistory(file, texts);   // 途中で止まっても、翻訳できたぶんは残す
        if (pdfAbort === ctl) pdfAbort = null;
    }
}
