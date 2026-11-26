"""v1.8.0（V13a）のブラウザ確認: 外部の読み込みがゼロ・アイコンが出る・圏外でも画面とアイコンが崩れない。使い方: python tests/e2e_v180.py"""
import json, os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import rates, translator
from werkzeug.serving import make_server
from app import app, ASSET_V

rates._http_get = lambda url: {"result": "success", "time_last_update_unix": 1794900000, "base_code": "USD", "rates": {"USD": 1, "JPY": 154.3, "EUR": 0.92}}
translator._generate = lambda parts, system=None: '{"detected_language":"English","source_text":"Hi","translation":"やあ","pronunciation":""}'
srv = make_server("127.0.0.1", 5103, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5103"
fails, errs, external = [], [], []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 800, "height": 900})
    def h(r):
        u = r.request.url
        if u.startswith(B) or u.startswith("data:") or u.startswith("blob:"): r.continue_()
        else:
            external.append(u); r.abort()
    ctx.route("**/*", h)
    ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))

    # ---- 1) 外部へのアクセスが、1回もない ----
    for path in ("/", "/start", "/privacy", "/select-language?type=source", "/offline"):
        pg.goto(B + path, wait_until="load"); pg.wait_for_timeout(500)
    pg.goto(B + "/", wait_until="load"); pg.wait_for_timeout(500)
    for t in ("image", "voice", "camera", "conversation", "money", "history"):
        pg.evaluate("switchTab('%s')" % t); pg.wait_for_timeout(100)
    # 通貨の逆引き（bigdatacloud）は、ボタンを押したときだけ。ここでは押していない
    check(f"no request to any other site (CDN gone) {external}", not external)

    # ---- 2) 画面の形とアイコン ----
    pg.evaluate("switchTab('text')"); pg.wait_for_timeout(200)
    check("layout comes from the bundled Tailwind (card is max-w-xl = 576px)", pg.evaluate("Math.round(document.querySelector('.max-w-xl').getBoundingClientRect().width)") == 576)
    check("card is rounded-3xl and bg-slate-900 mapped to the theme card", pg.evaluate("getComputedStyle(document.querySelector('.max-w-xl')).borderTopLeftRadius") == "24px"
          and pg.evaluate("getComputedStyle(document.querySelector('.max-w-xl')).backgroundColor") == "rgb(18, 26, 46)")
    check("Font Awesome solid + regular fonts are loaded", pg.evaluate("document.fonts.load('900 16px \"Font Awesome 7 Free\"').then(a => a.length)") >= 1
          and pg.evaluate("document.fonts.check('900 16px \"Font Awesome 7 Free\"')"))
    glyph = pg.evaluate("getComputedStyle(document.querySelector('#nav-camera i'), '::before').content")
    check(f"icons have a glyph (camera: {glyph!r})", glyph not in ("none", "normal", '""'))
    w = pg.evaluate("[...document.querySelectorAll('#bottom-nav i')].map(i => Math.round(i.getBoundingClientRect().width))")
    check(f"icons keep the old auto width (not a fixed 1.25em) {w}", all(0 < x < 24 for x in w) and len(set(w)) > 1)

    # ---- 3) 圏外（機内モード）でも、画面もアイコンも崩れない ----
    pg.evaluate("navigator.serviceWorker.ready.then(() => 1)"); pg.reload(wait_until="load")
    pg.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
    cached = pg.evaluate("(async()=>{const c=await caches.open('tookie-'+%s);return (await c.keys()).map(r=>new URL(r.url).pathname)})()" % json.dumps(ASSET_V))
    for must in ("/static/vendor/tailwind.css", "/static/vendor/fontawesome/css/all.min.css", "/static/vendor/fontawesome/webfonts/fa-solid-900.woff2", "/static/vendor/fontawesome/webfonts/fa-regular-400.woff2"):
        check(f"precached {must}", must in cached)
    check("no old CDN cache is kept", "tookie-runtime-v1" not in pg.evaluate("caches.keys()"))
    ctx.set_offline(True)
    pg.goto(B + "/offline", wait_until="load"); pg.wait_for_timeout(600)
    check("offline: page is styled (card width 576px) and has no console errors", pg.evaluate("Math.round(document.querySelector('.max-w-xl').getBoundingClientRect().width)") == 576)
    check("offline: icons still come out", pg.evaluate("document.fonts.check('900 16px \"Font Awesome 7 Free\"')") and
          pg.evaluate("getComputedStyle(document.querySelector('#offline-status i'), '::before').content") not in ("none", "normal", '""'))
    ok = pg.evaluate("(async()=>{const r=await fetch('/static/vendor/fontawesome/webfonts/fa-solid-900.woff2');return r.ok && (await r.arrayBuffer()).byteLength>10000})()")
    check("offline: the solid font file is served from the device", ok)
    ctx.set_offline(False)

    # ---- 4) 幅 320px（ダーク・ライト）でも、はみ出さない ----
    for theme in ("dark", "light"):
        c2 = br.new_context(viewport={"width": 320, "height": 800})
        c2.route("**/*", h); c2.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
        q = c2.new_page(); q.on("pageerror", lambda e: errs.append(str(e)))
        q.add_init_script("localStorage.setItem('tl_settings_v1', %s)" % json.dumps(json.dumps({"theme": theme, "fs": "xl"})))
        q.goto(B + "/", wait_until="load"); q.wait_for_timeout(300)
        bad = []
        for t in ("text", "image", "voice", "camera", "conversation", "money", "history"):
            q.evaluate("switchTab('%s')" % t); q.wait_for_timeout(80)
            if q.evaluate("document.documentElement.scrollWidth > innerWidth + 1"): bad.append(t)
        check(f"320px {theme} xl: no horizontal overflow {bad}", not bad)
        c2.close()
    br.close()
check(f"still no external request after everything {external}", not external)
check("no page errors " + str(errs), not errs)
print("FAILS:", fails)
sys.exit(1 if fails else 0)
