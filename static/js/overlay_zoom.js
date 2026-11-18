// 画像の重ね翻訳（2/4）: 拡大表示。overlay.js の後に読み込む

// ---- 拡大表示（全画面。＋－ボタンかピンチで大きくして、指でなぞって動かす） ----
let zoomEl = null;
const ZOOM_LEVELS = [1, 1.5, 2, 3, 4];

function closeZoom() {
    if (zoomEl) { zoomEl.remove(); zoomEl = null; }
    document.removeEventListener('keydown', zoomKey);
}
function zoomKey(ev) { if (ev.key === 'Escape') closeZoom(); }

function zoomBtn(label, text, onClick) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'ov-zoom-btn';
    b.setAttribute('aria-label', label);
    b.textContent = text;
    b.addEventListener('click', onClick);
    return b;
}

function openZoom(mode) {
    const st = ovState[mode];
    if (!st || !st.imgUrl) return;
    closeZoom();
    const ov = document.createElement('div');
    ov.className = 'ov-zoom';
    ov.setAttribute('role', 'dialog');
    ov.setAttribute('aria-modal', 'true');

    const scroll = document.createElement('div');
    scroll.className = 'ov-zoom-scroll';
    const stage = document.createElement('div');
    stage.className = 'ov-stage ov-zoom-stage';
    const img = document.createElement('img');
    img.className = 'block w-full h-auto';
    img.alt = '';
    img.src = st.imgUrl;
    const layer = document.createElement('div');
    layer.className = 'ov-layer';
    fillLayer(layer, st.blocks);
    layer.classList.toggle('hidden', !st.on);
    stage.append(img, layer);
    scroll.appendChild(stage);

    let idx = 0;
    const setLevel = (i) => {
        idx = Math.max(0, Math.min(ZOOM_LEVELS.length - 1, i));
        stage.style.width = (ZOOM_LEVELS[idx] * 100) + '%';
        requestAnimationFrame(() => fitLayer(layer));
    };
    const bar = document.createElement('div');
    bar.className = 'ov-zoom-bar';
    bar.append(
        zoomBtn(UI.big_close, '✕', closeZoom),
        zoomBtn(UI.ov_zoom_out, '－', () => setLevel(idx - 1)),
        zoomBtn(UI.ov_zoom_in, '＋', () => setLevel(idx + 1)),
        zoomBtn(st.on ? UI.ov_hide : UI.ov_show, '◐', () => { layer.classList.toggle('hidden'); if (!layer.classList.contains('hidden')) fitLayer(layer); }),
    );
    ov.append(scroll, bar);
    document.body.appendChild(ov);
    zoomEl = ov;
    document.addEventListener('keydown', zoomKey);
    img.addEventListener('load', () => fitLayer(layer));
    setLevel(0);
    bar.firstChild.focus({ preventScroll: true });
}
