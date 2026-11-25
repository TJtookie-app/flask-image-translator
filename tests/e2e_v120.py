"""v1.2 のブラウザ確認: 口調を変える（3つ→選ぶと訳と履歴が置き換わる）／要約（600字以上でボタン→押すと要約）。使い方: python tests/e2e_v120.py"""
import os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import translator
from werkzeug.serving import make_server
from app import app

calls = []
def fake(parts, system=None):
    calls.append(system or "")
    if system and '"formal"' in system:
        return '{"formal":"Good day.","neutral":"Hello.","casual":"Hey!"}'
    if system and '"summary"' in system:
        return '{"summary":"- first point\\n- second point"}'
    return '{"detected_language":"Japanese","source_text":"x","translation":"Hello","pronunciation":""}'
translator._generate = fake
srv = make_server("127.0.0.1", 5092, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5092"
fails = []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 390, "height": 900})
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(B) else r.abort())
    ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
    pg = ctx.new_page()

    # --- 短い文: 要約ボタンは無い。口調を変える ---
    pg.goto(B + "/", wait_until="domcontentloaded")
    pg.fill("textarea[name=direct_text]", "こんにちは")
    pg.click("#tab-text button[type=submit]")
    pg.wait_for_selector("#resultText-text")
    check("short text: no summary button", pg.locator("#summary-btn-text").count() == 0)
    pg.click("#tab-text .rc-more")
    check("tone item in menu", pg.is_visible("text=口調を変える"))
    pg.click("text=口調を変える")
    pg.wait_for_selector("#tones-text .tone-chip")
    chips = pg.locator("#tones-text .tone-chip")
    check("three tone chips (formal/neutral/casual)", chips.count() == 3)
    txt = pg.inner_text("#tones-text")
    check("chips show names and texts", "丁寧" in txt and "標準" in txt and "くだけた" in txt and "Good day." in txt and "Hey!" in txt)
    check("one API call for 3 tones", calls.count([c for c in calls if '"formal"' in c][0]) == 1)
    pg.click("#tones-text .tone-chip >> nth=2")
    check("result replaced by casual", pg.inner_text("#resultText-text").strip() == "Hey!")
    check("tone box closed", not pg.is_visible("#tones-text"))
    hist = pg.evaluate("JSON.parse(localStorage.getItem('tl_history_v1') || localStorage.getItem('tl_history') || '[]')")
    ok_hist = bool(hist) and hist[0].get("out") == "Hey!"
    if not hist:   # 履歴の保存キーが違う場合は、画面の履歴で確かめる
        pg.click("#nav-history"); pg.click("#hf-all")
        ok_hist = "Hey!" in pg.inner_text("#history-list")
    check("history updated to the chosen tone", ok_hist)

    # --- 長文: 要約ボタン ---
    pg.goto(B + "/", wait_until="domcontentloaded")
    pg.fill("textarea[name=direct_text]", "あ" * 650)
    pg.click("#tab-text button[type=submit]")
    pg.wait_for_selector("#resultText-text")
    check("long text: summary button shown", pg.is_visible("#summary-btn-text"))
    check("summary hidden before click", not pg.is_visible("#summary-text"))
    n = len(calls)
    pg.click("#summary-btn-text")
    pg.wait_for_function("document.getElementById('summary-text').innerText.includes('first point')")
    check("summary shown after click", "second point" in pg.inner_text("#summary-text") and "要約" in pg.inner_text("#summary-text"))
    check("exactly one extra API call for summary", len(calls) == n + 1)
    br.close()

print("FAILS:", fails)
sys.exit(1 if fails else 0)
