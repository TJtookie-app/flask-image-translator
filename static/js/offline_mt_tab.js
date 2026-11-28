// オフライン画面のテキスト翻訳（v1.9.1）: 設定でダウンロード済みのモデルで、通信なしで訳す（日本語⇄英語）
(function () {
    const root = document.getElementById('omt-tab');
    if (!root || typeof OfflineMT === 'undefined') return;
    const $t = (id) => document.getElementById(id);
    const NAMES = { 'ja-en': ['Japanese', 'English', 'en-US'], 'en-ja': ['English', 'Japanese', 'ja-JP'] };
    const JA = /[぀-ヿ㐀-鿿]/;
    let dir = 'auto', busy = false;
    const ready = {};

    const pick = (text) => (dir !== 'auto' ? dir : (JA.test(text) ? 'ja-en' : 'en-ja'));
    const show = (id, on) => $t(id).classList.toggle('hidden', !on);

    async function refresh() {
        for (const p of Object.keys(NAMES)) ready[p] = OfflineMT.supported() && await OfflineMT.isDownloaded(p).catch(() => false);
        paint();
    }

    function paint() {
        const text = $t('omt-tab-in').value.trim();
        const pair = pick(text);
        show('omt-tab-need', !OfflineMT.supported() || !ready[pair]);
        $t('omt-tab-run').disabled = busy || !text || !ready[pair];
    }

    function setDir(v) {
        dir = v;
        root.querySelectorAll('#omt-tab-dirs button').forEach((b) => {
            const on = b.dataset.dir === v;
            b.setAttribute('aria-pressed', on ? 'true' : 'false');
            b.className = b.className.replace(/bg-indigo-600 text-white|bg-slate-800 text-slate-300/, on ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-300');
        });
        paint();
    }

    async function run() {
        const text = $t('omt-tab-in').value.trim();
        const pair = pick(text);
        if (busy || !text || !ready[pair]) return;
        busy = true; show('omt-tab-err', false); paint();
        $t('omt-tab-out').textContent = UI.omt_running;
        $t('omt-tab-label').textContent = UI['omt_' + pair.replace('-', '_')];
        show('omt-tab-result', true);
        try {
            const out = await OfflineMT.translate(pair, text);
            $t('omt-tab-out').textContent = out;
            const n = NAMES[pair];
            if (typeof addHistory === 'function') addHistory({ mode: 'text', src: text, out, srcLang: n[0], tgt: n[1], tcode: n[2], pron: '' });
        } catch (e) { show('omt-tab-result', false); show('omt-tab-err', true); }
        busy = false; paint();
    }

    async function copy() {
        const label = $t('omt-tab-copy').querySelector('span');
        try { await navigator.clipboard.writeText($t('omt-tab-out').textContent); label.textContent = UI.copied; }
        catch (e) { return; }
        setTimeout(() => { label.textContent = UI.copy_btn; }, 1500);
    }

    root.querySelectorAll('#omt-tab-dirs button').forEach((b) => b.addEventListener('click', () => setDir(b.dataset.dir)));
    $t('omt-tab-in').addEventListener('input', paint);
    $t('omt-tab-run').addEventListener('click', () => { refresh().then(run); });
    $t('omt-tab-copy').addEventListener('click', copy);
    $t('omt-tab-open').addEventListener('click', () => {
        if (typeof setHistFilter === 'function') setHistFilter('settings');
        const card = $t('omt-card');
        if (card && card.scrollIntoView) card.scrollIntoView({ block: 'start' });
    });
    document.addEventListener('omt-changed', refresh);
    paint();
    refresh();
})();
