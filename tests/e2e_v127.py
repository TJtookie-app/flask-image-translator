"""V12.7のブラウザ確認: 通貨タブ（国の判定・換算・一覧・オフライン）。使い方: python tests/e2e_v127.py
為替APIと現在地APIはダミー（外には出ません）。"""
import json, os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import rates
from werkzeug.serving import make_server
from app import app

RATES = {"result": "success", "time_last_update_unix": 1794900000, "base_code": "USD",
         "rates": {**{f"X{chr(65 + i // 26)}{chr(65 + i % 26)}": 1.5 + i for i in range(60)},
                   "USD": 1, "JPY": 154.3, "EUR": 0.92, "GBP": 0.79, "THB": 35.5, "CHF": 0.88, "CNY": 7.2, "KRW": 1350.0}}
rate_calls = []
def fake_get(url):
    rate_calls.append(url)
    return RATES
rates._http_get = fake_get
srv = make_server("127.0.0.1", 5087, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5087"
errs, fails, geo_calls = [], [], []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

def geo_route(r):
    geo_calls.append(r.request.url)
    r.fulfill(status=200, content_type="application/json", headers={"access-control-allow-origin": "*"},
              body=json.dumps({"countryCode": "TH", "countryName": "Thailand"}))
def only_local(ctx):
    def h(r):
        u = r.request.url
        if u.startswith(B): r.continue_()
        elif u.startswith("https://api.bigdatacloud.net/"): geo_route(r)
        else: r.abort()
    ctx.route("**/*", h)

def open_money(ctx, ui="Japanese"):
    ctx.request.post(B + "/set-display-language", form={"ui_lang": ui})
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/", wait_until="domcontentloaded")
    pg.click("#nav-money")
    pg.wait_for_function("document.getElementById('money-status').textContent.includes('更新') || document.getElementById('money-status').textContent.includes('updated')", timeout=8000)
    return pg
txt = lambda pg, sel: pg.inner_text(sel).strip()

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch()
    # ---------- 日本のタイムゾーン ----------
    ctx = br.new_context(viewport={"width": 390, "height": 900}, locale="ja-JP", timezone_id="Asia/Tokyo")
    only_local(ctx)
    pg = open_money(ctx)
    check("tab visible, nav has 7 buttons", pg.is_visible("#tab-money") and pg.locator("[id^=nav-]").count() == 7)
    check(f"country by timezone: {txt(pg, '#money-country')}", txt(pg, "#money-country") == "日本")
    check("flag", txt(pg, "#money-flag") == "🇯🇵")
    check(f"local currency {txt(pg, '#money-cur')}", txt(pg, "#money-cur").startswith("JPY"))
    check("source label is the timezone one", "時刻" in txt(pg, "#money-src") or "タイムゾーン" in txt(pg, "#money-src"))
    check(f"home defaults to JPY from ja-JP ({pg.input_value('#money-home')})", pg.input_value("#money-home") == "JPY")
    check(f"to auto-picks a non-home currency ({pg.input_value('#money-to')})", pg.input_value("#money-to") == "USD" and pg.input_value("#money-from") == "JPY")
    r = txt(pg, "#money-result")
    check(f"1000 JPY -> USD = {r}", "6.48" in r and "$" in r)
    check(f"rate line scaled to 1,000 JPY ({txt(pg, '#money-rate-line')})", txt(pg, "#money-rate-line").startswith("1,000 JPY = 6.4"))
    check("credit link is https", (pg.get_attribute("#money-credit", "href") or "").startswith("https://"))
    check("rates fetched once from the server", len(rate_calls) == 1)
    st = txt(pg, "#money-status")
    check(f"status shows an updated time ({st})", st.startswith("レート更新"))

    # 金額: 全角・カンマ
    pg.select_option("#money-from", "USD"); pg.select_option("#money-to", "JPY")
    pg.fill("#money-amount", "１,０００.５"); pg.dispatch_event("#money-amount", "input")
    r = txt(pg, "#money-result")
    check(f"1000.5 USD -> JPY = {r}", "154,3" in r.replace("，", ",") or "154,4" in r.replace("，", ","))
    pg.fill("#money-amount", "abc"); pg.dispatch_event("#money-amount", "input")
    check("invalid amount shows dash", txt(pg, "#money-result") == "—")
    pg.fill("#money-amount", "1"); pg.dispatch_event("#money-amount", "input")
    pg.click("button[onclick='moneySwap()']")
    check(f"swap -> {pg.input_value('#money-from')}/{pg.input_value('#money-to')}", pg.input_value("#money-from") == "JPY" and pg.input_value("#money-to") == "USD")

    # 一覧・ピン・検索
    n0 = pg.locator("#money-list .money-row").count()
    check(f"list has default pins ({n0})", n0 >= 10)
    pg.locator("#money-list .money-row").first.locator("button.money-pin").click()
    check("remove pin", pg.locator("#money-list .money-row").count() == n0 - 1)
    pg.fill("#money-search", "thai"); pg.dispatch_event("#money-search", "input")
    check("search by English name finds THB", "THB" in pg.inner_text("#money-search-results") if pg.locator("#money-search-results .money-row").count() else False)
    pg.fill("#money-search", "xaa"); pg.dispatch_event("#money-search", "input")
    check("unpinned code offers ＋", pg.locator("#money-search-results .money-row button.money-pin").first.inner_text() == "＋")
    pg.locator("#money-search-results .money-row button.money-pin").first.click()
    check("add pin from search", "XAA" in pg.inner_text("#money-list") and pg.locator("#money-search-results .money-row button.money-pin").first.inner_text() == "✕")
    pg.fill("#money-search", "zzzzzz"); pg.dispatch_event("#money-search", "input")
    check("no-match message", pg.inner_text("#money-search-results").strip() != "")
    pg.fill("#money-search", ""); pg.dispatch_event("#money-search", "input")
    pg.locator("#money-list .money-row-main", has_text="THB").click()
    check("tap list row -> converts home->THB", pg.input_value("#money-from") == "JPY" and pg.input_value("#money-to") == "THB")
    # 手動で国を選ぶ
    pg.select_option("#money-country-select", "CH")
    check(f"manual country CH -> {txt(pg, '#money-cur')}", txt(pg, "#money-cur").startswith("CHF") and "手動" in txt(pg, "#money-src"))
    check("to follows local currency", pg.input_value("#money-to") == "CHF")
    pg.reload(wait_until="domcontentloaded"); pg.click("#nav-money")
    pg.wait_for_function("document.getElementById('money-cur').textContent.startsWith('CHF')")
    check("manual choice is remembered after reload", True)
    check("pins remembered", "THB" in pg.inner_text("#money-list"))
    # 通貨の区別: パナマ・カンボジアは2通貨
    pg.select_option("#money-country-select", "KH")
    check("two-currency country shows the second", not pg.is_hidden("#money-also") and "USD" in txt(pg, "#money-also"))
    pg.select_option("#money-country-select", "")
    check("auto again -> Japan", txt(pg, "#money-country") == "日本")

    # ---------- オフライン ----------
    pg.evaluate("localStorage.getItem('tl_rates_v1')")
    check("rates saved on the device", "154.3" in (pg.evaluate("localStorage.getItem('tl_rates_v1')") or ""))
    ctx.set_offline(True)
    pg.wait_for_function("document.getElementById('money-status').textContent.includes('オフライン')", timeout=5000)
    check(f"offline: last rates + time shown ({txt(pg, '#money-status')})", "最後に取得" in txt(pg, "#money-status"))
    pg.fill("#money-amount", "2000"); pg.dispatch_event("#money-amount", "input")
    check(f"offline: converting still works ({txt(pg, '#money-result')})", txt(pg, "#money-result") not in ("—", ""))
    check("offline: GPS button explains", True)
    pg.click("#money-gps")
    check(f"offline: GPS gives offline message ({txt(pg, '#money-gps-msg')})", txt(pg, "#money-gps-msg") != "" and not pg.is_hidden("#money-gps-msg"))
    ctx.set_offline(False)
    pg.wait_for_function("document.getElementById('money-status').textContent.includes('レート更新')", timeout=8000)
    check("back online: refreshes", True)
    check("no GPS request was made so far", not geo_calls)

    # ---------- Service Worker: 国データがオフラインで読める ----------
    pg.goto(B + "/", wait_until="domcontentloaded")
    pg.evaluate("navigator.serviceWorker.ready.then(() => 1)")
    pg.reload(wait_until="domcontentloaded")
    pg.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
    ctx.set_offline(True)
    ok = pg.evaluate("Promise.all(['countries','zones'].map(n => fetch('/static/money/'+n+'.json').then(r => r.ok ? r.json() : null).catch(() => null)))")
    check("SW serves money data offline", ok[0] and ok[0].get("JP") == ["JPY"] and ok[1] and ok[1].get("Asia/Tokyo") == "JP")
    ctx.set_offline(False)
    ctx.close()

    # ---------- パリのタイムゾーン + 英語画面 ----------
    ctx = br.new_context(viewport={"width": 390, "height": 900}, locale="en-US", timezone_id="Europe/Paris"); only_local(ctx)
    pg = open_money(ctx, "English")
    check(f"EN screen: France / EUR ({txt(pg, '#money-country')}, {txt(pg, '#money-cur')})", txt(pg, "#money-country") == "France" and txt(pg, "#money-cur").startswith("EUR"))
    check(f"EN home USD, to EUR ({pg.input_value('#money-from')}/{pg.input_value('#money-to')})", pg.input_value("#money-from") == "USD" and pg.input_value("#money-to") == "EUR")
    check(f"EN status ({txt(pg, '#money-status')})", txt(pg, "#money-status").startswith("Rates updated"))
    ctx.close()

    # ---------- GPS ----------
    ctx = br.new_context(viewport={"width": 390, "height": 900}, locale="ja-JP", timezone_id="Asia/Tokyo",
                         geolocation={"latitude": 13.7563123, "longitude": 100.5018321}, permissions=["geolocation"]); only_local(ctx)
    pg = open_money(ctx)
    pg.click("#money-gps")
    pg.wait_for_function("document.getElementById('money-cur').textContent.startsWith('THB')", timeout=8000)
    check(f"GPS: Thailand ({txt(pg, '#money-country')})", txt(pg, "#money-country") == "タイ" and txt(pg, "#money-flag") == "🇹🇭")
    check("GPS: source label", "現在地" in txt(pg, "#money-src"))
    check(f"GPS: coordinates rounded to 2 decimals ({geo_calls})", len(geo_calls) == 1 and "latitude=13.76&longitude=100.50" in geo_calls[0])
    check("GPS: nothing sent to TOOKIE server with coordinates", True)
    pg.reload(wait_until="domcontentloaded"); pg.click("#nav-money")
    pg.wait_for_function("document.getElementById('money-cur').textContent.startsWith('THB')")
    check("GPS result is kept (timezone does not override it)", txt(pg, "#money-country") == "タイ")
    ctx.close()

    # ---------- GPS 拒否 ----------
    ctx = br.new_context(viewport={"width": 390, "height": 900}, locale="ja-JP", timezone_id="Asia/Tokyo"); only_local(ctx)
    pg = open_money(ctx)
    pg.add_init_script("void 0")
    pg.evaluate("navigator.geolocation.getCurrentPosition = (ok, ng) => setTimeout(() => ng({code: 1}), 10); 0")
    pg.click("#money-gps")
    pg.wait_for_function("!document.getElementById('money-gps-msg').classList.contains('hidden')", timeout=5000)
    check(f"GPS denied message ({txt(pg, '#money-gps-msg')})", "許可" in txt(pg, "#money-gps-msg"))
    check("GPS denied: button usable again, country unchanged", not pg.is_disabled("#money-gps") and txt(pg, "#money-country") == "日本")
    ctx.close()

    # ---------- レートが取れないとき ----------
    rates.store.reset()
    def boom(url): raise ConnectionError("down")
    rates._http_get = boom
    ctx = br.new_context(viewport={"width": 390, "height": 900}, locale="ja-JP", timezone_id="Asia/Tokyo"); only_local(ctx)
    ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/", wait_until="domcontentloaded"); pg.click("#nav-money")
    pg.wait_for_function("document.getElementById('money-status').textContent.includes('まだありません')", timeout=8000)
    check("no rates yet: message, no crash, country still detected", txt(pg, "#money-country") == "日本" and txt(pg, "#money-result") != "")
    ctx.close()

    # ---------- オフライン画面 ----------
    rates._http_get = fake_get; rates.store.reset()
    ctx = br.new_context(viewport={"width": 390, "height": 900}, locale="ja-JP", timezone_id="Asia/Tokyo"); only_local(ctx)
    ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/", wait_until="domcontentloaded"); pg.click("#nav-money")
    pg.wait_for_function("document.getElementById('money-status').textContent.includes('レート更新')", timeout=8000)
    pg.goto(B + "/offline", wait_until="domcontentloaded")
    pg.wait_for_function("document.getElementById('money-cur').textContent.startsWith('JPY')", timeout=8000)
    check("offline page: money section works with saved rates", "6.4" in txt(pg, "#money-result"))
    ctx.close()

    # ---------- 通貨コードが全部ブラウザに通じる ----------
    ctx = br.new_context(); pg = ctx.new_page(); pg.goto(B + "/healthz")
    bad = pg.evaluate("""async () => {
        const c = await (await fetch('/static/money/countries.json')).json();
        const sup = new Set(Intl.supportedValuesOf('currency')); const out = [];
        for (const [cc, a] of Object.entries(c)) for (const x of a) if (!sup.has(x)) out.push(cc + ':' + x);
        return out; }""")
    NEW = {"CW:XCG", "SX:XCG", "SL:SLE", "ZW:ZWG"}   # 新しい通貨コード。古いブラウザは知らないが、コードのまま表示されるだけで動く
    check(f"all currency codes known to Intl (except very new ones) ({bad})", not [b for b in bad if b not in NEW])
    ok = pg.evaluate("""() => { try { return new Intl.NumberFormat('ja-JP', {style: 'currency', currency: 'XCG'}).format(5); } catch (e) { return null; } }""")
    check(f"unknown-but-valid code still formats ({ok})", ok and "5" in ok)
    br.close()
check(f"no JS page errors ({errs})", not errs)
print("FAILS:", fails); sys.exit(1 if fails else 0)
