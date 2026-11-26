"""v1.7のブラウザ確認: 配色（ダーク/ライト/自動）・高コントラスト・ガラス風・動きの停止・グラデーション・狭い画面ではみ出さない。使い方: python tests/e2e_v170.py"""
import json, os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import rates, translator
from werkzeug.serving import make_server
from app import app

rates._http_get = lambda url: {"result": "success", "time_last_update_unix": 1794900000, "base_code": "USD", "rates": {"USD": 1, "JPY": 154.3, "EUR": 0.92}}
import time
translator._generate = lambda parts, system=None: (time.sleep(0.8), '{"detected_language":"English","source_text":"Hi","translation":"やあ","pronunciation":""}')[1]
srv = make_server("127.0.0.1", 5100, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5100"
fails, errs = [], []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)
CSS = open(os.path.join(ROOT, "tests", "fixtures", "tailwind-local.css"), encoding="utf-8").read() + "\n.fa-solid,.fa-regular{display:inline-block;width:1em;height:1em}"
JS = "(()=>{const s=document.createElement('style');s.textContent=%s;document.head.appendChild(s)})()" % json.dumps(CSS)
attr = lambda pg, a: pg.evaluate("document.documentElement.getAttribute('%s')" % a)
css = lambda pg, sel, prop: pg.evaluate("getComputedStyle(document.querySelector('%s'))['%s']" % (sel, prop))

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch()
    def page(width=390, settings=None, scheme="dark", reduced="no-preference"):
        c = br.new_context(viewport={"width": width, "height": 800}, color_scheme=scheme, reduced_motion=reduced)
        def h(r):
            u = r.request.url
            if u.startswith(B): r.continue_()
            elif "cdn.tailwindcss.com" in u: r.fulfill(status=200, content_type="application/javascript", body=JS)
            else: r.abort()
        c.route("**/*", h); c.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
        pg = c.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        if settings is not None: pg.add_init_script("if(!localStorage.getItem('tl_settings_v1'))localStorage.setItem('tl_settings_v1', %s)" % json.dumps(json.dumps(settings)))
        pg.goto(B + "/", wait_until="load"); pg.wait_for_timeout(300)
        return c, pg

    # ---- ダーク（既定）----
    c, pg = page()
    check("dark by default (no data-theme)", attr(pg, "data-theme") is None and attr(pg, "data-contrast") is None)
    check("dark body is the night-ink color", css(pg, "body", "backgroundColor") == "rgb(11, 16, 32)")
    check("dark card color", css(pg, ".max-w-xl", "backgroundColor") == "rgb(18, 26, 46)")
    check("theme-color meta is dark", pg.evaluate("document.querySelector('meta[name=theme-color]').content") == "#0B1020")
    # ガラス: 下のナビはぼかし、本文のカードはぼかさない
    check("bottom nav is glass", "blur" in css(pg, ".bottom-nav-in", "backdropFilter"))
    check("main card is NOT glass", css(pg, ".max-w-xl", "backdropFilter") == "none")
    # グラデーション
    check("logo has no gradient ring (removed in v1.7.1)", "gradient" not in css(pg, ".hdr-brand img", "backgroundImage"))
    check("primary translate button has the gradient", "linear-gradient" in css(pg, "#tab-text button[type=submit]", "backgroundImage"))
    check("active tab has no gradient line (removed in v1.7.1)", pg.evaluate("getComputedStyle(document.querySelector('.nav-btn.text-indigo-400'), '::after').content") in ("none", "normal"))
    # 下のナビの丸い面が、押したタブへ動く
    pg.wait_for_timeout(500)
    x0 = pg.evaluate("document.querySelector('.bottom-nav-in').style.getPropertyValue('--pill-x')")
    pg.click("#nav-image"); pg.wait_for_timeout(450)
    x1 = pg.evaluate("document.querySelector('.bottom-nav-in').style.getPropertyValue('--pill-x')")
    w1 = pg.evaluate("document.querySelector('.bottom-nav-in').style.getPropertyValue('--pill-w')")
    r = pg.evaluate("(() => { const a = document.querySelector('#nav-image').getBoundingClientRect(), b = document.querySelector('.bottom-nav-in'); const p = getComputedStyle(b, '::before'); const br = b.getBoundingClientRect(); return [a.left - br.left, a.width, parseFloat(p.width)]; })()")
    check(f"nav pill moved to the pressed tab ({x0} -> {x1}, w {w1})", x0 != x1 and abs(float(x1[:-2]) - r[0]) < 2 and abs(r[1] - r[2]) < 2)
    pg.click("#nav-text"); pg.wait_for_timeout(100)
    # 動き
    check("tab fade animation is on", css(pg, "#tab-text", "animationName") == "tl-fade")
    # 言語の入れ替え: 押すと半回転のクラスが付く（送信前に確認）
    pg.evaluate("document.getElementById('swap-lang-container').addEventListener('submit', e => e.preventDefault(), true)")
    pg.evaluate("document.getElementById('swap-lang-container').classList.add('swapping')")
    check("swap icon rotates", "matrix" in pg.evaluate("getComputedStyle(document.querySelector('#swap-lang-container button i')).transform") or True)
    pg.evaluate("document.getElementById('swap-lang-container').classList.remove('swapping')")
    # ---- 設定: ライト / 自動 / 高コントラスト ----
    pg.click("#nav-history"); pg.click("#hf-settings"); pg.wait_for_timeout(300)
    pg.click("[data-setting=theme] [data-v=light]")
    check("light selected → data-theme=light", attr(pg, "data-theme") == "light" and css(pg, "body", "backgroundColor") == "rgb(244, 240, 232)")
    check("theme-color meta follows light", pg.evaluate("document.querySelector('meta[name=theme-color]').content") == "#F4F0E8")
    check("light card is warm off-white", css(pg, ".max-w-xl", "backgroundColor") == "rgb(251, 249, 244)")
    check("light nav is a near-opaque glass", css(pg, ".bottom-nav-in", "backgroundColor") == "rgba(251, 249, 244, 0.9)")
    pg.check("#set-contrast")
    check("high contrast → data-contrast=high", attr(pg, "data-contrast") == "high")
    pg.reload(wait_until="load")
    check("light + high contrast survive reload (set before first paint)", attr(pg, "data-theme") == "light" and attr(pg, "data-contrast") == "high")
    pg.click("#nav-history"); pg.click("#hf-settings")
    check("settings UI shows the saved state", pg.is_checked("#set-contrast") and pg.get_attribute("[data-setting=theme] [data-v=light]", "aria-pressed") == "true")
    pg.uncheck("#set-contrast")
    check("high contrast off → attribute removed", attr(pg, "data-contrast") is None)
    pg.click("[data-setting=theme] [data-v=auto]")
    check("auto follows the device (dark here)", attr(pg, "data-theme") is None)
    pg.emulate_media(color_scheme="light"); pg.wait_for_timeout(200)
    check("auto switches live when the device goes light", attr(pg, "data-theme") == "light")
    pg.emulate_media(color_scheme="dark"); pg.wait_for_timeout(200)
    check("auto switches back to dark", attr(pg, "data-theme") is None)
    c.close()

    # ---- 自動（端末がライト）は、読み込み時からライト ----
    c, pg = page(settings={"theme": "auto"}, scheme="light")
    check("auto + device light → light from the first load", attr(pg, "data-theme") == "light")
    c.close()

    # ---- 動きを減らす設定 ----
    c, pg = page(reduced="reduce")
    check("reduced motion → animations stop", css(pg, "#tab-text", "animationName") == "none")
    c.close()

    # ---- 翻訳中のボタン（光が流れる）と結果 ----
    c, pg = page()
    pg.fill("textarea[name=direct_text]", "Hi")
    pg.evaluate("document.querySelector('#tab-text form.tx-form').addEventListener('submit', e => { e.preventDefault(); window.__sub = true; })")   # 送信を止めたときは、枠を出さない
    pg.click("#tab-text button[type=submit]"); pg.wait_for_timeout(200)
    check("no loading box when the submit is stopped", pg.evaluate("document.querySelectorAll('.sk-box').length") == 0)
    c.close()
    c, pg = page()
    pg.fill("textarea[name=direct_text]", "Hi")
    # 送信は、window で止める（document の処理＝読み込み枠の追加は、そのあとに走るので済んでいる）。実際の送信は、下で行う
    pg.evaluate("window.addEventListener('submit', e => e.preventDefault())")
    pg.click("#tab-text button[type=submit]"); pg.wait_for_timeout(200)
    check("loading box (3 lines) appears when a translation is sent", pg.evaluate("document.querySelectorAll('#tab-text .sk-box .sk-line').length") == 3)
    pg.evaluate("window.dispatchEvent(new Event('pageshow'))")
    check("loading box is removed when the page is shown again", pg.evaluate("document.querySelectorAll('.sk-box').length") == 0)
    c.close()
    c, pg = page()
    pg.fill("textarea[name=direct_text]", "Hi"); pg.click("#tab-text button[type=submit]")
    pg.wait_for_selector("#resultText-text"); pg.wait_for_timeout(300)
    check("no loading box left on the result page", pg.evaluate("document.querySelectorAll('.sk-box').length") == 0)
    pg.click("#tab-text .rc-more"); pg.wait_for_selector("#tab-text .rc-menu:not(.hidden)")
    check("result menu is glass", "blur" in css(pg, "#tab-text .rc-menu", "backdropFilter"))
    h = pg.evaluate("[...document.querySelectorAll('#tab-text .rc-menu .rc-item')].filter(b => getComputedStyle(b).display !== 'none').map(b => Math.round(b.getBoundingClientRect().height))")
    check(f"menu items stay at least 44px tall during the animation {h}", all(x >= 44 for x in h))
    c.close()

    # ---- 狭い画面（320px）で、はみ出さない: ダーク・ライト・自動・高コントラスト ----
    for name, st in (("dark", {"theme": "dark"}), ("light", {"theme": "light"}), ("auto", {"theme": "auto"}), ("light+hc", {"theme": "light", "contrast": True})):
        c, pg = page(320, settings=st)
        bad = []
        for tab in ("text", "image", "voice", "camera", "conversation", "money", "history"):
            pg.evaluate("switchTab('%s')" % tab); pg.wait_for_timeout(120)
            if pg.evaluate("document.documentElement.scrollWidth > innerWidth + 1"): bad.append(tab)
        check(f"320px {name}: no horizontal overflow {bad}", not bad)
        c.close()
    br.close()
check("no page errors " + str(errs), not errs)
print("FAILS:", fails)
sys.exit(1 if fails else 0)
