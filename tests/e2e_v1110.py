"""v1.11.0（中国語・韓国語を追加、英語を経由した訳、言語バーを選べる形に）のブラウザ確認。翻訳エンジンとモデルは模擬
（出力に、入力と、使ったモデルの名前が入るので、手順と、中国語の文字の指定が正しいかを確かめられる）。使い方: python tests/e2e_v1110.py"""
import os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import rates
from werkzeug.serving import make_server
from app import app

rates._http_get = lambda url: {"result": "success", "time_last_update_unix": 1794900000, "base_code": "USD", "rates": {"USD": 1, "JPY": 154.3}}
srv = make_server("127.0.0.1", 5109, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5109"
LIB = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.5.2"
CORS = {"Access-Control-Allow-Origin": "*"}
FAKE = """
export const env = { allowLocalModels: true, useBrowserCache: false, allowRemoteModels: true, backends: { onnx: { wasm: {} } } };
export async function pipeline(task, model, opts) {
  const c = await caches.open('transformers-cache');
  for (const f of ['onnx/encoder_model_quantized.onnx', 'onnx/decoder_model_merged_quantized.onnx', 'tokenizer.json']) {
    opts.progress_callback({ status: 'progress', file: f, loaded: 100, total: 100 });
    await c.put('https://huggingface.co/' + model + '/resolve/main/' + f, new Response('x'));
  }
  const tag = model.split('/')[1].replace('opus-mt-', '');
  const p = async (text) => [{ translation_text: '<' + tag + ':' + text + '>' }];
  p.dispose = async () => { self.__disposed = (self.__disposed || 0) + 1; };
  return p;
}
"""
fails, errs = [], []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

from playwright.sync_api import sync_playwright
def new_ctx(br, width=390, theme=None, target="English"):
    ctx = br.new_context(viewport={"width": width, "height": 900}, service_workers="block")
    def h(r):
        u = r.request.url
        if u.startswith(LIB): r.fulfill(status=200, body=FAKE, headers=CORS, content_type="application/javascript")
        elif u.startswith(B) or u.startswith("data:") or u.startswith("blob:"): r.continue_()
        else: r.abort()
    ctx.route("**/*", h)
    ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
    p0 = ctx.new_page(); p0.goto(B + "/", wait_until="networkidle")
    p0.evaluate("(t) => fetch('/set-language', {method: 'POST', body: new URLSearchParams({target_lang: t, lang_type: 'target'})}).then(r => r.status)", target); p0.close()
    if theme: ctx.add_init_script("localStorage.setItem('tl_settings_v1', %r)" % ('{"theme":"%s"}' % theme))
    return ctx
def get_model(pg, pair):
    pg.evaluate("if (document.getElementById('nav-history')) switchTab('history'); setHistFilter('settings')"); pg.wait_for_timeout(200)
    pg.locator(f'.omt-row[data-pair="{pair}"] .omt-get').click()
    pg.wait_for_function(f"document.querySelector('.omt-row[data-pair=\"{pair}\"] .omt-del:not(.hidden)')", timeout=10000)
def bar(pg): return (pg.input_value("#omt-tab-from"), pg.input_value("#omt-tab-to"))
def dis(pg, sel, v): return pg.eval_on_selector(f"{sel} option[value='{v}']", "o => o.disabled")
def run(pg, text, expect):
    pg.fill("#omt-tab-in", text); pg.click("#omt-tab-run")
    pg.wait_for_function("(e) => { const t = document.getElementById('omt-tab-out').textContent; return t.includes(e) && !t.includes('翻訳しています'); }", arg=expect, timeout=10000)
    return pg.inner_text("#omt-tab-out")

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = new_ctx(br)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/offline", wait_until="load"); pg.wait_for_timeout(500)

    # ---- 1) 言語バーは選べる形。使えない組み合わせは選べない ----
    check("both bars list the five languages", pg.locator("#omt-tab-from option").count() == 5 and pg.locator("#omt-tab-to option").count() == 5)
    check("starts as Japanese → English; the swap button is still in the middle", bar(pg) == ("Japanese", "English") and pg.locator("#omt-tab-swap").is_visible())
    check("To: Korean (no model exists) is not selectable; Chinese is (via English)", dis(pg, "#omt-tab-to", "Korean") and not dis(pg, "#omt-tab-to", "Chinese (Simplified)") and not dis(pg, "#omt-tab-to", "English") and not dis(pg, "#omt-tab-to", "Japanese"))
    pg.select_option("#omt-tab-from", "Korean")
    check("From Korean: To can be Japanese/English/Chinese; Japanese stays valid", bar(pg)[0] == "Korean" and not dis(pg, "#omt-tab-to", "Japanese") and not dis(pg, "#omt-tab-to", "Chinese (Traditional)"))
    pg.select_option("#omt-tab-from", "English")
    check(f"From English while To is English: they swap, and the To is re-chosen because English → Korean has no model {bar(pg)}", bar(pg) == ("English", "Japanese"))
    pg.select_option("#omt-tab-to", "English")
    check(f"choosing the same language on the other side swaps them {bar(pg)}", bar(pg) == ("Japanese", "English"))
    pg.select_option("#omt-tab-from", "Korean"); pg.select_option("#omt-tab-to", "Korean") if False else None
    pg.select_option("#omt-tab-to", "Chinese (Simplified)"); pg.select_option("#omt-tab-from", "English")
    check(f"From English with To Chinese stays valid {bar(pg)}", bar(pg) == ("English", "Chinese (Simplified)"))
    pg.select_option("#omt-tab-from", "Japanese"); pg.select_option("#omt-tab-to", "Chinese (Simplified)")
    check("Japanese → Chinese (Simplified) is selectable", bar(pg) == ("Japanese", "Chinese (Simplified)"))

    # ---- 2) 足りないモデルは、名前で案内する（経由なので2つ） ----
    pg.fill("#omt-tab-in", "こんにちは")
    need = pg.inner_text("#omt-tab-need")
    check(f"missing models are named: 日本語 → 英語 and 英語 → 中国語 {need!r}", "日本語 → 英語" in need and "英語 → 中国語" in need)
    pg.click("#omt-tab-run"); pg.wait_for_function("!document.getElementById('omt-tab-err').classList.contains('hidden')", timeout=5000)
    check("running without them: the error also names them", "英語 → 中国語" in pg.inner_text("#omt-tab-err"))

    # ---- 3) ダウンロード → 経由で訳す（中国語の文字の指定が付く） ----
    get_model(pg, "ja-en")
    check("one of the two is not enough: still guided", "英語 → 中国語" in pg.inner_text("#omt-tab-need") and "日本語 → 英語" not in pg.inner_text("#omt-tab-missing"))
    get_model(pg, "en-zh")
    pg.wait_for_function("!document.getElementById('omt-tab-need').offsetParent", timeout=5000)
    out = run(pg, "こんにちは", "en-zh")
    check(f"ja→zh goes ja-en then en-zh with the Simplified marker {out!r}", out == "<en-zh:>>cmn_Hans<< <ja-en:こんにちは>>" and "英語を経由" in pg.inner_text("#omt-tab-label"))
    pg.select_option("#omt-tab-to", "Chinese (Traditional)")
    out = run(pg, "こんにちは", "cmn_Hant")
    check(f"Traditional uses its own marker {out!r}", out == "<en-zh:>>cmn_Hant<< <ja-en:こんにちは>>")
    hist = pg.evaluate("loadHistory()[0]")
    check(f"history keeps the language names {hist['srcLang']}→{hist['tgt']}", hist["srcLang"] == "Japanese" and hist["tgt"] == "Chinese (Traditional)" and hist["offline"] is True)

    # ---- 4) 直接の組み合わせ・かな／ハングル／英語に合わせたバー ----
    pg.select_option("#omt-tab-to", "English")
    out = run(pg, "おはよう", "おはよう")
    check(f"ja→en direct {out!r}", out == "<ja-en:おはよう>")
    get_model(pg, "ko-en"); get_model(pg, "zh-en")
    pg.fill("#omt-tab-in", "안녕하세요")
    check(f"typing Hangul turns the bar into Korean → English {bar(pg)}", bar(pg) == ("Korean", "English"))
    out = run(pg, "안녕하세요", "ko-en")
    check(f"ko→en {out!r}", out == "<ko-en:안녕하세요>")
    pg.select_option("#omt-tab-from", "Chinese (Simplified)"); pg.select_option("#omt-tab-to", "English")
    pg.fill("#omt-tab-in", "你好")
    check(f"Han-only text keeps the chosen Chinese (no flip back to Japanese) {bar(pg)}", bar(pg) == ("Chinese (Simplified)", "English"))
    out = run(pg, "你好", "zh-en")
    check(f"zh→en {out!r}", out == "<zh-en:你好>")
    pg.fill("#omt-tab-in", "こんにちは")
    check(f"typing kana flips to Japanese {bar(pg)}", bar(pg)[0] == "Japanese")
    pg.fill("#omt-tab-in", "Hello")
    check(f"typing English flips From to English and To is re-chosen {bar(pg)}", bar(pg)[0] == "English" and bar(pg)[1] in ("Japanese", "Chinese (Simplified)", "Chinese (Traditional)"))

    # ---- 5) 入れ替え ----
    pg.fill("#omt-tab-in", ""); pg.select_option("#omt-tab-from", "Korean"); pg.select_option("#omt-tab-to", "English")
    pg.click("#omt-tab-swap")
    check(f"swap of Korean → English cannot be English → Korean (no model): lands on a valid pair {bar(pg)}", bar(pg)[0] == "English" and bar(pg)[1] == "Japanese")
    pg.select_option("#omt-tab-from", "Japanese"); pg.select_option("#omt-tab-to", "Chinese (Simplified)"); pg.click("#omt-tab-swap")
    check(f"swap of Japanese → Chinese works both ways {bar(pg)}", bar(pg) == ("Chinese (Simplified)", "Japanese"))
    get_model(pg, "en-ja")
    out = run(pg, "你好", "en-jap")
    check(f"zh→ja goes zh-en then en-ja {out!r}", out == "<en-jap:<zh-en:你好>>")

    # ---- 6) 翻訳メモリーとの組み合わせ（経由でも、覚えた文は先に使う） ----
    pg.evaluate("tmAdd('你好。', 'こんにちは。', 'Japanese', false)")
    pg.select_option("#omt-tab-from", "Chinese (Simplified)"); pg.select_option("#omt-tab-to", "Japanese")
    out = run(pg, "你好。我很好。", "こんにちは。")
    check(f"a remembered sentence comes from the memory, the other one goes through English {out!r}", out.startswith("こんにちは。") and "<zh-en:我很好。>" in out and "メモリー＋" in pg.inner_text("#omt-tab-label"))

    # ---- 7) 設定: 5つの行。自動ダウンロードは日本語⇄英語だけ ----
    pg.evaluate("setHistFilter('settings')")
    check("settings have five rows, each with a state and a delete button after download", pg.locator(".omt-row").count() == 5 and pg.locator(".omt-run").count() == 5)
    c2 = new_ctx(br); a = c2.new_page(); a.on("pageerror", lambda e: errs.append(str(e)))
    a.goto(B + "/", wait_until="load"); a.wait_for_timeout(300)
    a.evaluate("switchTab('history'); setHistFilter('settings')"); a.wait_for_timeout(200)
    a.locator("#set-auto-model").check()
    a.wait_for_function("document.querySelectorAll('.omt-del:not(.hidden)').length === 2", timeout=15000); a.wait_for_timeout(1500)
    done = a.evaluate("Promise.all(OfflineMT.PAIRS.map(p => OfflineMT.isDownloaded(p)))")
    check(f"auto-download fetches only ja-en and en-ja {done}", done == [True, True, False, False, False])
    c2.close()

    # ---- 8) 通常の画面（圏外）: 韓国語を英語に ----
    c3 = new_ctx(br); m = c3.new_page(); m.on("pageerror", lambda e: errs.append(str(e)))
    m.goto(B + "/", wait_until="load"); m.wait_for_timeout(300)
    m.evaluate("Object.defineProperty(navigator, 'onLine', {get: () => false, configurable: true})")
    m.fill("#tab-text textarea", "안녕하세요"); m.click("#tab-text button[type=submit]")
    m.wait_for_function("!document.getElementById('local-msg').classList.contains('hidden')", timeout=5000)
    check("main screen offline, model missing: names the model to download", "韓国語 → 英語" in m.inner_text("#local-msg"))
    m.evaluate("Object.defineProperty(navigator, 'onLine', {get: () => true, configurable: true})")
    get_model(m, "ko-en"); m.evaluate("switchTab('text'); Object.defineProperty(navigator, 'onLine', {get: () => false, configurable: true})")
    m.fill("#tab-text textarea", "안녕하세요"); m.click("#tab-text button[type=submit]")
    m.wait_for_function("!document.getElementById('local-result').classList.contains('hidden')", timeout=8000)
    check(f"main screen offline: Korean → English on the device {m.inner_text('#local-out')!r}", m.inner_text("#local-out") == "<ko-en:안녕하세요>" and "端末内の AI" in m.inner_text("#local-via"))
    check("history records the detected source language", m.evaluate("loadHistory()[0].srcLang") == "Korean")
    c3.close()
    c4 = new_ctx(br, target="Korean"); k = c4.new_page(); k.on("pageerror", lambda e: errs.append(str(e)))
    k.goto(B + "/", wait_until="load"); k.wait_for_timeout(300)
    k.evaluate("Object.defineProperty(navigator, 'onLine', {get: () => false, configurable: true})")
    k.fill("#tab-text textarea", "こんにちは"); k.click("#tab-text button[type=submit]")
    k.wait_for_function("!document.getElementById('local-msg').classList.contains('hidden')", timeout=5000)
    check("target Korean offline: says the pair is not available (no model exists)", "組み合わせ" in k.inner_text("#local-msg") and not k.locator("#local-result").is_visible())
    c4.close()

    # ---- 9) 見た目（選ぶバー・5つの行）----
    for theme, w in (("dark", 390), ("light", 390), ("dark", 320), ("light", 320)):
        c5 = new_ctx(br, width=w, theme=theme); q = c5.new_page(); q.on("pageerror", lambda e: errs.append(str(e)))
        q.goto(B + "/offline", wait_until="load"); q.wait_for_timeout(300)
        q.select_option("#omt-tab-to", "Chinese (Traditional)"); q.fill("#omt-tab-in", "こんにちは"); q.wait_for_timeout(100)
        ow = q.evaluate("document.documentElement.scrollWidth <= innerWidth")
        small = q.evaluate("[...document.querySelectorAll('#omt-tab button, #omt-tab select')].filter(b => b.offsetParent).map(b => b.getBoundingClientRect().height).filter(h => h < 40).length")
        if w == 390: q.screenshot(path=f"/tmp/v1110_{theme}.png")
        q.evaluate("setHistFilter('settings')"); q.locator("#omt-card").scroll_into_view_if_needed(); q.wait_for_timeout(200)
        ow2 = q.evaluate("document.documentElement.scrollWidth <= innerWidth")
        check(f"{theme} {w}px: no overflow in the tab ({ow}) or the settings ({ow2}); selects and buttons tall enough ({small} too small)", ow and ow2 and small == 0)
        c5.close()
    br.close()
w = open(os.path.join(ROOT, "static", "js", "offline_mt_worker.js"), encoding="utf-8").read()
check("the worker keeps one model at a time (memory) and takes the language marker", "releaseOthers" in w and "dispose" in w and "pre + s.trim()" in w)
check(f"no page errors {errs}", not errs)
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
