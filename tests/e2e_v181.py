"""v1.8.1（V13b）のブラウザ確認: Android アプリの起動画面（app-shell）。
サーバーが起きたら本体へ移る／起動中は待つ表示／圏外ならすぐ本体（保存済みの画面）へ／長引いたら「もう一度」「そのまま開く」。
使い方: python tests/e2e_v181.py"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = "file://" + os.path.join(ROOT, "app-shell", "index.html")
SITE = "https://tookie-translator.onrender.com/"
CORS = {"Access-Control-Allow-Origin": "*"}
fails = []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch()

    def new(health, offline=False, lang="ja-JP"):
        ctx = br.new_context(viewport={"width": 390, "height": 800}, locale=lang)
        log = {"site": 0, "pings": 0}
        def site(route):
            u = route.request.url
            if u.endswith("/healthz"):
                log["pings"] += 1
                code, body = health(log["pings"])
                route.fulfill(status=code, body=body, headers=CORS, content_type="text/plain")
            else:
                log["site"] += 1
                route.fulfill(status=200, body="<title>site</title><p id=real>本体</p>", content_type="text/html")
        ctx.route("https://tookie-translator.onrender.com/**", site)
        ctx.add_init_script("window.__off = 0; const r = Date.now.bind(Date); Date.now = () => r() + window.__off;"
                            + ("Object.defineProperty(navigator, 'onLine', {get: () => false});" if offline else ""))
        return ctx, ctx.new_page(), log

    # 1) すぐ起きている → 本体へ移る
    ctx, pg, log = new(lambda n: (200, "ok"))
    pg.goto(PAGE); pg.wait_for_url(SITE, timeout=5000)
    check("awake server: moves to the real site", pg.url == SITE and pg.locator("#real").count() == 1)
    ctx.close()

    # 2) 起動中（503 が続く）→ 待つ表示 → 3回目で起きて移る
    ctx, pg, log = new(lambda n: (503, "starting") if n < 3 else (200, "ok"))
    pg.goto(PAGE); pg.wait_for_timeout(1200)
    check("waking: shows the wait message, no jump yet", "起こしています" in pg.inner_text("#msg") and pg.url.startswith("file:"))
    check("waking: progress bar shown, buttons hidden", pg.locator("#bar").is_visible() and not pg.locator("#acts").is_visible())
    pg.wait_for_url(SITE, timeout=15000)
    check(f"waking: moves on once it answers ok ({log['pings']} pings)", log["pings"] == 3 and pg.url == SITE)
    ctx.close()

    # 3) 200 でも本文が ok でない（Render の仮ページなど）→ 起きたとは見なさない
    ctx, pg, log = new(lambda n: (200, "<html>Service waking up</html>") if n < 2 else (200, "ok"))
    pg.goto(PAGE); pg.wait_for_timeout(1200)
    check("a 200 interstitial is not treated as awake", pg.url.startswith("file:") and log["pings"] >= 1)
    pg.wait_for_url(SITE, timeout=10000)
    ctx.close()

    # 4) 圏外 → 待たず、すぐ本体（保存済みの画面）へ
    ctx, pg, log = new(lambda n: (500, "x"), offline=True)
    pg.goto(PAGE); pg.wait_for_url(SITE, timeout=5000)
    check("offline: goes to the site at once (service worker shows the saved screen)", log["pings"] == 0 and pg.url == SITE)
    ctx.close()

    # 5) 長引く → 「もう一度」「そのまま開く」。「そのまま開く」で本体へ
    ctx, pg, log = new(lambda n: (503, "starting"))
    pg.goto(PAGE); pg.wait_for_timeout(600)
    pg.evaluate("window.__off = 200000")
    pg.wait_for_selector("#acts:not([hidden])", timeout=8000)
    check("long wait: gives up politely with two buttons", pg.locator("#retry").inner_text() == "もう一度" and pg.locator("#open").inner_text() == "そのまま開く" and not pg.locator("#bar").is_visible())
    check("long wait: message offered", "つながりにくい" in pg.inner_text("#msg"))
    n0 = log["pings"]
    pg.click("#retry"); pg.wait_for_timeout(800)
    check("retry: shows the wait again and pings again", pg.locator("#bar").is_visible() and log["pings"] > n0)
    pg.evaluate("window.__off = 400000"); pg.wait_for_selector("#acts:not([hidden])", timeout=8000)
    pg.click("#open"); pg.wait_for_url(SITE, timeout=5000)
    check("open anyway: goes to the site", pg.url == SITE)
    ctx.close()

    # 6) 英語の端末
    ctx, pg, log = new(lambda n: (503, "x"), lang="en-US")
    pg.goto(PAGE); pg.wait_for_timeout(500)
    check("English device: English message", "Waking up" in pg.inner_text("#msg") and pg.evaluate("document.documentElement.lang") == "en")
    ctx.close()

    # 7) 狭い画面でも、はみ出さない
    ctx = br.new_context(viewport={"width": 320, "height": 560}); pg = ctx.new_page()
    ctx.route("https://tookie-translator.onrender.com/**", lambda r: r.fulfill(status=503, body="x", headers=CORS))
    pg.goto(PAGE); pg.wait_for_timeout(500)
    check("320px: no horizontal overflow", pg.evaluate("document.documentElement.scrollWidth <= innerWidth"))
    ctx.close()
    br.close()
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
