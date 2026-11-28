// オフライン画面のテキスト翻訳（v1.9.1）: 翻訳メモリーと、設定でダウンロード済みのモデルで、通信なしで訳す。
// 言語のバーは、オンラインの画面と同じ形（v1.10.1）。v1.11.0 で、日本語・英語・中国語・韓国語から選べるようにした（使えない組み合わせは選べない）
(function () {
    const root = document.getElementById('omt-tab');
    if (!root || typeof OfflineMT === 'undefined' || typeof OfflineText === 'undefined') return;
    const $t = (id) => document.getElementById(id);
    const T = OfflineText;
    const HAN = ['Japanese', 'Chinese (Simplified)', 'Chinese (Traditional)'];
    let from = TARGET_LANG === 'Japanese' ? 'English' : 'Japanese', to = TARGET_LANG === 'Japanese' ? 'Japanese' : 'English', busy = false;
    const ready = {};

    const show = (id, on) => $t(id).classList.toggle('hidden', !on);
    const valid = (f, t) => !!T.route(f, t);
    // 翻訳元に対して、使える翻訳先を選び直す（英語なら日本語、それ以外は英語を先に）
    const fixFrom = () => { from = ['English'].concat(T.NAMES).find((n) => valid(n, to)) || from; };
    const fixTo = () => { if (!valid(from, to)) to = [from === 'English' ? 'Japanese' : 'English'].concat(T.NAMES).find((n) => valid(from, n)) || to; };
    const preferHan = () => (HAN.indexOf(from) >= 0 ? from : (to === 'Japanese' ? 'Chinese (Simplified)' : 'Japanese'));
    // 入れた文の言語が、いまの翻訳元と違えば、バーを合わせる（取り違えを防ぐ）
    function follow(text) {
        const d = text ? T.detect(text, preferHan()) : null;
        if (!d || d === from) return;
        from = d;
        if (to === from || !valid(from, to)) fixTo();
        paint();
    }

    async function refresh() {
        for (const p of OfflineMT.PAIRS) ready[p] = OfflineMT.supported() && await OfflineMT.isDownloaded(p).catch(() => false);
        paint();
    }

    function paint() {
        const text = $t('omt-tab-in').value.trim();
        const steps = T.route(from, to) || [];
        const missing = steps.map((s) => s.pair).filter((p) => !ready[p]);
        $t('omt-tab-from').value = from; $t('omt-tab-to').value = to;
        // 翻訳先に選べないのは、どの言語からも使えるモデルがないもの（いまは韓国語）。同じ言語を選んだときは、入れ替える
        Array.from($t('omt-tab-to').options).forEach((o) => { o.disabled = !T.NAMES.some((f) => valid(f, o.value)); });
        show('omt-tab-need', !OfflineMT.supported() || missing.length > 0);
        $t('omt-tab-missing').textContent = T.missingText(missing).trim();
        $t('omt-tab-run').disabled = busy || !text;      // モデルが無くても、翻訳メモリーにある文は訳せるので、押せる
    }

    async function run() {
        const text = $t('omt-tab-in').value.trim();
        if (busy || !text) return;
        follow(text);
        busy = true; show('omt-tab-err', false); paint();
        const label = () => ((langByName(from) || {}).native || from) + ' → ' + ((langByName(to) || {}).native || to);
        $t('omt-tab-out').textContent = UI.omt_running;
        $t('omt-tab-label').textContent = label();
        show('omt-tab-result', true);
        let r;
        try { r = await T.translate(text, to, from); } catch (e) { r = { error: 'failed' }; }
        if (r.error) {
            show('omt-tab-result', false);
            $t('omt-tab-err').textContent = r.error === 'failed' ? UI.ot_err : (UI['lo_msg_' + r.error] || UI.ot_err) + T.missingText(r.missing);
            show('omt-tab-err', true);
        } else {
            $t('omt-tab-out').textContent = r.out;
            const via = T.viaText(r);
            $t('omt-tab-label').textContent = label() + (via ? '  ·  ' + via : '');
            addHistory({ mode: 'text', src: text, out: r.out, srcLang: from, tgt: to, tcode: codeOf(to), pron: '', offline: true });
        }
        busy = false; paint();
    }

    async function copy() {
        const label = $t('omt-tab-copy').querySelector('span');
        try { await navigator.clipboard.writeText($t('omt-tab-out').textContent); label.textContent = UI.copied; }
        catch (e) { return; }
        setTimeout(() => { label.textContent = UI.copy_btn; }, 1500);
    }

    $t('omt-tab-from').addEventListener('change', () => {
        const old = from; from = $t('omt-tab-from').value;
        if (from === to) to = old;
        if (!valid(from, to)) fixTo();
        paint();
    });
    $t('omt-tab-to').addEventListener('change', () => {
        const old = to; to = $t('omt-tab-to').value;
        if (to === from) from = old;
        if (!valid(from, to)) fixFrom();
        paint();
    });
    $t('omt-tab-swap').addEventListener('click', () => { const f = from; from = to; to = f; if (!valid(from, to)) fixTo(); paint(); });
    $t('omt-tab-in').addEventListener('input', () => { follow($t('omt-tab-in').value.trim()); paint(); });
    $t('omt-tab-run').addEventListener('click', () => { refresh().then(run); });   // 押すたびに、ダウンロードの状態を確かめ直す
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
