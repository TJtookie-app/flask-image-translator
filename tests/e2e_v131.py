"""v1.3.1のブラウザ確認: ボタン列の「先がある」合図。使い方: python tests/e2e_v131.py"""
import json, os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
from werkzeug.serving import make_server
from app import app

srv = make_server("127.0.0.1", 5091, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5091"
fails = []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)
CSS = open(os.path.join(ROOT, "tests", "fixtures", "tailwind-local.css"), encoding="utf-8").read() + "\n.fa-solid,.fa-regular{display:inline-block;width:1em;height:1em}"
ST = """() => { const b = document.getElementById('hist-scroll'), c = document.getElementById('hist-chips');
  const vis = id => getComputedStyle(document.getElementById(id)).display !== 'none';
  return {l: vis('hist-arrow-l'), r: vis('hist-arrow-r'), sl: c.scrollLeft, span: c.scrollWidth - c.clientWidth}; }"""

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch()
    for width, ui in ((320, "Japanese"), (360, "English"), (390, "Japanese"), (360, "Arabic")):
        ctx = br.new_context(viewport={"width": width, "height": 800})
        ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(B) else r.abort())
        ctx.request.post(B + "/set-display-language", form={"ui_lang": ui})
        pg = ctx.new_page(); pg.goto(B + "/", wait_until="domcontentloaded"); pg.add_style_tag(content=CSS)
        pg.click("#nav-history"); pg.wait_for_timeout(450)
        tag = f"{width}px {ui[:2]}"
        rtl = pg.evaluate("getComputedStyle(document.getElementById('hist-chips')).direction") == "rtl"
        s = pg.evaluate(ST)
        if s["span"] > 4:
            # 最初は、「始まりの側」が端。先がある側にだけ矢印が出る
            check(f"{tag}: at start, only the 'more' arrow shows {s}", (s["l"] if rtl else s["r"]) and not (s["r"] if rtl else s["l"]))
            pg.click("#hist-arrow-l" if rtl else "#hist-arrow-r"); pg.wait_for_timeout(700)
            s2 = pg.evaluate(ST)
            check(f"{tag}: tapping the arrow scrolls the row {s['sl']}→{s2['sl']}", s2["sl"] != s["sl"])
            check(f"{tag}: both arrows may show in the middle, or the far one hid {s2}", s2["l"] or s2["r"])
            pg.evaluate("(() => { const c = document.getElementById('hist-chips'); c.scrollLeft = %s; })()" % ("-c.scrollWidth" if rtl else "c.scrollWidth")); pg.wait_for_timeout(300)
            s3 = pg.evaluate(ST)
            check(f"{tag}: at the far end the arrow for that side is gone {s3}", not (s3["l"] if rtl else s3["r"]) and (s3["r"] if rtl else s3["l"]))
            # 選んだボタンが矢印の下に隠れない
            pg.click("#hf-trash" if not rtl else "#hf-settings"); pg.wait_for_timeout(700)
            ok = pg.evaluate("""(id) => { const b = document.getElementById(id).getBoundingClientRect(), c = document.getElementById('hist-chips').getBoundingClientRect();
              return b.left >= c.left - 1 && b.right <= c.right + 1; }""", "hf-trash" if not rtl else "hf-settings")
            check(f"{tag}: selected chip fully inside the row", ok)
        else:
            check(f"{tag}: row fits, no arrows {s}", not s["l"] and not s["r"])
        check(f"{tag}: no horizontal page scroll", pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
        ctx.close()
    br.close()
print("FAILS:", fails)
sys.exit(1 if fails else 0)
