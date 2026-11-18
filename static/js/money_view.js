// 通貨タブ（4/4）: 換算・一覧・検索の表示。money.js の後に読み込む

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
