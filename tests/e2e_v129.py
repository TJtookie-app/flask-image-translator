"""V12.9のブラウザ確認: スマホ幅（390/360/320px、日本語・英語）で、どのタブでも「横にはみ出さない・ヘッダーが重ならない・下のバーの文字が切れない」。
Tailwind の CDN は使えないので、手元で作った同等の CSS（tests/fixtures/tailwind-local.css）を差し込んで、実際の幅で測ります。
（アイコンの FontAwesome は入らないので、幅1emの箱で代用します）使い方: python tests/e2e_v129.py"""
import json, os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import rates
from werkzeug.serving import make_server
from app import app

rates._http_get = lambda url: {"result": "success", "time_last_update_unix": 1794900000, "base_code": "USD",
    "rates": {**{f"X{chr(65 + i // 26)}{chr(65 + i % 26)}": 1.5 + i for i in range(60)}, "USD": 1, "JPY": 154.3, "EUR": 0.92, "KRW": 1350.0}}
srv = make_server("127.0.0.1", 5089, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5089"
errs, fails = [], []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

CSS = open(os.path.join(ROOT, "tests", "fixtures", "tailwind-local.css"), encoding="utf-8").read() + "\n.fa-solid,.fa-regular{display:inline-block;width:1em;height:1em}"
JS = "(()=>{const s=document.createElement('style');s.textContent=%s;document.head.appendChild(s)})()" % json.dumps(CSS)
PROBE = """() => {
  const card = document.querySelector('.max-w-xl'); const cr = card.getBoundingClientRect(); const vw = innerWidth; const out = [];
  document.querySelectorAll('body *').forEach(e => {
    if (e.closest('#bottom-nav') || e.closest('.hidden') || ['SCRIPT', 'OPTION', 'STYLE'].includes(e.tagName) || e.closest('.money-popup')) return;
    const r = e.getBoundingClientRect(); if (!r.width || !r.height) return;
    const cs = getComputedStyle(e); if (cs.visibility === 'hidden' || cs.display === 'none' || cs.position === 'fixed') return;
    if (r.right > vw + 0.5 || r.left < -0.5 || r.right > cr.right + 0.5) out.push([e.id || e.className.toString().slice(0, 50), Math.round(r.left), Math.round(r.right)]);
  });
  const brand = document.querySelector('.hdr-brand').getBoundingClientRect(), btns = document.querySelector('.hdr-brand').nextElementSibling.getBoundingClientRect();
  const navCut = [...document.querySelectorAll('#bottom-nav .nav-btn span')].filter(s => s.scrollWidth > s.clientWidth + 0.5).map(s => s.textContent);
  const sub = document.querySelector('.hdr-brand span:last-child');
  return {scrollW: document.documentElement.scrollWidth, vw, out: out.slice(0, 8), headerOverlap: brand.right > btns.left + 0.5, navCut, subtitleCut: sub.scrollWidth > sub.clientWidth + 0.5};
}"""

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch()
    for W in (390, 360, 320):
        for ui in ("Japanese", "English"):
            c = br.new_context(locale="ja-JP" if ui == "Japanese" else "en-US", timezone_id="Asia/Tokyo", viewport={"width": W, "height": 800}, has_touch=True, is_mobile=True, device_scale_factor=2)
            def h(r):
                u = r.request.url
                if u.startswith(B): r.continue_()
                elif "cdn.tailwindcss.com" in u: r.fulfill(status=200, content_type="application/javascript", body=JS)
                else: r.abort()
            c.route("**/*", h); c.request.post(B + "/set-display-language", form={"ui_lang": ui})
            pg = c.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(B + "/", wait_until="load"); pg.wait_for_timeout(300)
            tag = f"{W}px {ui[:2]}"
            bad = []
            for tab in ("text", "image", "voice", "camera", "conversation", "money", "history"):
                pg.evaluate("switchTab('%s')" % tab)
                if tab == "money": pg.wait_for_function("document.getElementById('money-status').textContent.length > 0 && !document.getElementById('money-status').textContent.match(/loading|読み込/i)", timeout=8000)
                pg.wait_for_timeout(200)
                r = pg.evaluate(PROBE)
                if r["scrollW"] > r["vw"] or r["out"]: bad.append((tab, r["scrollW"], r["out"]))
            check(f"{tag}: no horizontal overflow on any tab ({bad})", not bad)
            r = pg.evaluate(PROBE)
            check(f"{tag}: header logo and buttons do not overlap, subtitle not cut", not r["headerOverlap"] and not r["subtitleCut"])
            check(f"{tag}: bottom bar labels are not cut ({r['navCut']})", not r["navCut"])
            c.close()
    br.close()
check(f"no JS page errors ({errs})", not errs)
print("FAILS:", fails); sys.exit(1 if fails else 0)
