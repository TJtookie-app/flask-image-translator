// 画面のタイトル（v1.7.2）: 左上の「丸いアイコン＋名前」を、いまの画面に合わせて入れ替える。
// 名前は、下のナビ・設定の上のボタンと同じ言葉（UI の既存ラベル）。「履歴を消去」は、履歴の一覧のときだけ右端に出る。
const PAGE_TITLES = {
    text: ['fa-pen-to-square', 'nav_text'], image: ['fa-image', 'nav_image'], voice: ['fa-microphone', 'nav_voice'],
    camera: ['fa-camera', 'nav_camera'], conversation: ['fa-comments', 'nav_conversation'], money: ['fa-coins', 'money_title'],
};
const HIST_TITLES = {
    settings: ['fa-gear', 'filter_settings'], all: ['fa-clock-rotate-left', 'nav_history'], fav: ['fa-star', 'filter_fav'],
    gl: ['fa-book', 'filter_glossary'], phrases: ['fa-comment-dots', 'filter_phrases'], study: ['fa-graduation-cap', 'filter_study'],
    trash: ['fa-trash-can', 'filter_trash'],
};

function updatePageTitle() {
    const shown = document.querySelector('.tab-content:not(.hidden)');
    const tab = shown ? shown.id.replace('tab-', '') : 'text';
    const isHist = tab === 'history';
    const def = isHist ? HIST_TITLES[typeof histFilter === 'string' ? histFilter : 'settings'] : PAGE_TITLES[tab];
    if (!def) return;
    const icon = $('page-title-icon'), text = $('page-title-text');
    if (icon) icon.className = 'fa-solid ' + def[0];
    if (text) text.textContent = UI[def[1]] || UI.nav_text || '';
    // 「履歴を消去」の場所は、履歴の一覧のときだけ（そのほかの画面・用語集などでは出さない）
    const act = $('page-title-act');
    if (act) act.classList.toggle('hidden', !(isHist && histFilter !== 'settings' && ['all', 'fav'].includes(histFilter)));
}

(function () {
    if (typeof switchTab === 'function') {     // オフライン画面には、タブの切り替えが無い（履歴と通貨が並ぶ）
        const origTab = switchTab;
        switchTab = function () { const r = origTab.apply(this, arguments); updatePageTitle(); return r; };
    }
    const origHist = renderHistory;
    renderHistory = function () { const r = origHist.apply(this, arguments); updatePageTitle(); return r; };
})();
document.addEventListener('DOMContentLoaded', updatePageTitle);
