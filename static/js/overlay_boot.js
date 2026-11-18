// 画像の重ね翻訳（4/4）: 送信前の処理と起動時の復元。overlay.js の後に読み込む

// ---- 送信前の処理（画像は縮小して保持／PDF は別処理） ----
document.addEventListener('submit', async (ev) => {
    const form = ev.target;
    if (!form.closest || !form.closest('#tab-image')) return;
    const input = form.querySelector('input[type=file]');
    const file = input && input.files && input.files[0];
    if (!file) return;
    if (isPdf(file)) {
        ev.preventDefault();
        ev.stopImmediatePropagation();
        runPdf(file);
        return;
    }
    ev.preventDefault();   // 縮小が終わってから送る
    const blob = await downscaleImage(file);
    if (blob && blob.size < file.size * 1.5 + 1024) {
        try {
            const dt = new DataTransfer();
            dt.items.add(new File([blob], 'image.jpg', { type: 'image/jpeg' }));
            input.files = dt.files;
            storeLastImage(await blobToDataURL(blob), 'image');
        } catch (e) { storeLastImage('', 'image'); }
    } else {
        storeLastImage('', 'image');
    }
    form.submit();
}, true);

// ---- 起動時: 直前の画像・カメラ翻訳の結果を重ねて表示 ----
document.addEventListener('DOMContentLoaded', () => {
    if (typeof OVERLAY_BLOCKS !== 'undefined' && Array.isArray(OVERLAY_BLOCKS) && OVERLAY_BLOCKS.length) {
        const mode = OV_VIEWS[INITIAL_TAB] ? INITIAL_TAB : 'image';
        renderOverlay(OVERLAY_BLOCKS, lastImage(mode), mode);
    }
});
