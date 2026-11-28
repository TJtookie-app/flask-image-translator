// 表示・翻訳の設定（丁寧さ・読み方・文字サイズ・配色）。この端末の localStorage に保存する
const SKEY = 'tl_settings_v1';
const SETTING_DEFAULTS = { formality: 'auto', pron: true, fs: 'm', theme: 'dark', contrast: false, tm: true, autoModel: false };
const SETTING_CHOICES = { formality: ['auto', 'natural', 'literal', 'formal', 'business'], fs: ['m', 'l', 'xl'], theme: ['dark', 'light', 'auto'] };

function loadSettings() {
    const st = Object.assign({}, SETTING_DEFAULTS);
    try {
        const saved = JSON.parse(localStorage.getItem(SKEY) || '{}') || {};
        Object.keys(SETTING_CHOICES).forEach(k => { if (SETTING_CHOICES[k].indexOf(saved[k]) >= 0) st[k] = saved[k]; });
        if (typeof saved.pron === 'boolean') st.pron = saved.pron;
        if (typeof saved.contrast === 'boolean') st.contrast = saved.contrast;
        if (typeof saved.tm === 'boolean') st.tm = saved.tm;                      // 翻訳メモリーを使う（既定: 使う）
        if (typeof saved.autoModel === 'boolean') st.autoModel = saved.autoModel;   // オフライン翻訳のモデルを、自動でダウンロード（既定: しない）
    } catch (e) {}
    return st;
}

function saveSettings(st) {
    try { localStorage.setItem(SKEY, JSON.stringify(st)); } catch (e) {}
}

// 実際に使う配色（「自動」のときは、端末の設定に合わせる）
function effectiveTheme(st) {
    if (st.theme === 'auto') {
        try { return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'; } catch (e) { return 'dark'; }
    }
    return st.theme === 'light' ? 'light' : 'dark';
}

function applySettings(st) {
    const d = document.documentElement;
    const theme = effectiveTheme(st);
    if (theme === 'light') d.setAttribute('data-theme', 'light'); else d.removeAttribute('data-theme');
    if (st.contrast) d.setAttribute('data-contrast', 'high'); else d.removeAttribute('data-contrast');
    d.removeAttribute('data-bg'); d.removeAttribute('data-accent');   // v1.7.4: 背景・アクセント色の選択は取りやめた（v1.7.3 で付いた属性が残らないように消す）
    if (st.fs === 'l' || st.fs === 'xl') {
        d.setAttribute('data-fs', st.fs);
        d.style.fontSize = st.fs === 'xl' ? '128%' : '114%';
    } else {
        d.removeAttribute('data-fs');
        d.style.fontSize = '';
    }
    const meta = document.querySelector('meta[name=theme-color]');
    if (meta) meta.setAttribute('content', theme === 'light' ? '#F4F0E8' : '#0B1020');
}

function renderSettings() {
    const st = loadSettings();
    document.querySelectorAll('#settings-section [data-setting]').forEach(group => {
        const key = group.getAttribute('data-setting');
        group.querySelectorAll('button[data-v]').forEach(b => {
            const on = b.getAttribute('data-v') === st[key];
            b.setAttribute('aria-pressed', on ? 'true' : 'false');
            b.className = 'set-opt px-2 py-2 rounded-xl text-xs font-semibold border border-slate-700 transition ' +
                (on ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-300');
        });
    });
    const pron = document.getElementById('set-pron');
    if (pron) pron.checked = !!st.pron;
    const con = document.getElementById('set-contrast');
    if (con) con.checked = !!st.contrast;
}

function bindSettings() {
    document.querySelectorAll('#settings-section [data-setting]').forEach(group => {
        const key = group.getAttribute('data-setting');
        group.addEventListener('click', ev => {
            const b = ev.target.closest('button[data-v]');
            if (!b) return;
            const st = loadSettings();
            st[key] = b.getAttribute('data-v');
            saveSettings(st);
            applySettings(st);
            renderSettings();
        });
    });
    const pron = document.getElementById('set-pron');
    if (pron) pron.addEventListener('change', () => {
        const st = loadSettings();
        st.pron = pron.checked;
        saveSettings(st);
    });
    const con = document.getElementById('set-contrast');
    if (con) con.addEventListener('change', () => {
        const st = loadSettings();
        st.contrast = con.checked;
        saveSettings(st);
        applySettings(st);
    });
    try {   // 「自動」のとき、端末の設定が変わったら、すぐ反映する
        const mq = window.matchMedia('(prefers-color-scheme: light)');
        const on = () => { const st = loadSettings(); if (st.theme === 'auto') applySettings(st); };
        if (mq.addEventListener) mq.addEventListener('change', on); else if (mq.addListener) mq.addListener(on);
    } catch (e) {}
}

document.addEventListener('DOMContentLoaded', () => {
    applySettings(loadSettings());
    bindSettings();
    renderSettings();
});
