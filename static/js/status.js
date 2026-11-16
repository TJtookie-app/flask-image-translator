// 翻訳が遅いときの案内（段階表示）と、今日の残り回数の表示
const WAIT_SLOW_MS = 6000;      // 6秒たっても終わらないとき: サーバー起動中・混雑の案内
const WAIT_SLOWER_MS = 25000;   // 25秒たっても終わらないとき: 閉じずに待つ案内
let waitTimers = [];

function stopWaitNotice() {
    waitTimers.forEach(clearTimeout);
    waitTimers = [];
    document.querySelectorAll('.wait-note').forEach(n => n.classList.add('hidden'));
}

function startWaitNotice(form) {
    stopWaitNotice();
    let note = form.querySelector('.wait-note');
    if (!note) {
        note = document.createElement('p');
        note.className = 'wait-note hidden';
        note.setAttribute('role', 'status');
        note.setAttribute('aria-live', 'polite');
        form.appendChild(note);
    }
    waitTimers = [
        setTimeout(() => { note.textContent = UI.wait_slow; note.classList.remove('hidden'); }, WAIT_SLOW_MS),
        setTimeout(() => { note.textContent = UI.wait_slower; }, WAIT_SLOWER_MS),
    ];
}

// 戻るボタンで画面が復元されたとき、「翻訳中…」のまま押せなくならないよう元に戻す
function resetSubmitButtons() {
    document.querySelectorAll('form.tx-form').forEach(form => {
        form.querySelectorAll('button[type=submit]').forEach(b => { b.disabled = false; b.classList.remove('opacity-60'); });
        const label = form.querySelector('button[type=submit] .btn-label');
        if (label && label.dataset.label) label.textContent = label.dataset.label;
    });
    stopWaitNotice();
}

// サイト全体の「今日の残り回数」。無料枠で運営している（上限が小さい）ときだけ表示する
async function refreshQuota() {
    const el = $('quota-note');
    if (!el) return;
    try {
        const r = await fetch('/api/quota', { cache: 'no-store', credentials: 'same-origin' });
        if (!r.ok) return;
        const q = await r.json();
        if (!q.show) { el.classList.add('hidden'); return; }
        el.textContent = q.remaining > 0 ? fmt(UI.quota_left_n, { n: q.remaining }) : UI.quota_none;
        el.classList.toggle('low', q.remaining > 0 && q.remaining <= 3);
        el.classList.toggle('none', q.remaining === 0);
        el.classList.remove('hidden');
    } catch (e) { /* 通信できないとき（オフラインなど）は何も出さない */ }
}

window.addEventListener('pageshow', e => { if (e.persisted) { resetSubmitButtons(); refreshQuota(); } });
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') refreshQuota(); });
document.addEventListener('DOMContentLoaded', refreshQuota);
