// 画像の重ね翻訳（1/4）: 画像の縮小・重ね表示。続きは overlay_zoom.js / overlay_save.js / overlay_boot.js
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
