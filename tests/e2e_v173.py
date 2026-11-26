"""v1.7.3のブラウザ確認: 背景3種（カードを少し透かす）・アクセント色・結果カード・手ごたえ（コピー/星/マイク/カメラ枠/振動）・320px特大・右から左。使い方: python tests/e2e_v173.py"""
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

    # ---- 標準: 何も変わらない ----
    c, pg = page()
    check("standard: no data-bg / data-accent", attr(pg, "data-bg") is None and attr(pg, "data-accent") is None)
    check("standard: body has no gradient, card is the solid night-ink card", GRAD(pg) == "none" and CARD(pg) == "rgb(18, 26, 46)")
    check("standard: button is the indigo button", BTN(pg) == "rgb(93, 100, 224)")
    c.close()

    # ---- 背景3種（ダーク）: 設定画面から選ぶ・再読み込みしても残る・カードが少し透ける ----
    c, pg = page()
    pg.click("#nav-history"); pg.click("#hf-settings")
    pg.click("[data-setting=bg] [data-v=deep]"); pg.wait_for_timeout(100)
    check("deep blue: attribute + gradient body + translucent card", attr(pg, "data-bg") == "deep" and "linear-gradient" in GRAD(pg) and CARD(pg) == "rgba(18, 26, 46, 0.86)")
    check("deep blue: button color unchanged (still single color)", BTN(pg) == "rgb(93, 100, 224)" and css(pg, "#tab-text button[type=submit]", "backgroundImage") == "none")
    check("deep blue: theme-color meta follows", pg.evaluate("document.querySelector('meta[name=theme-color]').content") == "#04061A")
    pg.reload(wait_until="load"); pg.wait_for_timeout(200)
    check("deep blue survives reload", attr(pg, "data-bg") == "deep" and "linear-gradient" in GRAD(pg))
    pg.click("#nav-history"); pg.click("#hf-settings")
    check("settings UI shows the saved background", pg.get_attribute("[data-setting=bg] [data-v=deep]", "aria-pressed") == "true")
    pg.click("[data-setting=bg] [data-v=moon]"); pg.wait_for_timeout(100)
    check("moonlight: gradient + accent turns teal by itself", attr(pg, "data-bg") == "moon" and "rgb(15, 32, 39)" in GRAD(pg) and BTN(pg) == "rgb(20, 128, 142)")
    pg.click("[data-setting=accent] [data-v=rose]"); pg.wait_for_timeout(100)
    check("moonlight + rose accent: the chosen accent wins", BTN(pg) == "rgb(194, 58, 98)")
    pg.click("[data-setting=bg] [data-v=ink]"); pg.click("[data-setting=accent] [data-v=auto]"); pg.wait_for_timeout(100)
    check("back to standard: attributes removed", attr(pg, "data-bg") is None and attr(pg, "data-accent") is None and GRAD(pg) == "none")
    c.close()

    # ---- アクセント色（ダーク・ライト）: ボタンの色 ----
    want = {"dark": {"indigo": "rgb(93, 100, 224)", "teal": "rgb(20, 128, 142)", "orange": "rgb(191, 84, 16)", "rose": "rgb(194, 58, 98)"},
            "light": {"indigo": "rgb(75, 84, 201)", "teal": "rgb(45, 106, 114)", "orange": "rgb(184, 83, 14)", "rose": "rgb(184, 58, 94)"}}
    for theme in ("dark", "light"):
        got = {}
        for acc in ("indigo", "teal", "orange", "rose"):
            c, pg = page(settings={"theme": theme, "accent": acc}); got[acc] = BTN(pg); c.close()
        check(f"{theme}: accent colors on the translate button {got}", got == want[theme])
    c, pg = page(settings={"theme": "light", "bg": "deep"})
    check("light + deep blue: soft sand-blue gradient, card rgba(251,249,244,.88)", "linear-gradient" in GRAD(pg) and CARD(pg) == "rgba(251, 249, 244, 0.88)")
    c.close()

    # ---- 文字の読みやすさ: 実際に表示された色で、いちばん明るい背景の端まで ----
    lum = lambda v: (lambda a: 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2])([((x / 255) / 12.92 if x / 255 <= .03928 else (((x / 255) + .055) / 1.055) ** 2.4) for x in v])
    nums = lambda s: [float(x) for x in __import__("re").findall(r"[\d.]+", s)]
    def ratio(a, b):
        la, lb = lum(a), lum(b); return (max(la, lb) + .05) / (min(la, lb) + .05)
    for theme, bg, edge in (("dark", "deep", [21, 48, 138]), ("dark", "moon", [44, 83, 100]), ("light", "deep", [220, 226, 236]), ("light", "moon", [217, 228, 226])):
        c, pg = page(settings={"theme": theme, "bg": bg})
        cd = nums(CARD(pg)); a = cd[3]; comp = [cd[i] * a + edge[i] * (1 - a) for i in range(3)]
        tx = nums(css(pg, "#page-title-text", "color"))
        check(f"{theme} {bg}: title text on the card over the brightest edge {ratio(tx, comp):.1f}:1 (>=7)", ratio(tx, comp) >= 7)
        c.close()

    # ---- 設定の選択欄: 320px・特大・ダーク/ライトではみ出さない／押す場所は44px以上 ----
    for name, st in (("dark xl", {"theme": "dark", "fs": "xl"}), ("light xl", {"theme": "light", "fs": "xl", "bg": "moon", "accent": "orange"})):
        c, pg = page(320, settings=st)
        pg.click("#nav-history"); pg.click("#hf-settings"); pg.wait_for_timeout(150)
        ov = pg.evaluate("document.documentElement.scrollWidth > innerWidth + 1")
        sizes = pg.evaluate("[...document.querySelectorAll('[data-setting=bg] button, [data-setting=accent] button')].map(b => { const r = b.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height), r.right]; })")
        check(f"320px {name}: background/accent choices fit, >=44px tall, no overflow {sizes}", not ov and all(s[1] >= 44 and s[2] <= 320 for s in sizes) and len(sizes) == 8)
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
