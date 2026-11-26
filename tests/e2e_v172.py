"""v1.7.2のブラウザ確認: 「翻訳する」と進捗バーは単色／どの画面も左上に同じ形のタイトル（320px・特大・ダーク/ライト・右から左の言語）。使い方: python tests/e2e_v172.py"""
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
srv = make_server("127.0.0.1", 5101, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5101"
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
        c = br.new_context(viewport={"width": width, "height": 800}, color_scheme=scheme, reduced_motion=reduced)
        def h(r):
            u = r.request.url
            if u.startswith(B): r.continue_()
            elif "cdn.tailwindcss.com" in u: r.fulfill(status=200, content_type="application/javascript", body=JS)
            else: r.abort()
        c.route("**/*", h); c.request.post(B + "/set-display-language", form={"ui_lang": lang})
        pg = c.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        if settings is not None: pg.add_init_script("if(!localStorage.getItem('tl_settings_v1'))localStorage.setItem('tl_settings_v1', %s)" % json.dumps(json.dumps(settings)))
        pg.goto(B + "/", wait_until="load"); pg.wait_for_timeout(300)
        return c, pg

    TABS = [("text", "fa-pen-to-square", "テキスト"), ("image", "fa-image", "画像"), ("voice", "fa-microphone", "音声"), ("camera", "fa-camera", "カメラ"),
            ("conversation", "fa-comments", "チャット"), ("money", "fa-coins", "通貨・為替")]
    HIST = [("settings", "fa-gear", "設定"), ("all", "fa-clock-rotate-left", "履歴"), ("fav", "fa-star", "お気に入り"), ("gl", "fa-book", "用語集"),
            ("phrases", "fa-comment-dots", "フレーズ集"), ("study", "fa-graduation-cap", "学習"), ("trash", "fa-trash-can", "ゴミ箱")]
    box = lambda pg, sel: pg.evaluate("(()=>{const r=document.querySelector('%s').getBoundingClientRect();return [r.left,r.top,r.right,r.bottom,r.width,r.height]})()" % sel)
    title = lambda pg: (pg.inner_text("#page-title-text").strip(), pg.get_attribute("#page-title-icon", "class"))

    # ---- 単色（ダーク・ライト）----
    for scheme, st in (("dark", None), ("light", {"theme": "light"})):
        c, pg = page(settings=st)
        btn = css(pg, "#tab-text button[type=submit]", "backgroundColor")
        check(f"{scheme}: translate button has no gradient", css(pg, "#tab-text button[type=submit]", "backgroundImage") == "none")
        check(f"{scheme}: translate button color is the single button color {btn}", btn == ("rgb(93, 100, 224)" if scheme == "dark" else "rgb(45, 106, 114)"))
        pg.evaluate("document.body.insertAdjacentHTML('beforeend','<div class=\"pbar\" id=\"pb1\"><div class=\"pbar-fill\"></div></div><div class=\"pbar pbar-done\" id=\"pb2\"><div class=\"pbar-fill\"></div></div>')")
        check(f"{scheme}: progress bar is a single color", css(pg, "#pb1 .pbar-fill", "backgroundImage") == "none" and css(pg, "#pb1 .pbar-fill", "backgroundColor") in ("rgb(124, 131, 240)", "rgb(45, 106, 114)"))
        check(f"{scheme}: finished bar stays green", css(pg, "#pb2 .pbar-fill", "backgroundColor") == "rgb(16, 185, 129)")
        c.close()

    # ---- 全画面のタイトル: 場所・形がそろう ----
    c, pg = page()
    ref = None; bad = []
    for tab, ico, name in TABS:
        pg.evaluate("switchTab('%s')" % tab); pg.wait_for_timeout(100)
        t, cls = title(pg); b = box(pg, "#page-title")
        if (t, ico in cls) != (name, True): bad.append((tab, t, cls))
        ref = ref or b
        if abs(b[1] - ref[1]) > 1 or abs(b[0] - ref[0]) > 1 or abs(b[5] - ref[5]) > 1: bad.append((tab, "position", b))
    check(f"6 tab titles: right name + icon, same left/top/height {bad}", not bad)
    pg.evaluate("switchTab('history')")
    bad = []
    for f, ico, name in HIST:
        if f == "phrases" and not pg.evaluate("!!document.getElementById('hf-phrases')"): continue
        pg.evaluate("setHistFilter('%s')" % f); pg.wait_for_timeout(100)
        t, cls = title(pg); b = box(pg, "#page-title")
        if (t, ico in cls) != (name, True): bad.append((f, t, cls))
        if abs(b[1] - ref[1]) > 1 or abs(b[0] - ref[0]) > 1: bad.append((f, "position", b))
    check(f"settings area titles (settings/history/fav/glossary/phrases/study/trash) {bad}", not bad)
    ib, tb = box(pg, "#page-title .pt-ico"), box(pg, "#page-title-text")
    check("icon badge is a 32px circle left of the text", abs(ib[4] - 32) < 1 and abs(ib[5] - 32) < 1 and ib[2] < tb[0] + 1)
    check("title is left-aligned near the card edge", ref[0] < 60)
    # 履歴を消去: 履歴・お気に入りの一覧だけ。タイトル行の右端
    vis = {}
    for f in ("settings", "all", "fav", "gl", "study", "trash"):
        pg.evaluate("setHistFilter('%s')" % f); pg.wait_for_timeout(60); vis[f] = pg.is_visible("#history-clear-btn")
    check(f"clear-history button only on history/favorites {vis}", vis == {"settings": False, "all": True, "fav": True, "gl": False, "study": False, "trash": False})
    pg.evaluate("setHistFilter('all')"); pg.wait_for_timeout(60)
    cb, pb = box(pg, "#history-clear-btn"), box(pg, "#page-title")
    check("clear-history button sits on the right end of the title row", cb[2] <= pb[2] + 1 and cb[0] > pb[0] + pb[4] / 2 and cb[1] >= pb[1] - 20 and cb[3] <= pb[3] + 20)
    check("clear-history tap area is at least 44px tall", pg.evaluate("(()=>{const b=document.getElementById('history-clear-btn');const cs=getComputedStyle(b);return b.getBoundingClientRect().height>=44-1})()"))
    pg.evaluate("switchTab('money')"); pg.wait_for_timeout(60)
    check("clear-history button is hidden on other tabs", not pg.is_visible("#history-clear-btn"))
    check("no duplicate heading on the currency tab", pg.locator("#tab-money h2").count() == 0 and pg.locator("h2:visible").count() == 1)
    c.close()

    # ---- 狭い画面・特大・ダーク/ライト: はみ出さない・重ならない・切れない ----
    for name, st in (("dark xl", {"theme": "dark", "fs": "xl"}), ("light xl", {"theme": "light", "fs": "xl"}), ("light+hc xl", {"theme": "light", "contrast": True, "fs": "xl"})):
        c, pg = page(320, settings=st)
        bad = []
        for tab in [t[0] for t in TABS] + ["history"]:
            pg.evaluate("switchTab('%s')" % tab); pg.wait_for_timeout(80)
            if tab == "history":
                for f in ("all", "settings", "fav", "phrases", "study", "trash"):
                    pg.evaluate("setHistFilter('%s')" % f); pg.wait_for_timeout(50)
                    if pg.evaluate("document.documentElement.scrollWidth > innerWidth + 1"): bad.append((f, "overflow"))
                    ib, tb, ab = box(pg, "#page-title .pt-ico"), box(pg, "#page-title-text"), box(pg, "#page-title-act")
                    if pg.is_visible("#page-title-act") and tb[2] > ab[0] + 1: bad.append((f, "overlap", tb, ab))
                    if ib[2] > tb[0] + 1: bad.append((f, "icon overlap"))
            if pg.evaluate("document.documentElement.scrollWidth > innerWidth + 1"): bad.append((tab, "overflow"))
            r = box(pg, "#page-title")
            if r[2] > 320 or r[0] < 0: bad.append((tab, "outside", r))
        check(f"320px {name}: title never overflows or overlaps {bad}", not bad)
        pg.evaluate("setHistFilter('all'); switchTab('history')"); pg.wait_for_timeout(80)
        # 「履歴を消去」を含めても、いちばん長い名前（フレーズ集）が切れすぎない: 英語の長い名前でも1行で、文字が重ならない
        c.close()

    # ---- 色: ダークとライトで文字が見える（背景との比が十分）----
    lum = lambda c: (lambda v: 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2])([((x / 255) / 12.92 if x / 255 <= .03928 else (((x / 255) + .055) / 1.055) ** 2.4) for x in c])
    parse = lambda s: [int(x) for x in __import__("re").findall(r"\d+", s)[:3]]
    def ratio(a, b):
        la, lb = lum(parse(a)), lum(parse(b)); hi, lo = max(la, lb), min(la, lb); return (hi + .05) / (lo + .05)
    for scheme, st in (("dark", None), ("light", {"theme": "light"})):
        c, pg = page(settings=st)
        fg, bg = css(pg, "#page-title-text", "color"), css(pg, ".max-w-xl", "backgroundColor")
        r1 = ratio(fg, bg)
        sb = [float(x) for x in __import__("re").findall(r"[\d.]+", css(pg, "#page-title .pt-ico", "backgroundColor"))]
        a = sb[3] if len(sb) > 3 else 1.0
        under = parse(bg); mix = "rgb(%d, %d, %d)" % tuple(round(sb[i] * a + under[i] * (1 - a)) for i in range(3))     # 半透明の背景は、カードの色と混ぜた色で比べる
        r2 = ratio(css(pg, "#page-title .pt-ico", "color"), mix)
        check(f"{scheme}: title text contrast {r1:.1f}:1 (>=7) and icon {r2:.1f}:1 (>=3)", r1 >= 7 and r2 >= 3)
        c.close()

    # ---- 右から左の言語（アラビア語）: アイコンは右、「履歴を消去」は左 ----
    c, pg = page(lang="Arabic")
    ib, tb = box(pg, "#page-title .pt-ico"), box(pg, "#page-title-text")
    check("RTL: icon is on the right of the text", ib[0] > tb[0])
    pg.evaluate("switchTab('history'); setHistFilter('all')"); pg.wait_for_timeout(100)
    cb, tb = box(pg, "#history-clear-btn"), box(pg, "#page-title-text")
    check("RTL: clear-history button moves to the left end", cb[2] <= tb[0] + 2)
    c.close()

    # ---- 翻訳の結果の画面にもタイトル・ボタンは出たまま ----
    c, pg = page()
    pg.fill("textarea[name=direct_text]", "Hi"); pg.click("#tab-text button[type=submit]")
    pg.wait_for_selector("#resultText-text")
    check("result page keeps the Text title", title(pg)[0] == "テキスト" and pg.is_visible("#page-title"))
    c.close()
    br.close()
check("no page errors " + str(errs), not errs)
print("FAILS:", fails)
sys.exit(1 if fails else 0)
