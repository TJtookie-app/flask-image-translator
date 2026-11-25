"""v1.4のブラウザ確認: 設定の翻訳スタイル7つ（狭い画面でも切れない・選ぶと保存され、翻訳の依頼に載る）／ニュアンス・使い方の解説（読む側/言う側）。使い方: python tests/e2e_v140.py"""
import json, os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import translator
from werkzeug.serving import make_server
from app import app

prompts = []
def fake(parts, system=None):
    p = parts[0] if parts and isinstance(parts[0], str) else ""
    prompts.append((system or "", p))
    if system and '"explanation"' in system:
        return '{"explanation":"meaning here"}'
    if "hello" in p.lower() or "good morning" in p.lower():
        return '{"detected_language":"English","source_text":"hello","translation":"こんにちは","pronunciation":""}'
    return '{"detected_language":"Japanese","source_text":"おはよう","translation":"Good morning","pronunciation":""}'
translator._generate = fake
srv = make_server("127.0.0.1", 5093, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5093"
fails = []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)
CSS = open(os.path.join(ROOT, "tests", "fixtures", "tailwind-local.css"), encoding="utf-8").read() + "\n.fa-solid,.fa-regular{display:inline-block;width:1em;height:1em}"
JS = "(()=>{const s=document.createElement('style');s.textContent=%s;document.head.appendChild(s)})()" % json.dumps(CSS)

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch()
    for width, ui in ((320, "Japanese"), (360, "English"), (390, "Japanese")):
        ctx = br.new_context(viewport={"width": width, "height": 900}, locale="ja-JP" if ui == "Japanese" else "en-US")
        def h(r):
            u = r.request.url
            if u.startswith(B): r.continue_()
            elif "cdn.tailwindcss.com" in u: r.fulfill(status=200, content_type="application/javascript", body=JS)
            else: r.abort()
        ctx.route("**/*", h); ctx.request.post(B + "/set-display-language", form={"ui_lang": ui})
        pg = ctx.new_page(); pg.goto(B + "/", wait_until="load"); pg.wait_for_timeout(300)
        pg.click("#nav-history"); pg.click("#hf-settings"); pg.wait_for_timeout(300)
        btns = pg.evaluate("""[...document.querySelectorAll('[data-setting=formality] .set-opt')].map(b => {
            const r = b.getBoundingClientRect(); return [b.dataset.v, Math.round(r.left), Math.round(r.right), b.scrollWidth > b.clientWidth + 1, b.textContent.trim()]; })""")
        tag = f"{width}px {ui[:2]}"
        check(f"{tag}: 7 style buttons {[b[0] for b in btns]}", [b[0] for b in btns] == ["auto", "natural", "literal", "formal", "business", "casual", "slang"])
        check(f"{tag}: buttons inside the screen and text not cut", all(b[1] >= 0 and b[2] <= width and not b[3] for b in btns) and all(b[4] for b in btns))
        rows = len({round(pg.evaluate("(i)=>document.querySelectorAll('[data-setting=formality] .set-opt')[i].getBoundingClientRect().top", i)) for i in range(7)})
        check(f"{tag}: laid out in 2 rows ({rows})", rows == 2)
        check(f"{tag}: no horizontal page scroll", pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
        pg.click("[data-setting=formality] [data-v=slang]"); pg.wait_for_timeout(100)
        st = pg.evaluate("JSON.parse(localStorage.getItem('tl_settings_v1'))")
        check(f"{tag}: slang saved {st.get('formality')}", st.get("formality") == "slang")
        pg.reload(wait_until="load"); pg.add_style_tag(content=CSS)
        pg.click("#nav-history"); pg.click("#hf-settings")
        check(f"{tag}: slang still selected after reload", pg.get_attribute("[data-setting=formality] [data-v=slang]", "aria-pressed") == "true")
        if width == 390:
            # 選んだスタイルが、翻訳の依頼に載る
            pg.click("#nav-text"); pg.fill("textarea[name=direct_text]", "hello"); prompts.clear()
            pg.click("#tab-text button[type=submit]"); pg.wait_for_selector("#resultText-text")
            check("slang style reached the translate prompt", any("slang" in q for _, q in prompts))
            # 外国語（英語）を読むとき: 原文を解説する
            reqs = []
            pg.on("request", lambda r: reqs.append(r.post_data) if r.url.endswith("/api/explain") else None)
            pg.click("#tab-text .rc-more"); pg.click("text=ニュアンス・使い方を解説" if ui == "Japanese" else "text=Explain nuance & usage")
            pg.wait_for_function("document.getElementById('explain-text').textContent.includes('meaning here')", timeout=8000)
            body = json.loads(reqs[-1])
            check(f"reading a foreign message: explains the original {body}", body["text"] == "hello" and body["lang"] == "English")
            # 自分の言語で入力したとき: 相手に言う側（訳文）を解説する
            pg.fill("textarea[name=direct_text]", "おはよう"); pg.click("#tab-text button[type=submit]"); pg.wait_for_selector("#resultText-text")
            pg.click("#tab-text .rc-more"); pg.click("text=ニュアンス・使い方を解説")
            pg.wait_for_function("document.getElementById('explain-text').textContent.includes('meaning here')", timeout=8000)
            RESULT_TGT = pg.evaluate("RESULT.tgt")
            body = json.loads(reqs[-1])
            check(f"own-language input: explains the translation {body}", body["text"] == "Good morning" and body["lang"] == RESULT_TGT)
        ctx.close()
    br.close()
print("FAILS:", fails)
sys.exit(1 if fails else 0)
