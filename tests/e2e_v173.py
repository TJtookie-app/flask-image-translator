"""v1.7.3/1.7.4のブラウザ確認: 背景・アクセント色が無いこと・結果カード・手ごたえ（コピー/星/マイク/カメラ枠/振動）・320px特大・右から左。使い方: python tests/e2e_v173.py"""
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
srv = make_server("127.0.0.1", 5102, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5102"
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
    def page(width=390, settings=None, scheme="dark", reduced="no-preference", lang="Japanese"):
        c = br.new_context(viewport={"width": width, "height": 800}, color_scheme=scheme, reduced_motion=reduced, permissions=["clipboard-read", "clipboard-write"])
        def h(r):
            u = r.request.url
            if u.startswith(B): r.continue_()
            elif "cdn.tailwindcss.com" in u: r.fulfill(status=200, content_type="application/javascript", body=JS)
            else: r.abort()
        c.route("**/*", h); c.request.post(B + "/set-display-language", form={"ui_lang": lang})
        pg = c.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.add_init_script("window.__vib = []; navigator.vibrate = function (n) { window.__vib.push(n); return true; }")
        if settings is not None: pg.add_init_script("if(!localStorage.getItem('tl_settings_v1'))localStorage.setItem('tl_settings_v1', %s)" % json.dumps(json.dumps(settings)))
        pg.goto(B + "/", wait_until="load"); pg.wait_for_timeout(300)
        return c, pg

    GRAD = lambda pg: pg.evaluate("getComputedStyle(document.body).backgroundImage")
    CARD = lambda pg: css(pg, ".max-w-xl", "backgroundColor")
    BTN = lambda pg: css(pg, "#tab-text button[type=submit]", "backgroundColor")

    # ---- v1.7.4: 背景・アクセント色の選択は取りやめ。v1.7.3 で保存された設定が残っていても、見た目は元（v1.7.2）のまま ----
    for theme, card, btn in (("dark", "rgb(18, 26, 46)", "rgb(93, 100, 224)"), ("light", "rgb(251, 249, 244)", "rgb(45, 106, 114)")):
        c, pg = page(settings={"theme": theme, "bg": "deep", "accent": "rose"})
        check(f"{theme}: old saved bg/accent are ignored (no attributes, solid card, original button)",
              attr(pg, "data-bg") is None and attr(pg, "data-accent") is None and GRAD(pg) == "none" and CARD(pg) == card and BTN(pg) == btn)
        pg.click("#nav-history"); pg.click("#hf-settings")
        check(f"{theme}: settings screen has no background/accent choices", pg.locator("[data-setting=bg]").count() == 0 and pg.locator("[data-setting=accent]").count() == 0)
        c.close()
    for name, st in (("dark xl", {"theme": "dark", "fs": "xl"}), ("light xl", {"theme": "light", "fs": "xl"})):
        c, pg = page(320, settings=st)
        pg.click("#nav-history"); pg.click("#hf-settings"); pg.wait_for_timeout(150)
        check(f"320px {name}: settings screen has no overflow", not pg.evaluate("document.documentElement.scrollWidth > innerWidth + 1"))
        c.close()

    # ---- 結果カード・手ごたえ ----
    c, pg = page()
    pg.fill("textarea[name=direct_text]", "Hi"); pg.click("#tab-text button[type=submit]")
    pg.wait_for_selector("#resultText-text"); pg.wait_for_timeout(400)
    fs = pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#resultText-text')).fontSize)")
    check(f"result text is larger ({fs}px) and uses the main text color", fs >= 22 and css(pg, "#resultText-text", "color") == "rgb(215, 220, 234)")
    check("result card has the accent line (::before, 3px)", pg.evaluate("(()=>{const s=getComputedStyle(document.querySelector('#tab-text .rc-box'),'::before');return s.width==='3px'&&s.backgroundColor==='rgb(124, 131, 240)'&&s.left==='0px'})()"))
    check("language label is a chip", css(pg, "#tab-text .rc-tag", "borderTopLeftRadius") != "0px" and css(pg, "#tab-text .rc-tag", "textTransform") == "none")
    pg.evaluate("window.__vib.length = 0")
    pg.click("#tab-text .rc-btn[title=コピー], #tab-text .rc-btn[aria-label=コピー]"); pg.wait_for_timeout(200)
    check("copy: icon turns into a check with a pop, and the phone vibrates once", pg.evaluate("(()=>{const i=document.querySelector('#tab-text .rc-btn .fa-check');return !!i&&getComputedStyle(i).animationName==='lk-pop'})()") and pg.evaluate("window.__vib.length") == 1)
    pg.click("#tab-text .rc-more"); pg.wait_for_selector("#tab-text .rc-menu:not(.hidden)")
    pg.click("#tab-text .fav-btn"); pg.wait_for_timeout(150)
    check("favorite: the star pops and the phone vibrates", pg.evaluate("(()=>{const i=document.querySelector('#tab-text .fav-btn i');return i.className.includes('fa-solid')&&getComputedStyle(i).animationName==='lk-star'})()") and pg.evaluate("window.__vib.length") == 2)
    # マイク: 録音中の波紋
    pg.evaluate("switchTab('voice')"); pg.wait_for_timeout(100)
    check("mic: no ripple while idle", css(pg, "#start-record-btn", "animationName") in ("none",))
    pg.evaluate("document.getElementById('mic-icon').className = 'fa-solid fa-square text-red-400 animate-pulse'")
    check("mic: ripple while recording", css(pg, "#start-record-btn", "animationName") == "lk-ring")
    # カメラ: 四隅の枠
    pg.evaluate("document.getElementById('cam-full').classList.remove('hidden')"); pg.wait_for_timeout(100)
    fr = pg.evaluate("(()=>{const f=document.querySelector('.cam-frame').getBoundingClientRect();const s=document.querySelector('#camera-capture-btn').getBoundingClientRect();const h=document.querySelector('#cam-hint').getBoundingClientRect();return [f.left,f.top,f.right,f.bottom,s.top,h.top,innerWidth]})()")
    check(f"camera: 4 corners, inside the screen, above the hint and shutter {[round(x) for x in fr]}", pg.locator(".cam-frame i").count() == 4 and fr[0] > 0 and fr[2] < fr[6] and fr[3] <= fr[5] and fr[3] < fr[4])
    check("camera: frame never blocks taps", css(pg, ".cam-frame", "pointerEvents") == "none")
    c.close()

    # ---- 動きを減らす: 新しい動きも止まる ----
    c, pg = page(reduced="reduce")
    pg.fill("textarea[name=direct_text]", "Hi"); pg.click("#tab-text button[type=submit]")
    pg.wait_for_selector("#resultText-text")
    pg.click("#tab-text .rc-btn[aria-label=コピー]"); pg.wait_for_timeout(150)
    check("reduced motion: no pop on copy, no vibration", pg.evaluate("getComputedStyle(document.querySelector('#tab-text .rc-btn .fa-check')).animationName") == "none" and pg.evaluate("window.__vib.length") == 0)
    c.close()

    # ---- 右から左の言語: 結果カードの線は右側 ----
    c, pg = page(lang="Arabic")
    pg.fill("textarea[name=direct_text]", "Hi"); pg.click("#tab-text button[type=submit]")
    pg.wait_for_selector("#resultText-text")
    check("RTL: accent line is on the right edge", pg.evaluate("(()=>{const s=getComputedStyle(document.querySelector('#tab-text .rc-box'),'::before');return s.right==='0px'&&s.left!=='0px'})()"))
    c.close()
    br.close()
check("no page errors " + str(errs), not errs)
print("FAILS:", fails)
sys.exit(1 if fails else 0)
