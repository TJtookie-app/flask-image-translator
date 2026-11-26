// 控えめな動き（v1.7.1）: 下のナビの「丸い面」が動く／翻訳を待つあいだの読み込み枠／言語入れ替えの半回転。動きを減らす設定のときは、CSS 側で止まる

// 下のナビ: 選択中のタブの位置と幅を、CSS の変数に入れる（丸い面は、CSS の transition で動く）
function movePill() {
    const bar = document.querySelector('.bottom-nav-in');
    const act = bar && bar.querySelector('.nav-btn[class*="text-indigo-400"]');
    if (!act) return;
    bar.style.setProperty('--pill-x', act.offsetLeft + 'px');
    bar.style.setProperty('--pill-w', act.offsetWidth + 'px');
    bar.style.setProperty('--pill-o', '1');
}

(function () {
    const orig = switchTab;
    switchTab = function () { const r = orig.apply(this, arguments); movePill(); return r; };
})();

document.addEventListener('DOMContentLoaded', () => {
    movePill();
    const bar = document.querySelector('.bottom-nav-in');
    // 最初の位置合わせは動かさない。そのあとだけ、すっと動く
    if (bar) requestAnimationFrame(() => requestAnimationFrame(() => bar.classList.add('pill-ready')));
    window.addEventListener('resize', movePill);
    window.addEventListener('orientationchange', movePill);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(movePill);

    const swap = document.getElementById('swap-lang-container');
    if (swap) swap.addEventListener('submit', () => swap.classList.add('swapping'));
});

// 翻訳を待つあいだ、結果が出る場所に薄い枠を出す（送信が止められたときは出さない）
document.addEventListener('submit', ev => {
    if (ev.defaultPrevented) return;
    const form = ev.target.closest && ev.target.closest('form.tx-form');
    if (!form || (form.parentElement && form.parentElement.querySelector('.sk-box'))) return;
    const box = document.createElement('div');
    box.className = 'sk-box';
    box.setAttribute('aria-hidden', 'true');
    for (let i = 0; i < 3; i++) { const l = document.createElement('div'); l.className = 'sk-line'; box.appendChild(l); }
    form.insertAdjacentElement('afterend', box);
});
window.addEventListener('pageshow', () => document.querySelectorAll('.sk-box').forEach(x => x.remove()));
