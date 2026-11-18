// 画像の重ね翻訳（3/4）: 画像として保存。overlay.js の後に読み込む

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
