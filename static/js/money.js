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

// 端末のタイムゾーンから国を決める（許可がいらず、オフラインでも動く。旅行先で端末の時刻が自動で変わればそれに追従する）
function mDetectByTimezone() {
    let tz = '';
    try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) {}
    return moneyGeo.zones[tz] || null;
}
function mApplyAutoWhere() {
    if (moneyState.where && moneyState.where.src !== 'tz') return;   // GPS・手動で決めた国は、そのまま
    const cc = mDetectByTimezone();
    if (cc) moneyState.where = { cc, src: 'tz', at: Date.now() };
}
function mSyncPair() {
    const st = moneyState, local = mLocalCurs();
    if (!st.from) st.from = st.home;
    if (st.toAuto || !st.to) {
        const cand = local.find(c => c !== st.from) || MONEY_DEFAULT_PINS.find(c => c !== st.from) || 'USD';
        st.to = cand;
    }
    if (st.to === st.from) st.to = MONEY_DEFAULT_PINS.find(c => c !== st.from) || 'USD';
}

// ---- 起動 ----
async function initMoney() {
    if (!moneyGeo) {
        try {
            const [c, z] = await Promise.all(['countries', 'zones'].map(n => fetch('/static/money/' + n + '.json').then(r => r.json())));
            moneyGeo = { countries: c, zones: z };
        } catch (e) { moneyGeo = { countries: {}, zones: {} }; }
    }
    moneyState = moneyState || mLoadState();
    if (!moneyState.home || !/^[A-Z]{3}$/.test(moneyState.home)) moneyState.home = mHomeDefault();
    moneyRates = moneyRates || mLoad(RKEY);
    mApplyAutoWhere();
    mSyncPair();
    mSaveState();
    renderMoney();
    refreshRates(false);
}

async function refreshRates(force) {
    if (moneyBusy) return;
    if (typeof navigator !== 'undefined' && navigator.onLine === false) { moneyNet = moneyRates ? 'offline' : 'none'; renderMoney(); return; }
    if (!force && moneyRates && Date.now() - (moneyRates.savedAt || 0) < MONEY_REFRESH_MS) { moneyNet = moneyRates.stale ? 'failed' : 'ok'; renderMoney(); return; }
    moneyBusy = true;
    moneyNet = moneyRates ? 'ok' : 'loading';
    renderMoneyStatus();
    try {
        const r = await fetch('/api/rates', { cache: 'no-store' });
        const data = await r.json();
        if (!r.ok || !data || !data.rates) throw new Error('rates');
        moneyRates = Object.assign({}, data, { savedAt: Date.now() });
        mSave(RKEY, moneyRates);
        moneyNet = data.stale ? 'failed' : 'ok';
    } catch (e) {
        moneyNet = moneyRates ? (navigator.onLine === false ? 'offline' : 'failed') : 'none';
    }
    moneyBusy = false;
    mSyncPair();
    renderMoney();
}
window.addEventListener('online', () => { if (moneyState && $('tab-money') && !$('tab-money').classList.contains('hidden')) refreshRates(true); });
window.addEventListener('offline', () => { if (moneyState) { moneyNet = moneyRates ? 'offline' : 'none'; renderMoneyStatus(); } });

// ---- 現在地(GPS)で国を判定 ----
function mSay(text) {
    const el = $('money-gps-msg');
    el.textContent = text || '';
    el.classList.toggle('hidden', !text);
}

function moneyDetectGps() {
    mSay('');
    if (!navigator.geolocation) { mSay(UI.money_gps_fail); return; }
    if (navigator.onLine === false) { mSay(UI.money_gps_offline); return; }
    const label = $('money-gps').querySelector('span');
    const done = () => { label.textContent = UI.money_gps_btn; $('money-gps').disabled = false; };
    label.textContent = UI.money_gps_busy;
    $('money-gps').disabled = true;
    navigator.geolocation.getCurrentPosition(async (pos) => {
        try {
            // 座標は約1km単位に丸めて、端末から直接送る（TOOKIE のサーバーには送らない・保存しない）
            const q = '?latitude=' + pos.coords.latitude.toFixed(2) + '&longitude=' + pos.coords.longitude.toFixed(2) + '&localityLanguage=en';
            const r = await fetch(GEO_URL + q);
            const j = await r.json();
            const cc = String((j && j.countryCode) || '').toUpperCase();
            if (!r.ok || !moneyGeo.countries[cc]) throw new Error('geo');
            moneyState.where = { cc, src: 'gps', at: Date.now() };
            moneyState.toAuto = true;
            mSyncPair(); mSaveState(); renderMoney();
        } catch (e) { mSay(UI.money_gps_fail); }
        done();
    }, (err) => {
        mSay(err && err.code === 1 ? UI.money_gps_denied : UI.money_gps_fail);
        done();
    }, { enableHighAccuracy: false, timeout: 15000, maximumAge: 10 * 60 * 1000 });
}

function moneyPickCountry(value) {
    mSay('');
    if (!value) { moneyState.where = null; mApplyAutoWhere(); }
    else if (moneyGeo.countries[value]) moneyState.where = { cc: value, src: 'manual', at: Date.now() };
    moneyState.toAuto = true;
    mSyncPair(); mSaveState(); renderMoney();
}

function moneySetHome(code) {
    if (!/^[A-Z]{3}$/.test(code)) return;
    if (moneyState.from === moneyState.home) moneyState.from = code;
    moneyState.home = code;
    mSyncPair(); mSaveState(); renderMoney();
}

// ---- 表示 ----
function mOption(value, text) {
    const o = document.createElement('option');
    o.value = value; o.textContent = text;
    return o;
}

function mFillCurrencySelect(sel, current, firstCodes) {
    const all = mAllCodes();
    const first = [...new Set(firstCodes)].filter(c => all.includes(c));
    sel.replaceChildren();
    first.forEach(c => sel.appendChild(mOption(c, c + ' ' + mCurName(c))));
    if (first.length) sel.appendChild(Object.assign(mOption('', '──────────'), { disabled: true }));
    all.filter(c => !first.includes(c)).forEach(c => sel.appendChild(mOption(c, c + ' ' + mCurName(c))));
    if (current && !all.includes(current)) sel.insertBefore(mOption(current, current + ' ' + mCurName(current)), sel.firstChild);
    sel.value = current;
}

function renderMoneyWhere() {
    const w = moneyState.where, curs = mLocalCurs();
    $('money-flag').textContent = w ? mFlag(w.cc) : '🌍';
    $('money-country').textContent = w ? mRegionName(w.cc) : '';
    $('money-cur').textContent = curs.length ? curs[0] + ' · ' + mCurName(curs[0]) : '—';
    const also = $('money-also');
    also.classList.toggle('hidden', curs.length < 2);
    also.textContent = curs.length > 1 ? UI.money_also + ': ' + curs.slice(1).map(c => c + ' ' + mCurName(c)).join(' / ') : '';
    $('money-src').textContent = !w ? UI.money_where_unknown : w.src === 'gps' ? UI.money_src_gps : w.src === 'manual' ? UI.money_src_manual : UI.money_src_tz;
    // 国の選択肢（画面の言語の名前順）
    const sel = $('money-country-select');
    let coll = null;
    try { coll = new Intl.Collator(mLocale()); } catch (e) {}
    // 国の選択肢: 名前の付かない特殊な地域（ディエゴガルシア島など）は出さず、名前が取れない国は末尾へ
    const ccs = Object.keys(moneyGeo.countries).filter(cc => /^[A-Z]{2}$/.test(cc) && !MONEY_HIDE_COUNTRIES.includes(cc))
        .map(cc => [cc, mRegionName(cc)]).sort((a, b) => {
            const ua = a[1] === a[0], ub = b[1] === b[0];
            if (ua !== ub) return ua ? 1 : -1;
            return coll ? coll.compare(a[1], b[1]) : a[1].localeCompare(b[1]);
        });
    sel.replaceChildren(mOption('', UI.money_country_auto), ...ccs.map(([cc, n]) => mOption(cc, mFlag(cc) + ' ' + n)));
    sel.value = w && w.src === 'manual' ? w.cc : '';
}

function renderMoneyStatus() {
    const el = $('money-status');
    const t = moneyRates ? mTime(moneyRates.updated) : '';
    let msg = '';
    if (moneyNet === 'loading') msg = UI.money_loading;
    else if (moneyNet === 'none' || !moneyRates) msg = UI.money_none;
    else if (moneyNet === 'offline') msg = fmt(UI.money_offline_saved, { t });
    else if (moneyNet === 'failed') msg = fmt(UI.money_stale, { t });
    else msg = fmt(UI.money_updated, { t });
    el.textContent = msg;
    el.classList.toggle('text-amber-200', moneyNet === 'offline' || moneyNet === 'failed' || moneyNet === 'none');
    const credit = $('money-credit');
    if (moneyRates && moneyRates.attribution && /^https:\/\//.test(moneyRates.attribution)) {
        credit.href = moneyRates.attribution;
        credit.textContent = moneyRates.source === 'frankfurter.dev (ECB)' ? 'Frankfurter (ECB)' : 'Exchange Rate API';
    }
}

function moneyConvert(fromSelect) {
    const st = moneyState;
    if (fromSelect) {
        st.from = $('money-from').value || st.from;
        st.to = $('money-to').value || st.to;
        st.toAuto = false;
    }
    st.amount = $('money-amount').value;
    mSaveState();
    const amount = mParseAmount(st.amount), v = mRate(st.from, st.to);
    $('money-result').textContent = amount === null ? '—' : v === null ? UI.money_no_rate : mMoney(amount * v, st.to);
    $('money-rate-line').textContent = mPairText(st.from, st.to);
}

function moneySwap() {
    const st = moneyState;
    [st.from, st.to] = [st.to, st.from];
    st.toAuto = false;
    mSaveState();
    renderMoneyConverter();
}

function renderMoneyConverter() {
    const st = moneyState, local = mLocalCurs();
    const priority = [st.home, ...local, ...st.pins];
    mFillCurrencySelect($('money-home'), st.home, [st.home, ...local, ...MONEY_DEFAULT_PINS]);
    mFillCurrencySelect($('money-from'), st.from, priority);
    mFillCurrencySelect($('money-to'), st.to, priority);
    $('money-amount').value = st.amount;
    moneyConvert(false);
}

function mRow(code, { local, pinned, onTap, onPin }) {
    const row = document.createElement('div');
    row.className = 'money-row';
    const tap = document.createElement('button');
    tap.type = 'button';
    tap.className = 'money-row-main';
    tap.addEventListener('click', onTap);
    const l = document.createElement('div');
    l.className = 'min-w-0 text-left';
    const c = document.createElement('div');
    c.className = 'text-sm font-bold text-slate-100';
    c.textContent = (local ? '📍 ' : '') + code;
    const n = document.createElement('div');
    n.className = 'text-xs text-slate-400 truncate';
    n.textContent = mCurName(code);
    l.append(c, n);
    const v = document.createElement('div');
    v.dir = 'auto';
    v.className = 'text-sm font-semibold text-amber-200 text-right';
    v.textContent = mPairText(code, moneyState.home);
    tap.append(l, v);
    row.appendChild(tap);
    if (onPin) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'money-pin';
        b.setAttribute('aria-label', pinned ? UI.money_remove : UI.money_add);
        b.textContent = pinned ? '✕' : '＋';
        b.addEventListener('click', onPin);
        row.appendChild(b);
    }
    return row;
}

// 一覧の行をタップすると、「あなたの通貨 → その通貨」の換算に切り替える
function mUseForConvert(code) {
    const st = moneyState;
    st.from = st.home; st.to = code; st.toAuto = false;
    mSaveState();
    renderMoneyConverter();
    $('money-amount').scrollIntoView({ block: 'center', behavior: 'smooth' });
}

function mTogglePin(code) {
    const st = moneyState, i = st.pins.indexOf(code);
    if (i >= 0) st.pins.splice(i, 1); else st.pins.push(code);
    mSaveState();
    renderMoneyList();
    moneySearch();
}

function renderMoneyList() {
    const st = moneyState, local = mLocalCurs();
    const list = $('money-list');
    list.replaceChildren();
    const codes = [...new Set([...local, ...st.pins])].filter(c => c !== st.home);
    codes.forEach(c => list.appendChild(mRow(c, {
        local: local.includes(c), pinned: st.pins.includes(c),
        onTap: () => mUseForConvert(c),
        onPin: st.pins.includes(c) ? () => mTogglePin(c) : null,
    })));
}

function moneySearch() {
    const box = $('money-search-results');
    const q = $('money-search').value.trim().toLowerCase();
    box.replaceChildren();
    if (!q) return;
    let en = null;
    try { en = new Intl.DisplayNames(['en'], { type: 'currency' }); } catch (e) {}
    const hits = mAllCodes().filter(c => c !== moneyState.home && (c.toLowerCase().includes(q) ||
        mCurName(c).toLowerCase().includes(q) || (en && (en.of(c) || '').toLowerCase().includes(q)))).slice(0, 20);
    if (!hits.length) {
        const p = document.createElement('p');
        p.className = 'text-xs text-slate-400';
        p.textContent = UI.money_no_match;
        box.appendChild(p);
        return;
    }
    hits.forEach(c => box.appendChild(mRow(c, {
        local: false, pinned: moneyState.pins.includes(c),
        onTap: () => mUseForConvert(c),
        onPin: () => mTogglePin(c),
    })));
}

function renderMoney() {
    if (!moneyState || !moneyGeo || !$('tab-money')) return;
    renderMoneyWhere();
    renderMoneyConverter();
    renderMoneyList();
    moneySearch();
    renderMoneyStatus();
}
