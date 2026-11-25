"""v1.3 のブラウザ確認: 設定タブのボタン列は1行・横にスクロール／狭い画面＋特大文字でも、下のナビの文字が重ならない。使い方: python tests/e2e_v130.py"""
import os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
from werkzeug.serving import make_server
from app import app

srv = make_server("127.0.0.1", 5095, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5095"
CSS = open(os.path.join(ROOT, "tests", "fixtures", "tailwind-local.css"), encoding="utf-8").read() + "\n.fa-solid,.fa-regular{display:inline-block;width:1em;height:1em}"
fails = []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch()
    for width, fs in ((320, "xl"), (360, "m"), (390, "l")):
        ctx = br.new_context(viewport={"width": width, "height": 800})
        ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(B) else r.abort())
        ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
        pg = ctx.new_page(); pg.goto(B + "/", wait_until="domcontentloaded")
        pg.evaluate("(s)=>localStorage.setItem('tl_settings_v1', JSON.stringify(s))", {"theme": "dark", "fs": fs, "formality": "auto", "pron": True})
        pg.reload(wait_until="domcontentloaded"); pg.add_style_tag(content=CSS)
        pg.click("#nav-history")
        tops = pg.evaluate("[...document.querySelectorAll('#hist-chips .hist-chip')].map(b => Math.round(b.getBoundingClientRect().top))")
        check(f"{width}px/{fs}: chips on one line {set(tops)}", len(set(tops)) == 1 and len(tops) >= 6)
        sw = pg.evaluate("(() => { const e = document.getElementById('hist-chips'); return [e.scrollWidth, e.clientWidth]; })()")
        check(f"{width}px/{fs}: chip row scrolls sideways {sw}", sw[0] >= sw[1])
        # 選んだボタン（ゴミ箱）が、見える位置に動く
        pg.click("#hf-trash"); pg.wait_for_timeout(200)
        vis = pg.evaluate("(() => { const b = document.getElementById('hf-trash').getBoundingClientRect(), c = document.getElementById('hist-chips').getBoundingClientRect(); return b.left >= c.left - 1 && b.right <= c.right + 1; })()")
        check(f"{width}px/{fs}: selected chip scrolled into view", vis)
        # 下のナビの文字が、隣と重ならない
        boxes = pg.evaluate("[...document.querySelectorAll('#bottom-nav .nav-btn span')].map(s => { const r = s.getBoundingClientRect(); return [r.left, r.right, s.scrollWidth, s.clientWidth]; })")
        gaps = [boxes[i + 1][0] - boxes[i][1] for i in range(len(boxes) - 1)]
        check(f"{width}px/{fs}: nav labels do not overlap {['%.1f' % g for g in gaps]}", all(g >= -0.5 for g in gaps) and all(b[2] <= b[3] + 1 for b in boxes))
        # 横にはみ出さない
        check(f"{width}px/{fs}: no horizontal page scroll", pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
        ctx.close()
    br.close()
print("FAILS:", fails)
sys.exit(1 if fails else 0)
