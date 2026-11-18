// 通貨タブ（2/4）: 国と通貨ペアの初期設定・起動・レート取得。money.js の後に読み込む

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
