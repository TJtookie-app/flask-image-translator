// 通貨タブ（3/4）: 現在地(GPS)・国と自国通貨の選択。money.js の後に読み込む

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
