// 画像の重ね翻訳（画像・カメラの結果に、訳文を文字の位置へ重ねて表示）
// 操作: 重ね表示の切り替え / 一覧で見る / 拡大 / 画像として保存。PDF 翻訳は pdf.js
const IMG_MAX_SIDE = 1600;
// 画面の部品（templates/components/overlay_box.html）ごとの設定。key = 直前の画像を置く sessionStorage（タブを閉じると消える）
const OV_VIEWS = {
    image: { p: 'overlay', key: 'tl_last_img' },
    camera: { p: 'ovc', key: 'tl_last_img_camera' },
};
const ovState = {};   // mode -> { blocks, imgUrl, on（重ね表示）, list（一覧表示）, observed }

const isPdf = (f) => f && (f.type === 'application/pdf' || /\.pdf$/i.test(f.name || ''));

// ---- 画像を縮小（アップロードを軽くし、表示用に端末へ保持する） ----
function loadBitmap(file) {
    if (window.createImageBitmap) return createImageBitmap(file);
    return new Promise((resolve, reject) => {
        const url = URL.createObjectURL(file), img = new Image();
        img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
        img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('decode')); };
        img.src = url;
    });
}

async function downscaleImage(file) {
    try {
        const bmp = await loadBitmap(file);
        const w0 = bmp.width, h0 = bmp.height;
        if (!w0 || !h0) return null;
        const k = Math.min(1, IMG_MAX_SIDE / Math.max(w0, h0));
        const c = document.createElement('canvas');
        c.width = Math.round(w0 * k);
        c.height = Math.round(h0 * k);
        c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
        return await new Promise(res => c.toBlob(b => res(b), 'image/jpeg', 0.85));
    } catch (e) { return null; }
}

function blobToDataURL(blob) {
    return new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(String(r.result));
        r.onerror = () => reject(r.error);
        r.readAsDataURL(blob);
    });
}

function storeLastImage(url, mode) {
    const key = (OV_VIEWS[mode || 'image'] || OV_VIEWS.image).key;
    try { if (url) sessionStorage.setItem(key, url); else sessionStorage.removeItem(key); } catch (e) {
        try { sessionStorage.removeItem(key); } catch (e2) {}
    }
}
function lastImage(mode) {
    try { return sessionStorage.getItem((OV_VIEWS[mode || 'image'] || OV_VIEWS.image).key) || ''; } catch (e) { return ''; }
}

// ---- 重ね表示 ----
function fitBlock(el) {
    const h = el.clientHeight, w = el.clientWidth;
    if (!h || !w) return;
    let fs = Math.min(h * 0.85, 40);
    el.style.fontSize = fs + 'px';
    while (fs > 7 && (el.scrollHeight > h + 1 || el.scrollWidth > w + 1)) { fs -= 1; el.style.fontSize = fs + 'px'; }
}
function fitLayer(layer) { if (layer) layer.querySelectorAll('.ov-block').forEach(fitBlock); }

// 訳文のブロックを置く（結果の枠と拡大表示で共通）。タップで原文 ⇄ 訳文
function fillLayer(layer, blocks) {
    layer.replaceChildren();
    blocks.forEach(b => {
        const [y0, x0, y1, x1] = b.box;
        const el = document.createElement('div');
        el.className = 'ov-block';
        el.dir = 'auto';
        el.style.cssText = `left:${x0 / 10}%;top:${y0 / 10}%;width:${(x1 - x0) / 10}%;height:${(y1 - y0) / 10}%;`;
        el.textContent = b.translation;
        el.title = b.text || '';
        let showing = 'tr';
        el.addEventListener('click', () => {
            if (!b.text) return;
            showing = showing === 'tr' ? 'src' : 'tr';
            el.textContent = showing === 'tr' ? b.translation : b.text;
            el.classList.toggle('ov-src', showing === 'src');
            fitBlock(el);
        });
        layer.appendChild(el);
    });
}

function ovEls(mode) {
    const p = OV_VIEWS[mode].p;
    return { box: $(p + '-box'), stage: $(p + '-stage'), img: $(p + '-img'), layer: $(p + '-layer'), list: $(p + '-list'),
        toggle: $(p + '-toggle'), listbtn: $(p + '-listbtn'), zoom: $(p + '-zoom'), save: $(p + '-save') };
}

// 状態（重ね表示・一覧）に合わせて、表示とボタンを整える
function ovApply(mode) {
    const st = ovState[mode], el = ovEls(mode);
    if (!st || !el.box) return;
    const hasImg = !!st.imgUrl;
    const showList = st.list || !hasImg;          // 画像を保持できなかったときは、自動で一覧にする
    el.stage.classList.toggle('hidden', showList);
    el.list.classList.toggle('hidden', !showList);
    el.layer.classList.toggle('hidden', !st.on);
    el.toggle.classList.toggle('hidden', !hasImg || showList);
    el.toggle.textContent = st.on ? UI.ov_hide : UI.ov_show;
    el.listbtn.classList.toggle('hidden', !hasImg);
    el.listbtn.replaceChildren();
    const ic = document.createElement('i');
    ic.className = showList ? 'fa-solid fa-image' : 'fa-solid fa-list';
    const tx = document.createElement('span');
    tx.textContent = showList ? UI.ov_list_hide : UI.ov_list;
    el.listbtn.append(ic, tx);
    el.zoom.classList.toggle('hidden', !hasImg);
    el.save.classList.toggle('hidden', !hasImg);
    if (!showList && st.on) fitLayer(el.layer);
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
    st.blocks.forEach(b => {
        const d = document.createElement('div');
        d.className = 'p-2 rounded-xl bg-slate-950/60 border border-slate-800 space-y-0.5';
        const tr = document.createElement('div');
        tr.dir = 'auto';
        tr.className = 'text-sm text-indigo-100 whitespace-pre-wrap';
        tr.textContent = b.translation;
        d.appendChild(tr);
        if (b.text && st.imgUrl) {
            const src = document.createElement('div');
            src.dir = 'auto';
            src.className = 'text-xs text-slate-400 whitespace-pre-wrap';
            src.textContent = b.text;
            d.appendChild(src);
        }
        list.appendChild(d);
    });
}

function renderOverlay(blocks, imgUrl, mode) {
    mode = mode || 'image';
    const el = ovEls(mode);
    if (!el.box) return;
    const st = ovState[mode] = Object.assign(ovState[mode] || {}, { blocks, imgUrl: imgUrl || '', on: true, list: false });
    el.box.classList.remove('hidden');
    renderOvList(mode);
    if (st.imgUrl) {
        el.img.src = st.imgUrl;
        fillLayer(el.layer, blocks);
        if (!st.observed) {   // タブが開いたとき・回転したときに合わせ直す
            st.observed = true;
            if (window.ResizeObserver) new ResizeObserver(() => fitLayer(el.layer)).observe(el.stage);
            else window.addEventListener('resize', () => fitLayer(el.layer));
            el.img.addEventListener('load', () => fitLayer(el.layer));
        }
    }
    ovApply(mode);
}

function ovAction(p, action) {
    const mode = Object.keys(OV_VIEWS).find(m => OV_VIEWS[m].p === p);
    const st = mode && ovState[mode];
    if (!st) return;
    if (action === 'toggle') { st.on = !st.on; ovApply(mode); }
    else if (action === 'list') { st.list = !st.list; ovApply(mode); }
    else if (action === 'zoom') openZoom(mode);
    else if (action === 'save') saveOverlayImage(mode);
}

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

// ---- 画像として保存（元の画像に訳文を重ねて書き出す。スマホは共有シート、PC はダウンロード） ----
function loadImageEl(url) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error('image'));
        img.src = url;
    });
}

// 幅 maxW に収まるように改行する（空白があればそこで、なければ1文字ずつ。日本語などの空白なしの文に対応）
function wrapLines(ctx, text, maxW) {
    const lines = [];
    String(text).split('\n').forEach(para => {
        let line = '', sp = -1;
        for (const ch of para) {
            if (ch === ' ') {
                if (!line) continue;
                sp = line.length; line += ch; continue;
            }
            const test = line + ch;
            if (ctx.measureText(test).width <= maxW || !line) { line = test; continue; }
            if (sp >= 0) { lines.push(line.slice(0, sp)); line = line.slice(sp + 1) + ch; }
            else { lines.push(line); line = ch; }
            sp = -1;
        }
        lines.push(line);
    });
    return lines;
}

function drawBlock(ctx, b, W, H) {
    const [y0, x0, y1, x1] = b.box;
    const x = x0 / 1000 * W, y = y0 / 1000 * H, w = (x1 - x0) / 1000 * W, h = (y1 - y0) / 1000 * H;
    ctx.fillStyle = 'rgba(15, 23, 42, 0.86)';
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y, w, h, 3); else ctx.rect(x, y, w, h);
    ctx.fill();
    const pad = Math.max(2, Math.min(w, h) * 0.06);
    const maxW = Math.max(4, w - pad * 2), maxH = Math.max(4, h - pad * 2);
    let fs = Math.min(maxH * 0.9, W * 0.11), lines = [];
    for (; fs >= 8; fs -= 1) {
        ctx.font = `700 ${fs}px system-ui, "Noto Sans CJK JP", "Hiragino Sans", sans-serif`;
        lines = wrapLines(ctx, b.translation, maxW);
        if (lines.length * fs * 1.15 <= maxH) break;
    }
    ctx.font = `700 ${Math.max(fs, 8)}px system-ui, "Noto Sans CJK JP", "Hiragino Sans", sans-serif`;
    ctx.fillStyle = '#fff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.direction = /[֐-ࣿ]/.test(b.translation) ? 'rtl' : 'ltr';
    const lh = Math.max(fs, 8) * 1.15, top = y + h / 2 - (lines.length * lh) / 2 + lh / 2;
    lines.forEach((ln, i) => ctx.fillText(ln, x + w / 2, top + i * lh, maxW));
}

async function renderOverlayBlob(blocks, imgUrl) {
    const img = await loadImageEl(imgUrl);
    const W = img.naturalWidth, H = img.naturalHeight;
    const c = document.createElement('canvas');
    c.width = W; c.height = H;
    const ctx = c.getContext('2d');
    ctx.drawImage(img, 0, 0, W, H);
    blocks.forEach(b => drawBlock(ctx, b, W, H));
    return await new Promise((res, rej) => c.toBlob(b => (b ? res(b) : rej(new Error('blob'))), 'image/jpeg', 0.9));
}

async function saveOverlayImage(mode) {
    const st = ovState[mode], btn = ovEls(mode).save;
    if (!st || !st.imgUrl || !btn) return;
    const label = btn.querySelector('.ov-save-label');
    const say = (t) => { if (label) { label.textContent = t; setTimeout(() => { label.textContent = UI.ov_save; }, 2200); } };
    try {
        const blob = await renderOverlayBlob(st.blocks, st.imgUrl);
        const d = new Date(), z = (n) => String(n).padStart(2, '0');
        const name = `tookie-${d.getFullYear()}${z(d.getMonth() + 1)}${z(d.getDate())}-${z(d.getHours())}${z(d.getMinutes())}.jpg`;
        const file = new File([blob], name, { type: 'image/jpeg' });
        const touch = window.matchMedia && matchMedia('(pointer: coarse)').matches;
        if (touch && navigator.canShare && navigator.canShare({ files: [file] })) {
            try { await navigator.share({ files: [file] }); say(UI.ov_saved); return; }
            catch (e) { if (e && e.name === 'AbortError') return; }   // 共有を閉じただけなら何もしない。失敗したらダウンロードに切り替える
        }
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 5000);
        say(UI.ov_saved);
    } catch (e) { say(UI.ov_save_fail); }
}

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
