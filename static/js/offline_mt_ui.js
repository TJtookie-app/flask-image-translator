// オフライン翻訳（試作）の設定カード: ダウンロード・削除・試し翻訳・診断
(function () {
    const card = document.getElementById('omt-card');
    if (!card || typeof OfflineMT === 'undefined') return;
    const q = (sel, root) => (root || card).querySelector(sel);
    const rows = Array.from(card.querySelectorAll('.omt-row'));
    const packs = Array.from(card.querySelectorAll('.omt-pack'));
    const addBox = q('#omt-add'), addSel = q('#omt-add-sel'), addBtn = q('#omt-add-btn');
    const ready = {}, added = new Set();   // added: この画面で「言語を追加」した言語（ダウンロードが終わるまで、並べておく）
    let busy = false, loading = '';   // loading: ダウンロード中の方向
    const packOf = (pair) => rowOf(pair).closest('.omt-pack').dataset.pack;
    const pairsOf = (pk) => rows.filter((r) => packOf(r.dataset.pair) === pk).map((r) => r.dataset.pair);
    const shown = (pk) => pk && (card.querySelector('.omt-pack[data-pack="' + pk + '"]').dataset.base || added.has(pk) || pairsOf(pk).some((x) => ready[x] || loading === x));

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
        addSel.addEventListener('change', paintPacks);
    addBtn.addEventListener('click', addPack);
    card.querySelectorAll('.omt-run').forEach((b) => { b.disabled = busy || !ready[b.dataset.omtRun]; b.classList.toggle('hidden', !ready[b.dataset.omtRun]); });   // 入れた方向のボタンだけ並べる
    }

    // ダウンロード済み（または追加した）言語だけを並べる。残りは「言語を追加」の選択欄に入れる
    function paintPacks() {
        packs.forEach((el) => el.classList.toggle('hidden', !shown(el.dataset.pack)));
        addSel.addEventListener('change', paintPacks);
    addBtn.addEventListener('click', addPack);
        Array.from(addSel.options).forEach((o) => { if (o.value) { o.hidden = o.disabled = shown(o.value); } });
        if (addSel.value && shown(addSel.value)) addSel.value = '';
        addBox.classList.toggle('hidden', Array.from(addSel.options).every((o) => !o.value || o.hidden));
        addBtn.disabled = busy || !addSel.value;
    }

    function paintAll() { rows.forEach((r) => paint(r.dataset.pair)); paintPacks(); }

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
        if (!pairsOf(packOf(pair)).some((x) => ready[x])) { added.delete(packOf(pair)); paintPacks(); }
    }

    // 言語を追加: その言語の、足りない方向を順に入れる（途中で失敗したら止める。ボタンから続きをやり直せる）
    async function addPack() {
        const pk = addSel.value;
        if (!pk || busy) return;
        added.add(pk); addSel.value = ''; paintAll();
        for (const pair of pairsOf(pk)) {
            if (ready[pair]) continue;
            await get(pair);
            if (!ready[pair]) break;
        }
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
    addSel.addEventListener('change', paintPacks);
    addBtn.addEventListener('click', addPack);
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
