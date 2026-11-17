"""V12.8のブラウザ確認: 下のタブバーが固定される（通貨は履歴の左隣）・入力中はバーを隠す。使い方: python tests/e2e_v128.py
※ Tailwind の CDN は遮断して試すので、ヘッダーの細かい幅は確認できません（バーは style.css だけで作っているので確認できます）。"""
import json, os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import rates
from werkzeug.serving import make_server
from app import app

rates._http_get = lambda url: {"result": "success", "time_last_update_unix": 1794900000, "base_code": "USD",
    "rates": {**{f"X{chr(65 + i // 26)}{chr(65 + i % 26)}": 1.5 + i for i in range(60)}, "USD": 1, "JPY": 154.3}}
srv = make_server("127.0.0.1", 5088, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5088"
errs, fails = [], []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

def rect(pg, sel):
    return pg.evaluate("(s) => { const r = document.querySelector(s).getBoundingClientRect(); return {top: r.top, bottom: r.bottom, left: r.left, right: r.right, width: r.width, height: r.height}; }", sel)

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch()
    def ctxmake(**kw):
        c = br.new_context(locale="ja-JP", timezone_id="Asia/Tokyo", **kw)
        c.route("**/*", lambda r: r.continue_() if r.request.url.startswith(B) else r.abort())
        c.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
        pg = c.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(B + "/", wait_until="domcontentloaded")
        return c, pg

    # ---------- スマホ幅（タッチ） ----------
    ctx, pg = ctxmake(viewport={"width": 390, "height": 700}, has_touch=True, is_mobile=True, device_scale_factor=2)
    H = pg.evaluate("window.innerHeight")
    order = pg.evaluate("[...document.querySelectorAll('#bottom-nav .nav-btn')].map(b => b.id.replace('nav-', ''))")
    check(f"bottom bar: 7 tabs, history rightmost, money second from right ({order})", order == ["text", "image", "voice", "camera", "conversation", "money", "history"])
    check("bar is position: fixed", pg.evaluate("getComputedStyle(document.getElementById('bottom-nav')).position") == "fixed")
    r = rect(pg, ".bottom-nav-in"); check(f"capsule floats just above the bottom edge, inset from the sides ({r})", 2 <= H - r["bottom"] <= 40 and 8 <= r["left"] <= 16 and 390 - r["right"] >= 8 and r["width"] < 380)
    check("capsule has rounded corners", float(pg.evaluate("parseFloat(getComputedStyle(document.querySelector('.bottom-nav-in')).borderTopLeftRadius)")) >= 20)
    check("outside the capsule, touches reach the page (pointer-events: none)", pg.evaluate("getComputedStyle(document.getElementById('bottom-nav')).pointerEvents") == "none")
    # ボタンが6つに減っても、残りは幅を均等に分ける（空きの列ができない）
    ws = pg.evaluate("""() => { const bs = [...document.querySelectorAll('#bottom-nav .nav-btn')]; bs[3].remove(); const w = bs.filter(b => b.isConnected).map(b => b.getBoundingClientRect().width); const box = document.querySelector('.bottom-nav-in').getBoundingClientRect(); const last = bs[6].getBoundingClientRect(); return [Math.max(...w) - Math.min(...w), box.right - last.right]; }""")
    check(f"buttons share the width evenly even if one is missing ({ws})", ws[0] < 1 and ws[1] < 14)
    pg.reload(wait_until="domcontentloaded")
    # 中身を長くして、スクロールしてもバーが動かない
    pg.evaluate("(() => { const d = document.createElement('div'); d.id = 'filler'; d.style.height = '3000px'; document.querySelector('#tab-text').after(d); })()")
    top0 = rect(pg, ".bottom-nav-in")["top"]
    pg.evaluate("window.scrollTo(0, 1500)"); pg.wait_for_timeout(100)
    check("bar does not move when the page scrolls", pg.evaluate("window.scrollY") > 500 and abs(rect(pg, ".bottom-nav-in")["top"] - top0) < 1)
    pg.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)"); pg.wait_for_timeout(100)
    pr, br_ = rect(pg, "a[href='/privacy']"), rect(pg, ".bottom-nav-in")
    check(f"last content (privacy link) is not hidden under the bar ({pr['bottom']:.0f} <= {br_['top']:.0f})", pr["bottom"] <= br_["top"] + 0.5)
    check("privacy link is no longer inside the bar", pg.locator("#bottom-nav a").count() == 0)
    pg.evaluate("document.getElementById('filler').remove(); window.scrollTo(0, 0)")
    check("bar is under overlays (z-index below the viewers)", int(pg.evaluate("getComputedStyle(document.getElementById('bottom-nav')).zIndex")) < 60)

    # 通貨はバーの中（履歴の左隣）。ヘッダーにはない
    check("header has no money button", pg.locator("#nav-money").count() == 1 and pg.locator("#bottom-nav #nav-money").count() == 1)
    mr, hr = rect(pg, "#nav-money"), rect(pg, "#nav-history")
    check(f"money sits immediately left of history ({mr}, {hr})", mr["right"] <= hr["left"] + 4 and abs(mr["top"] - hr["top"]) < 2 and hr["right"] > 360)
    pg.click("#nav-money")
    pg.wait_for_function("document.getElementById('money-status').textContent.includes('レート更新')", timeout=8000)
    check("tap -> money tab opens", "hidden" not in pg.get_attribute("#tab-money", "class") and "hidden" in pg.get_attribute("#tab-text", "class"))
    check("money tab is highlighted in the bar", pg.evaluate("document.getElementById('nav-money').classList.contains('text-indigo-400')"))
    check("language bar is hidden on the money tab", "hidden" in pg.get_attribute("#language-bar-wrapper", "class"))
    r = rect(pg, ".bottom-nav-in"); check("bar still fixed on the money tab", abs(r["bottom"] - (H - 0)) < 40 and abs(r["top"] - top0) < 1)
    pg.click("#nav-history")
    check("history tab: money turns off", "hidden" in pg.get_attribute("#tab-money", "class") and not pg.evaluate("document.getElementById('nav-money').classList.contains('text-indigo-400')")
          and pg.evaluate("document.getElementById('nav-history').classList.contains('text-indigo-400')"))
    pg.click("#nav-text")
    check("back to text tab", "hidden" not in pg.get_attribute("#tab-text", "class"))

    # 「元に戻す」の通知はバーの上に出る
    pg.evaluate("undoToast('t1')")
    tr = rect(pg, "#undo-toast"); br_ = rect(pg, ".bottom-nav-in")
    check(f"undo toast is above the bar ({tr['bottom']:.0f} <= {br_['top']:.0f})", tr["bottom"] <= br_["top"] + 0.5)

    # 入力中（スマホ）はバーを隠す
    pg.click("textarea[name=direct_text]")
    pg.wait_for_function("document.body.classList.contains('kb-open')", timeout=3000)
    check("typing on a touch device hides the bar", pg.evaluate("getComputedStyle(document.getElementById('bottom-nav')).display") == "none")
    pg.evaluate("document.activeElement.blur()")
    pg.wait_for_function("!document.body.classList.contains('kb-open')", timeout=3000)
    check("bar comes back when typing ends", pg.evaluate("getComputedStyle(document.getElementById('bottom-nav')).display") != "none")
    pg.click("#nav-money")
    pg.wait_for_selector("#money-amount", state="attached")
    pg.focus("#money-from")
    check("choosing from a dropdown (select) does not hide the bar", not pg.evaluate("document.body.classList.contains('kb-open')"))
    ctx.close()

    # ---------- 幅の狭いスマホ（320px）: 言語ボタンはアイコンだけ ----------
    ctx, pg = ctxmake(viewport={"width": 320, "height": 640})
    check("320px: language button text is hidden (icon stays)", pg.evaluate("getComputedStyle(document.querySelector('.hdr-lang-text')).display") == "none")
    check("320px: 7 buttons share the bar width", pg.evaluate("[...document.querySelectorAll('#bottom-nav .nav-btn')].every(b => b.getBoundingClientRect().width > 36)"))
    ctx.close()
    ctx, pg = ctxmake(viewport={"width": 360, "height": 700})
    check("360px: language button text is hidden too", pg.evaluate("getComputedStyle(document.querySelector('.hdr-lang-text')).display") == "none")
    ctx.close()
    ctx, pg = ctxmake(viewport={"width": 390, "height": 700})
    check("390px: language button text is shown", pg.evaluate("getComputedStyle(document.querySelector('.hdr-lang-text')).display") != "none")
    ctx.close()

    # ---------- パソコン（広い画面）: バーは中央の幅に収まり、タッチでないので隠さない ----------
    ctx, pg = ctxmake(viewport={"width": 1280, "height": 800})
    r = rect(pg, ".bottom-nav-in"); check(f"desktop: bar content centered, max 36rem ({r['width']:.0f}px)", r["width"] <= 577 and abs((r["left"] + r["right"]) / 2 - 640) < 2)
    pg.click("textarea[name=direct_text]")
    check("desktop: typing does not hide the bar", not pg.evaluate("document.body.classList.contains('kb-open')"))
    # ライトテーマ
    pg.evaluate("document.documentElement.setAttribute('data-theme', 'light')")
    check("light theme: bar background is light", pg.evaluate("getComputedStyle(document.querySelector('.bottom-nav-in')).backgroundColor").startswith("rgba(255, 255, 255"))
    ctx.close()

    # ---------- 他のページには影響しない ----------
    ctx, pg = ctxmake(viewport={"width": 390, "height": 700})
    pg.goto(B + "/privacy", wait_until="domcontentloaded"); check("privacy page has no bottom bar", pg.locator("#bottom-nav").count() == 0)
    pg.goto(B + "/offline", wait_until="domcontentloaded"); check("offline page has no bottom bar, money section still shown", pg.locator("#bottom-nav").count() == 0 and pg.locator("#tab-money").count() == 1)
    br.close()
check(f"no JS page errors ({errs})", not errs)
print("FAILS:", fails); sys.exit(1 if fails else 0)
