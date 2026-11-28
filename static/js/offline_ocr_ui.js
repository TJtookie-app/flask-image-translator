// 設定の「写真の文字認識」: 言語パックごとの1行（ダウンロード・削除）。言語パックを追加したときは、続けて入れる（offline_mt_ui.js の通知）
(function () {
    const card = document.getElementById('omt-card');
    if (!card || typeof OfflineOCR === 'undefined') return;
    const rows = Array.from(card.querySelectorAll('.ocr-row'));
    const q = (sel, root) => (root || card).querySelector(sel);
    let busy = false, loading = '';

    function paint() {
        rows.forEach((r) => {
            const pk = r.dataset.ocrPack, ok = OfflineOCR.packReady(pk), now = loading === pk;
            q('.ocr-state', r).textContent = now ? UI.omt_state_loading : (ok ? UI.omt_state_ready : UI.ocr_state_none);
            q('.ocr-get', r).classList.toggle('hidden', ok || now);
            q('.ocr-del', r).classList.toggle('hidden', !ok || now);
            q('.ocr-get', r).disabled = busy; q('.ocr-del', r).disabled = busy;
            if (!now) q('.ocr-bar', r).classList.add('hidden');
        });
    }

    async function get(pk) {
        const row = rows.find((r) => r.dataset.ocrPack === pk);
        if (!row || busy || OfflineOCR.packReady(pk)) return;
        busy = true; loading = pk; q('#ocr-err').classList.add('hidden'); paint();
        const bar = q('.ocr-bar', row), fill = q('.pbar-fill', bar);
        bar.classList.remove('hidden'); fill.style.width = '0%';
        const codes = OfflineOCR.PACK[pk].filter((c) => !OfflineOCR.isDownloaded(c));
        try {
            for (let i = 0; i < codes.length; i++) {
                await OfflineOCR.download(codes[i], (r) => { fill.style.width = Math.round(((i + r) / codes.length) * 100) + '%'; });
            }
        } catch (e) {
            const err = q('#ocr-err'); err.textContent = UI.ocr_err + ' (' + ((e && e.message) || e) + ')'; err.classList.remove('hidden');
        }
        busy = false; loading = ''; paint();
        document.dispatchEvent(new Event('ocr-changed'));
    }

    function del(pk) {
        if (busy || !window.confirm(UI.omt_confirm_del)) return;
        OfflineOCR.remove(OfflineOCR.PACK[pk].filter((c) => c !== 'eng' || !other(pk)));
        paint(); document.dispatchEvent(new Event('ocr-changed'));
    }
    // 英語の認識データは、ほかの言語でも使うので、ほかに入れた言語が残っているあいだは消さない
    const other = (pk) => Object.keys(OfflineOCR.PACK).some((k) => k !== pk && OfflineOCR.PACK[k].some((c) => c !== 'eng' && OfflineOCR.isDownloaded(c)));

    if (!OfflineOCR.supported()) { rows.forEach((r) => r.classList.add('hidden')); return; }
    rows.forEach((r) => {
        q('.ocr-get', r).addEventListener('click', () => get(r.dataset.ocrPack));
        q('.ocr-del', r).addEventListener('click', () => del(r.dataset.ocrPack));
    });
    document.addEventListener('omt-pack-added', (ev) => get(ev.detail));
    paint();
})();
