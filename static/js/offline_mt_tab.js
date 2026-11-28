// オフライン画面のテキスト翻訳（v1.9.1）: 翻訳メモリーと、設定でダウンロード済みのモデルで、通信なしで訳す（日本語⇄英語）。言語のバーは、オンラインの画面と同じ形（v1.10.1）
(function () {
    const root = document.getElementById('omt-tab');
    if (!root || typeof OfflineMT === 'undefined') return;
    const $t = (id) => document.getElementById(id);
    const NAMES = { 'ja-en': ['Japanese', 'English', 'en-US'], 'en-ja': ['English', 'Japanese', 'ja-JP'] };
    const JA = /[぀-ヿ㐀-鿿]/;
    let dir = (typeof TARGET_LANG !== 'undefined' && TARGET_LANG === 'Japanese') ? 'en-ja' : 'ja-en', busy = false;
    const ready = {};

    const pick = () => dir;
    const nativeOf = (name) => ((typeof langByName === 'function' && langByName(name)) || {}).native || name;
    // 入れた文が日本語なら日本語→英語、そうでなければ英語→日本語に、バーを合わせる（取り違えを防ぐ）
    const follow = (text) => { if (text) { const want = JA.test(text) ? 'ja-en' : 'en-ja'; if (want !== dir) setDir(want); } };
    const show = (id, on) => $t(id).classList.toggle('hidden', !on);

    async function refresh() {
        for (const p of Object.keys(NAMES)) ready[p] = OfflineMT.supported() && await OfflineMT.isDownloaded(p).catch(() => false);
        paint();
    }

    function paint() {
        const text = $t('omt-tab-in').value.trim();
        const pair = pick();
        show('omt-tab-need', !OfflineMT.supported() || !ready[pair]);
        $t('omt-tab-run').disabled = busy || !text;      // モデルが無くても、翻訳メモリーにある文は訳せるので、押せる
    }

    function setDir(v) {
        dir = v;
        $t('omt-tab-from').textContent = nativeOf(NAMES[v][0]);
        $t('omt-tab-to').textContent = nativeOf(NAMES[v][1]);
        paint();
    }

    async function run() {
        const text = $t('omt-tab-in').value.trim();
        if (busy || !text) return;
        follow(text);
        const pair = pick();
        busy = true; show('omt-tab-err', false); paint();
        $t('omt-tab-out').textContent = UI.omt_running;
        $t('omt-tab-label').textContent = UI['omt_' + pair.replace('-', '_')];
        show('omt-tab-result', true);
        const n = NAMES[pair];
        let r;
        try { r = await OfflineText.translate(text, n[1], pair); } catch (e) { r = { error: 'failed' }; }
        if (r.error) {
            show('omt-tab-result', false);
            $t('omt-tab-err').textContent = r.error === 'failed' ? UI.ot_err : (UI['lo_msg_' + r.error] || UI.ot_err);
            show('omt-tab-err', true);
        } else {
            $t('omt-tab-out').textContent = r.out;
            const via = OfflineText.viaText(r);
            $t('omt-tab-label').textContent = UI['omt_' + pair.replace('-', '_')] + (via ? '  ·  ' + via : '');
            addHistory({ mode: 'text', src: text, out: r.out, srcLang: n[0], tgt: n[1], tcode: n[2], pron: '', offline: true });
        }
        busy = false; paint();
    }

    async function copy() {
        const label = $t('omt-tab-copy').querySelector('span');
        try { await navigator.clipboard.writeText($t('omt-tab-out').textContent); label.textContent = UI.copied; }
        catch (e) { return; }
        setTimeout(() => { label.textContent = UI.copy_btn; }, 1500);
    }

    $t('omt-tab-swap').addEventListener('click', () => setDir(dir === 'ja-en' ? 'en-ja' : 'ja-en'));
    $t('omt-tab-in').addEventListener('input', () => { follow($t('omt-tab-in').value.trim()); paint(); });
    $t('omt-tab-run').addEventListener('click', () => { refresh().then(run); });   // 押すたびに、ダウンロードの状態を確かめ直す
    $t('omt-tab-copy').addEventListener('click', copy);
    $t('omt-tab-open').addEventListener('click', () => {
        if (typeof setHistFilter === 'function') setHistFilter('settings');
        const card = $t('omt-card');
        if (card && card.scrollIntoView) card.scrollIntoView({ block: 'start' });
    });
    document.addEventListener('omt-changed', refresh);
    setDir(dir);
    refresh();
})();
