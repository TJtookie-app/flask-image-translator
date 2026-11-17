"""V12.7: 通貨タブ（為替レートの取得と保存、国の判定データ、画面の部品）"""
import json
import os
import re

import pytest

from conftest import start, ROOT

PRIMARY = {"result": "success", "time_last_update_unix": 1794900000, "base_code": "USD",
           "rates": {**{f"C{chr(65 + i // 26)}{chr(65 + i % 26)}": 1.5 + i for i in range(60)}, "USD": 1, "JPY": 154.3, "EUR": 0.92}}
FALLBACK = {"amount": 1.0, "base": "USD", "date": "2026-11-16",
            "rates": {**{f"F{chr(65 + i // 26)}{chr(65 + i % 26)}": 2.5 + i for i in range(12)}, "JPY": 155.0, "EUR": 0.93}}


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


@pytest.fixture()
def net(env):
    """外のAPIの代わり。net.calls に取りに行ったURLが入る。net.responses[url始まり] = 返す内容 / 例外"""
    import rates

    class Net:
        calls = []
        responses = {"https://open.er-api.com": PRIMARY, "https://api.frankfurter.dev": FALLBACK}

    n = Net(); n.calls = []

    def fake_get(url):
        n.calls.append(url)
        for prefix, resp in n.responses.items():
            if url.startswith(prefix):
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(url)
    env[3].setattr(rates, "_http_get", fake_get)
    n.app, n.rates, n.mp = env[0], rates, env[3]
    return n


# ---------------- レートの取得・保存 ----------------
def test_fetch_and_cache(net):
    d = net.rates.store.get()
    assert d["base"] == "USD" and d["rates"]["JPY"] == 154.3 and d["rates"]["USD"] == 1.0
    assert d["stale"] is False and d["source"] == "exchangerate-api.com" and d["attribution"].startswith("https://")
    assert d["updated"].endswith("Z") and d["fetched"].endswith("Z")
    net.rates.store.get(); net.rates.store.get()
    assert len(net.calls) == 1                      # 保存した値を返すだけ。外のAPIへは1回だけ


def test_refetch_after_ttl(net):
    net.mp.setenv("RATES_TTL_SEC", "0")
    net.rates.store.get(); net.rates.store.get()
    assert len(net.calls) == 2


def test_fallback_when_primary_fails(net):
    net.responses["https://open.er-api.com"] = ConnectionError("down")
    d = net.rates.store.get()
    assert d["rates"]["JPY"] == 155.0 and d["rates"]["USD"] == 1.0 and d["source"].startswith("frankfurter")
    assert d["updated"] == "2026-11-16T00:00:00Z"
    assert len(net.calls) == 2


def test_fallback_can_be_disabled(net):
    net.mp.setenv("RATES_FALLBACK_URL", "")
    net.responses["https://open.er-api.com"] = ConnectionError("down")
    with pytest.raises(net.rates.RatesUnavailable):
        net.rates.store.get()
    assert len(net.calls) == 1


def test_bad_payloads_are_rejected(net):
    for bad in ({"result": "error"}, {"result": "success", "rates": {"JPY": 1}}, {"result": "success", "rates": "x"}, ["x"]):
        net.rates.store.reset(); net.calls.clear()
        net.responses["https://open.er-api.com"] = bad
        net.responses["https://api.frankfurter.dev"] = {"rates": {}}
        with pytest.raises(net.rates.RatesUnavailable):
            net.rates.store.get()


def test_clean_rates():
    from rates import clean_rates
    out = clean_rates({"jpy": 150, "EUR": 0.9, "XXXX": 1, "AB": 1, "NEG": -1, "ZER": 0, "STR": "1", "BOO": True,
                       "NAN": float("nan"), "INF": float("inf"), "USD": 5}, 3)
    assert out == {"JPY": 150.0, "EUR": 0.9, "USD": 1.0}          # 壊れた値は捨て、USD は必ず 1
    assert clean_rates({"JPY": 1}, 5) is None and clean_rates(None, 1) is None


def test_stale_value_when_refresh_fails(net):
    net.mp.setenv("RATES_TTL_SEC", "0")
    net.rates.store.get()
    net.responses["https://open.er-api.com"] = ConnectionError("down")
    net.responses["https://api.frankfurter.dev"] = ConnectionError("down")
    d = net.rates.store.get()
    assert d["stale"] is True and d["rates"]["JPY"] == 154.3        # 前回の値を、stale 付きで返す


def test_backoff_after_failure(net):
    net.responses["https://open.er-api.com"] = ConnectionError("down")
    net.responses["https://api.frankfurter.dev"] = ConnectionError("down")
    for _ in range(3):
        with pytest.raises(net.rates.RatesUnavailable):
            net.rates.store.get()
    assert len(net.calls) == 2                                      # 失敗した直後は取りに行き直さない（待たされる人を増やさない）


# ---------------- /api/rates ----------------
def test_api_rates_ok_and_not_counted(net):
    from limits import limiter
    c = net.app.test_client(); start(c, "Japanese")
    r = c.get("/api/rates")
    j = r.get_json()
    assert r.status_code == 200 and j["rates"]["JPY"] == 154.3 and j["stale"] is False
    assert r.headers["Cache-Control"] == "no-store"
    assert limiter.quota()["used"] == 0                             # Gemini の残り回数には数えない


def test_api_rates_503_in_ui_language(net):
    net.responses["https://open.er-api.com"] = ConnectionError("down")
    net.responses["https://api.frankfurter.dev"] = ConnectionError("down")
    c = net.app.test_client(); start(c, "Japanese")
    r = c.get("/api/rates")
    assert r.status_code == 503 and r.get_json()["error"] == "為替レートを取得できませんでした。"
    start(c, "English")
    assert c.get("/api/rates").get_json()["error"] == "Could not get the exchange rates."


# ---------------- 同梱データ ----------------
def _data():
    return (json.loads(read("static", "money", "countries.json")), json.loads(read("static", "money", "zones.json")))


def test_money_data_is_consistent():
    countries, zones = _data()
    assert len(countries) > 200 and len(zones) > 400
    for cc, curs in countries.items():
        assert re.fullmatch(r"[A-Z]{2}", cc) and 1 <= len(curs) <= 2 and all(re.fullmatch(r"[A-Z]{3}", c) for c in curs), cc
    for zone, cc in zones.items():
        assert cc in countries, (zone, cc)                          # タイムゾーンが指す国は、必ず通貨の表にある
    assert countries["JP"] == ["JPY"] and countries["US"] == ["USD"] and countries["FR"] == ["EUR"] and countries["GB"] == ["GBP"]
    assert countries["PA"][0] == "USD" and countries["KH"] == ["KHR", "USD"] and countries["BG"] == ["EUR"] and countries["HR"] == ["EUR"]
    assert zones["Asia/Tokyo"] == "JP" and zones["Europe/Paris"] == "FR" and zones["America/New_York"] == "US"
    assert zones["Asia/Calcutta"] == "IN" and zones["Asia/Kolkata"] == "IN"     # 古い名前も同じ国
    assert zones["Asia/Saigon"] == "VN" and zones["Europe/Kiev"] == "UA" and zones["Pacific/Honolulu"] == "US"
    assert len(json.dumps(zones)) < 40000                           # 端末に保存する量は小さく


def test_every_supported_ui_language_region_has_a_currency():
    """画面の言語の地域（ja-JP の JP など）から「あなたの通貨」の初期値を決めるので、どれも表にあること"""
    import languages
    countries, _ = _data()
    for l in languages.LANGUAGES:
        region = l["code"].split("-")[1]
        assert region in countries, l["code"]


# ---------------- 画面の部品 ----------------
def test_money_tab_markup_and_nav(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    for needle in ("tab-money", "money-flag", "money-country-select", "money-gps", "money-amount", "money-from", "money-to",
                   "money-result", "money-list", "money-search", "money-status", "money-credit", "nav-money", "js/money.js",
                   "通貨・為替", "現在地で判定", "銀行間の目安"):
        assert needle in html, needle
    assert html.count("onclick=\"switchTab('") >= 7          # 下のバー6つ + ヘッダーの通貨ボタン
    assert html.index("js/money.js") < html.index("js/app.js")
    off = c.get("/offline").get_data(as_text=True)
    assert "tab-money" in off and "js/money.js" in off
    sw = c.get("/sw.js").get_data(as_text=True)
    assert "money/countries.json" in sw and "money/zones.json" in sw      # オフラインでも国の判定データが読める


def test_switch_tab_wiring():
    js = read("static", "js", "app.js")
    assert "tabName === 'money'" in js and "initMoney()" in js
    assert re.search(r"ownLang = \(.*'money'", js)                      # 通貨タブでは、翻訳の言語バーを隠す
    off = read("static", "js", "offline.js")
    assert "initMoney()" in off and "tab-money" in off


def test_money_js_key_points():
    js = read("static", "js", "money.js")
    for needle in ("tl_money_v1", "tl_rates_v1", "/api/rates", "resolvedOptions().timeZone", "navigator.geolocation",
                   "api.bigdatacloud.net/data/reverse-geocode-client", "toFixed(2)", "Intl.DisplayNames", "enableHighAccuracy: false",
                   "online", "offline", "mParseAmount", "MONEY_REFRESH_MS"):
        assert needle in js, needle
    # 座標は TOOKIE のサーバーへ送らない（外部サービスへ端末から直接）
    assert "fetch('/api/" not in js.replace("fetch('/api/rates'", "")
    assert "innerHTML" not in js                                         # 表示は textContent で組み立てる


def test_money_labels_in_both_languages():
    import languages
    ja, en = languages.UI_LABELS["Japanese"], languages.UI_LABELS["English"]
    keys = [k for k in ja if k.startswith("money_")] + ["nav_money", "err_rates", "privacy_body_7"]
    assert len([k for k in keys if k.startswith("money_")]) >= 30
    for k in keys:
        assert ja.get(k) and en.get(k), k
    for k in ("money_updated", "money_offline_saved", "money_stale"):
        assert "{t}" in ja[k] and "{t}" in en[k], k


def test_privacy_mentions_location_and_rates(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/privacy").get_data(as_text=True)
    assert "BigDataCloud" in html and "約1km" in html and "為替レート" in html
    start(c, "English")
    en = c.get("/privacy").get_data(as_text=True)
    assert "BigDataCloud" in en and "1 km" in en


def test_readme_env_vars_documented():
    readme = read("README.md")
    for needle in ("RATES_URL", "RATES_FALLBACK_URL", "RATES_TTL_SEC", "build_money_data.py"):
        assert needle in readme, needle


def test_geolocation_allowed_for_own_pages(env):
    """「現在地で判定」が動くには、Permissions-Policy が現在地を許可している必要がある（以前は禁止していた）"""
    app, *_ = env
    h = app.test_client().get("/").headers["Permissions-Policy"]
    assert "geolocation=(self)" in h and "camera=(self)" in h


def test_country_select_is_readable_and_tidy():
    css = read("static", "style.css")
    assert ".money-select option" in css and "color-scheme: dark" in css      # 開いたリストが白背景＋薄い文字にならない
    assert "html[data-theme=light] .money-select option" in css and ".money-popup option" in css
    assert 'class="money-popup' in read("templates", "components", "money_tab.html")   # 国を選ぶ見えない select にも配色が効く
    js = read("static", "js", "money.js")
    assert "MONEY_HIDE_COUNTRIES" in js and all(c in js for c in ("'DG'", "'EA'", "'IC'", "'TA'"))
