// 通貨タブ（1/4）: 定数・状態・表示用の整形・設定の読み書き。続きは money_start.js / money_where.js / money_view.js
// 通貨・為替タブ: 現在地の通貨（端末の時刻設定／現在地(GPS)／手動）、換算、主な通貨の一覧。
// レートは /api/rates（サーバーが数時間ごとに取得）。取れたレートは端末に保存し、オフラインでは最後のレートを出す。
// 国の判定に使うデータは static/money/*.json（tools/build_money_data.py で作成。Service Worker が端末に保存するのでオフラインでも読める）
const MKEY = 'tl_money_v1';   // 設定: { home, from, to, toAuto, amount, pins, where: { cc, src, at } }
const RKEY = 'tl_rates_v1';   // 最後に取得したレート: { base, rates, updated, fetched, source, attribution, stale, savedAt }
const MONEY_DEFAULT_PINS = ['USD', 'EUR', 'GBP', 'CNY', 'KRW', 'TWD', 'HKD', 'THB', 'SGD', 'AUD', 'CAD', 'CHF'];
const MONEY_HIDE_COUNTRIES = ['EU', 'DG', 'EA', 'IC', 'TA'];   // 国の一覧には出さない（EU・ディエゴガルシア島・セウタとメリリャ・カナリア諸島・トリスタンダクーニャ）
const MONEY_REFRESH_MS = 30 * 60 * 1000;     // この時間内に取得したレートは、開き直しても取り直さない
const GEO_URL = 'https://api.bigdatacloud.net/data/reverse-geocode-client';   // 現在地→国。端末から直接呼ぶ（キー不要・クライアント専用）

let moneyGeo = null;       // { countries: {JP: ['JPY']}, zones: {'Asia/Tokyo': 'JP'} }
let moneyRates = null;
let moneyState = null;
let moneyNet = 'loading';  // loading / ok（取得できた）/ failed（更新できず前回の値）/ offline / none（レートなし）
let moneyBusy = false;

// ---- 保存 ----
function mLoad(key) {
    try { const v = JSON.parse(localStorage.getItem(key) || 'null'); return v && typeof v === 'object' ? v : null; } catch (e) { return null; }
}
function mSave(key, v) { try { localStorage.setItem(key, JSON.stringify(v)); } catch (e) {} }

// ---- 表示用の小さな道具（言語名・通貨名・数字は、ブラウザ標準の Intl で画面の言語に合わせる） ----
const mLocale = () => (typeof codeOf === 'function' && codeOf(UI_LANG)) || 'en-US';
function mNames(type) { try { return new Intl.DisplayNames([mLocale()], { type }); } catch (e) { return null; } }
function mRegionName(cc) { const n = mNames('region'); try { return (n && n.of(cc)) || cc; } catch (e) { return cc; } }
function mCurName(code) { const n = mNames('currency'); try { return (n && n.of(code)) || code; } catch (e) { return code; } }
function mFlag(cc) {
    if (!/^[A-Z]{2}$/.test(cc || '')) return '🌍';
    return String.fromCodePoint(...[...cc].map(c => 0x1F1E6 + c.charCodeAt(0) - 65));
}
function mNum(x, maxDigits) {
    try { return new Intl.NumberFormat(mLocale(), { maximumFractionDigits: maxDigits }).format(x); } catch (e) { return String(x); }
}
// レートのような数字: 大きいほど桁を減らし、小さい数は細かく見せる
function mSmart(x) { return mNum(x, x >= 1000 ? 0 : x >= 100 ? 1 : x >= 1 ? 2 : x >= 0.01 ? 4 : 6); }
function mMoney(x, cur) {
    try {
        return new Intl.NumberFormat(mLocale(), { style: 'currency', currency: cur, maximumFractionDigits: x > 0 && x < 1 ? 4 : undefined }).format(x);
    } catch (e) { return mSmart(x) + ' ' + cur; }
}
function mTime(iso) {
    try { return new Date(iso).toLocaleString(mLocale(), { dateStyle: 'medium', timeStyle: 'short' }); } catch (e) { return String(iso || ''); }
}
// 全角の数字・カンマ・ピリオドも読む（"１,０００.５" → 1000.5）
function mParseAmount(text) {
    let t = String(text || '').normalize('NFKC').replace(/[\s,、，]/g, '');
    if (!/^\d*\.?\d*$/.test(t) || t === '' || t === '.') return null;
    const v = parseFloat(t);
    return Number.isFinite(v) ? v : null;
}

// ---- レート ----
const mRate = (from, to) => {
    const r = moneyRates && moneyRates.rates;
    return r && r[from] && r[to] ? r[to] / r[from] : null;
};
// 「1 USD = 154.3 JPY」のように見せる。値が小さすぎるときは 100 や 1000 単位にする
function mPair(from, to) {
    const v = mRate(from, to);
    if (v === null) return null;
    let unit = 1;
    while (v * unit < 1 && unit < 100000) unit *= 10;
    return { unit, value: v * unit };
}
function mPairText(from, to) {
    const p = mPair(from, to);
    return p ? mNum(p.unit, 0) + ' ' + from + ' = ' + mSmart(p.value) + ' ' + to : UI.money_no_rate;
}
function mAllCodes() {
    if (moneyRates && moneyRates.rates) return Object.keys(moneyRates.rates).sort();
    const s = new Set();
    Object.values((moneyGeo && moneyGeo.countries) || {}).forEach(a => a.forEach(c => s.add(c)));
    return [...s].sort();
}

// ---- 設定 ----
function mHomeDefault() {
    const region = (mLocale().split('-')[1] || '').toUpperCase();
    const c = moneyGeo && moneyGeo.countries[region];
    return (c && c[0]) || 'USD';
}
function mLoadState() {
    const s = mLoad(MKEY) || {};
    const pins = Array.isArray(s.pins) ? s.pins.filter(c => /^[A-Z]{3}$/.test(c)) : MONEY_DEFAULT_PINS.slice();
    return {
        home: /^[A-Z]{3}$/.test(s.home || '') ? s.home : mHomeDefault(),
        from: /^[A-Z]{3}$/.test(s.from || '') ? s.from : '',
        to: /^[A-Z]{3}$/.test(s.to || '') ? s.to : '',
        toAuto: s.toAuto !== false,
        amount: typeof s.amount === 'string' ? s.amount : '1000',
        pins,
        where: s.where && /^[A-Z]{2}$/.test(s.where.cc || '') ? s.where : null,
    };
}
const mSaveState = () => mSave(MKEY, moneyState);
const mLocalCurs = () => {
    const w = moneyState.where;
    return (w && moneyGeo.countries[w.cc]) || [];
};
