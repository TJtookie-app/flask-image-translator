// 設定の「翻訳メモリー」と「自動ダウンロード」のスイッチ（v1.10.0）
(function () {
    const tm = document.getElementById('set-tm'), auto = document.getElementById('set-auto-model');
    const count = document.getElementById('tm-count'), clear = document.getElementById('tm-clear');
    if (!tm || !auto) return;
    const st = loadSettings();
    tm.checked = st.tm; auto.checked = st.autoModel;
    const paint = () => { if (count) count.textContent = UI.tm_count.replace('{n}', String(tmCount())); };
    const set = (k, v) => { const s = loadSettings(); s[k] = v; saveSettings(s); };
    tm.addEventListener('change', () => set('tm', tm.checked));
    auto.addEventListener('change', () => {
        set('autoModel', auto.checked);
        if (auto.checked) document.dispatchEvent(new Event('omt-auto-on'));
    });
    if (clear) clear.addEventListener('click', () => {
        if (!tmCount() || !window.confirm(UI.tm_confirm_clear)) return;
        tmClear(); paint();
    });
    window.addEventListener('storage', paint);
    if (typeof setHistFilter === 'function') {   // 設定を開く（履歴の絞り込みを切り替える）たびに、件数を数え直す
        const orig = setHistFilter;
        window.setHistFilter = function () { const r = orig.apply(this, arguments); paint(); return r; };
    }
    if (count && window.IntersectionObserver) new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) paint(); }).observe(count);   // 設定を開いたとき（表示されたとき）に、件数を数え直す
    paint();
})();
