// オフライン翻訳（試作）の設定カード: ダウンロード・削除・試し翻訳・診断
(function () {
    const card = document.getElementById('omt-card');
    if (!card || typeof OfflineMT === 'undefined') return;
    const q = (sel, root) => (root || card).querySelector(sel);
    const rows = Array.from(card.querySelectorAll('.omt-row'));
    const ready = {};
    let busy = false, loading = '';   // loading: ダウンロード中の方向

    const rowOf = (pair) => rows.find((r) => r.dataset.pair === pair);
    const setBar = (row, ratio) => {
        const bar = q('.omt-bar', row);
        bar.classList.toggle('hidden', ratio === null);
        if (ratio !== null) q('.pbar-fill', bar).style.width = Math.round(ratio * 100) + '%';
    };
    const showErr = (on) => q('#omt-err').classList.toggle('hidden', !on);

    function paint(pair) {
        const row = rowOf(pair);
        const ok = !!ready[pair], now = loading === pair;
        q('.omt-state', row).textContent = now ? UI.omt_state_loading : (ok ? UI.omt_state_ready : UI.omt_state_none);
        q('.omt-get', row).classList.toggle('hidden', ok || now);
        q('.omt-del', row).classList.toggle('hidden', !ok || now);
        q('.omt-get', row).disabled = busy;
        q('.omt-del', row).disabled = busy;
        if (!now) setBar(row, null);
        const any = Object.values(ready).some(Boolean);
        q('#omt-test').classList.toggle('hidden', !any);
        card.querySelectorAll('.omt-run').forEach((b) => { b.disabled = busy || !ready[b.dataset.omtRun]; });
    }

    function paintAll() { rows.forEach((r) => paint(r.dataset.pair)); }

    async function refresh() {
        for (const r of rows) ready[r.dataset.pair] = await OfflineMT.isDownloaded(r.dataset.pair).catch(() => false);
        paintAll();
        document.dispatchEvent(new Event('omt-changed'));   // 画面上のテキスト翻訳（offline_mt_tab.js）に知らせる
    }

    async function get(pair) {
        if (busy) return;
        busy = true; loading = pair; showErr(false); paintAll(); setBar(rowOf(pair), 0);
        try {
            await OfflineMT.download(pair, (r) => setBar(rowOf(pair), r));
            ready[pair] = true;
        } catch (e) { showErr(true); }
        busy = false; loading = '';
        await refresh();
    }

    async function del(pair) {
        if (busy || !window.confirm(UI.omt_confirm_del)) return;
        busy = true; showErr(false);
        try { await OfflineMT.remove(pair); } catch (e) { showErr(true); }
        busy = false;
        await refresh();
    }

    async function run(pair) {
        const text = q('#omt-in').value.trim();
        if (busy || !text) return;
        busy = true; showErr(false); paintAll();
        const out = q('#omt-out');
        out.textContent = UI.omt_running;
        try { out.textContent = await OfflineMT.translate(pair, text); }
        catch (e) { out.textContent = ''; showErr(true); }
        busy = false;
        paintAll();
    }

    async function copyDiag() {
        const text = (await OfflineMT.envText()) + '\n---\n' + q('#omt-diag').textContent;
        try { await navigator.clipboard.writeText(text); q('#omt-copy').textContent = UI.omt_copied; }
        catch (e) { q('#omt-diag').textContent = text; }
        setTimeout(() => { q('#omt-copy').textContent = UI.omt_diag_copy; }, 1500);
    }

    // 設定で「自動ダウンロード」が ON のとき、オンラインなら、足りない方向を順に入れる（1回の起動で1回だけ。失敗したら、次の起動でやり直す）。
    // 携帯回線かどうかが分かる端末（Android など）では、携帯回線とデータ節約のときは始めない。iPhone の Safari は分からない
    const cellular = () => { const c = navigator.connection; return !!c && (c.type === 'cellular' || c.saveData === true); };
    async function autoGet() {
        if (!loadSettings().autoModel || navigator.onLine === false || cellular() || busy) return;
        try { if (sessionStorage.getItem('omt_auto')) return; sessionStorage.setItem('omt_auto', '1'); } catch (e) {}
        for (const r of rows) {
            const pair = r.dataset.pair;
            if (ready[pair] || !r.dataset.auto) continue;      // 自動で入れるのは、日本語⇄英語の2つだけ（中国語・韓国語は、ボタンを押したときだけ）
            await get(pair);
            if (!ready[pair]) break;
        }
    }
    document.addEventListener('omt-auto-on', () => { try { sessionStorage.removeItem('omt_auto'); } catch (e) {} autoGet(); });

    rows.forEach((r) => {
        q('.omt-get', r).addEventListener('click', () => get(r.dataset.pair));
        q('.omt-del', r).addEventListener('click', () => del(r.dataset.pair));
    });
    card.querySelectorAll('.omt-run').forEach((b) => b.addEventListener('click', () => run(b.dataset.omtRun)));
    q('#omt-copy').addEventListener('click', copyDiag);
    OfflineMT.setLogger((lines) => {
        q('#omt-diag').textContent = lines.join('\n');
    });

    if (!OfflineMT.supported()) {
        q('#omt-unsupported').classList.remove('hidden');
        q('#omt-rows').classList.add('hidden');
        return;
    }
    paintAll();
    OfflineMT.envText().then((t) => { q('#omt-diag').textContent = t + '\n---\n' + q('#omt-diag').textContent; });
    refresh().then(() => setTimeout(autoGet, 3000));   // ページを開いた直後の通信を邪魔しないよう、少し待つ
})();
