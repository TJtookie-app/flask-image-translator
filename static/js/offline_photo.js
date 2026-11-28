// オフライン画面の「写真から読み取る」: 写真の文字を端末内で読んで、そのまま翻訳する（v1.12.0 試作）。読み取る言語は、上の翻訳元の言語
(function () {
    const input = document.getElementById('omt-photo');
    if (!input || typeof OfflineOCR === 'undefined') return;
    const $t = (id) => document.getElementById(id);
    const say = (text, bad) => {
        const m = $t('omt-photo-msg');
        m.textContent = text; m.classList.toggle('hidden', !text);
        m.classList.toggle('text-red-300', !!bad); m.classList.toggle('text-slate-300', !bad);
    };
    let busy = false;
    input.addEventListener('change', async () => {
        const file = input.files && input.files[0];
        input.value = '';
        if (!file || busy) return;
        const from = $t('omt-tab-from').value, code = OfflineOCR.codeFor(from);
        const native = (typeof langByName === 'function' && (langByName(from) || {}).native) || from;
        if (!OfflineOCR.supported()) { say(UI.ocr_unsupported, true); return; }
        if (!code || !OfflineOCR.isDownloaded(code)) { say(UI.ocr_need.replace('{l}', native), true); return; }
        busy = true; say(UI.ocr_reading);
        try {
            const text = await OfflineOCR.recognize(file, code);
            if (!text) { say(UI.ocr_empty, true); }
            else {
                say('');
                const ta = $t('omt-tab-in');
                ta.value = text.slice(0, 2000);
                ta.dispatchEvent(new Event('input'));       // 文字から言語を合わせる
                $t('omt-tab-run').click();                  // 続けて翻訳する（読み間違いは、文を直して、もう一度押せる）
            }
        } catch (e) { say(UI.ocr_err + ' (' + ((e && e.message) || e) + ')', true); }
        busy = false;
    });
})();
