"""v1.10.0（翻訳メモリー・圏外の自動切り替え・自動ダウンロード）のブラウザ確認。翻訳エンジンとモデルは模擬。
使い方: python tests/e2e_v1100.py"""
import os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import rates
from werkzeug.serving import make_server
from app import app

rates._http_get = lambda url: {"result": "success", "time_last_update_unix": 1794900000, "base_code": "USD", "rates": {"USD": 1, "JPY": 154.3}}
srv = make_server("127.0.0.1", 5108, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5108"
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
  return async (text) => [{ translation_text: '<' + model.split('/')[1].replace('opus-mt-', '') + ':' + text + '>' }];
}
"""
fails, errs = [], []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

from playwright.sync_api import sync_playwright
posts = []
def new_ctx(br, width=390, theme=None, cellular=False, init=None):
    ctx = br.new_context(viewport={"width": width, "height": 900}, service_workers="block")
    def h(r):
        u = r.request.url
        if u.startswith(LIB): r.fulfill(status=200, body=FAKE, headers=CORS, content_type="application/javascript")
        elif u.startswith(B) or u.startswith("data:") or u.startswith("blob:"):
            if r.request.method == "POST" and u.rstrip("/") == B: posts.append(u); r.fulfill(status=200, body="<html><body id='posted'>POSTED</body></html>", content_type="text/html")
            else: r.continue_()
        else: r.abort()
    ctx.route("**/*", h)
    ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
    p0 = ctx.new_page(); p0.goto(B + "/", wait_until="networkidle")   # 読み込み中の通信が終わってから（Cookie の書き換えが重ならないように）
       # 表示が日本語だと翻訳先も日本語から始まるので、英語にする（ブラウザ経由。Cookie が secure のため）
    p0.evaluate("fetch('/set-language', {method: 'POST', body: new URLSearchParams({target_lang: 'English', lang_type: 'target'})}).then(r => r.status)"); p0.close()
    if theme: ctx.add_init_script("localStorage.setItem('tl_settings_v1', %r)" % ('{"theme":"%s"}' % theme))
    if cellular: ctx.add_init_script("Object.defineProperty(navigator, 'connection', {get: () => ({type: 'cellular', saveData: false})})")
    if init: ctx.add_init_script(init)
    return ctx
def setting(on, key): return f"localStorage.setItem('tl_settings_v1', JSON.stringify(Object.assign(loadSettings(), {{{key}: {on}}})))"
def has_model(pg, pair): return pg.evaluate(f"OfflineMT.isDownloaded('{pair}')")
def download(pg, pair):
    pg.evaluate("switchTab('history'); setHistFilter('settings')"); pg.wait_for_timeout(200)
    pg.locator(f'.omt-row[data-pair="{pair}"] .omt-get').click()
    pg.wait_for_function(f"document.querySelector('.omt-row[data-pair=\"{pair}\"] .omt-del:not(.hidden)')", timeout=10000)
    pg.evaluate("switchTab('text')")

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = new_ctx(br)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/", wait_until="load"); pg.wait_for_timeout(500)
    print("TARGET_LANG =", pg.evaluate("TARGET_LANG"))
    check("default target is English (the tests below depend on it)", pg.evaluate("TARGET_LANG") == "English")

    # ---- 1) 翻訳メモリーの部品 ----
    ev = pg.evaluate
    ev("tmClear()")
    ev("tmAdd('駅はどこですか？', 'Where is the station?', 'English', false)")
    check("exact (also after width/space/case normalization)", ev("tmFind('駅はどこですか？', 'English').kind") == "exact" and ev("tmFind(' ＡＢＣ ', 'English')") is None and ev("(tmAdd('Hello  World','こんにちは世界','Japanese',false), tmFind('hello world','Japanese').out)") == "こんにちは世界")
    check("not used for another target language", ev("tmFind('駅はどこですか？', 'Korean')") is None)
    check("similar: almost the same sentence is found, with the original shown", ev("tmFind('駅は、どこですか', 'English').kind") == "similar" and ev("tmFind('駅は、どこですか', 'English').src") == "駅はどこですか？")
    ev("tmAdd('3番線はどこですか？', 'Where is platform 3?', 'English', false)")
    check("similar is never used when the numbers differ", ev("tmFind('5番線はどこですか？', 'English')") is None)
    check("short or different sentences do not match", ev("tmFind('駅', 'English')") is None and ev("tmFind('トイレはどこですか？', 'English')") is None)
    ev("tmAdd('こんにちは', 'Hello (edited)', 'English', true)"); ev("tmAdd('こんにちは', 'Hello (auto)', 'English', false)")
    check("an edited translation is not overwritten by a later automatic one, and wins", ev("tmFind('こんにちは', 'English').out") == "Hello (edited)")
    ev("localStorage.setItem('tl_settings_v1', JSON.stringify({tm: false}))")
    n = ev("tmCount()"); ev("tmAdd('新しい文です', 'A new sentence', 'English', false)")
    check("with the memory switched off nothing is added or found", ev("tmCount()") == n and ev("tmFind('駅はどこですか？', 'English')") is None)
    ev("localStorage.removeItem('tl_settings_v1')")
    ev("tmClear(); for (let i = 0; i < 1700; i++) tmAdd('文章番号 ' + i + ' です', 'Sentence ' + i, 'English', false)")
    check("capped at 1500 and keeps the newest", ev("tmCount()") == 1500 and ev("tmFind('文章番号 1699 です', 'English')") is not None and ev("tmFind('文章番号 0 です', 'English')") is None)
    ev("tmClear()")

    # ---- 2) 覚えるタイミング ----
    ev("addHistory({mode:'text', src:'ありがとう', out:'Thank you', srcLang:'Japanese', tgt:'English', tcode:'en-US', pron:''})")
    ev("addHistory({mode:'text', src:'さようなら', out:'Goodbye (basic)', srcLang:'Japanese', tgt:'English', tcode:'en-US', pron:'', offline:true})")
    ev("addHistory({mode:'image', src:'メニュー', out:'Menu', srcLang:'Japanese', tgt:'English', tcode:'en-US', pron:''})")
    check("online text results are remembered; on-device results and images are not", ev("tmFind('ありがとう','English').out") == "Thank you" and ev("tmFind('さようなら','English')") is None and ev("tmFind('メニュー','English')") is None)
    ev("learnCorrection('おはよう', 'Good morning!', 'English')")
    check("a correction made by the user is remembered with priority", ev("tmFind('おはよう','English').out") == "Good morning!" and ev("tmLoad().find(x => x.r === 'おはよう').u") == 1)

    # ---- 3) 圏外の通常画面: メモリー → 端末内の AI ----
    ev("tmClear()"); ev("tmAdd('駅はどこですか？', 'Where is the station?', 'English', false)")
    ev("Object.defineProperty(navigator, 'onLine', {get: () => false, configurable: true})")
    ta = pg.locator("#tab-text textarea"); run = pg.locator("#tab-text button[type=submit]")
    posts.clear()
    ta.fill("駅はどこですか？"); run.click(); pg.wait_for_function("!document.getElementById('local-result').classList.contains('hidden')", timeout=5000)
    check(f"offline + in the memory: answered from the memory, nothing sent to the server {pg.inner_text('#local-out')!r}", pg.inner_text("#local-out") == "Where is the station?" and "メモリー" in pg.inner_text("#local-via") and not posts)
    ta.fill("お水をください。"); run.click(); pg.wait_for_function("!document.getElementById('local-msg').classList.contains('hidden')", timeout=5000)
    check("offline + not in the memory + no model: explains that the model is missing", "モデル" in pg.inner_text("#local-msg") and not pg.locator("#local-result").is_visible())
    pg.evaluate("Object.defineProperty(navigator, 'onLine', {get: () => true, configurable: true})")
    download(pg, "ja-en")
    pg.evaluate("Object.defineProperty(navigator, 'onLine', {get: () => false, configurable: true})")
    ta.fill("お水をください。"); run.click(); pg.wait_for_function("document.getElementById('local-out').textContent.includes('<ja-en:')", timeout=8000)
    check(f"offline + model: translated on the device {pg.inner_text('#local-out')!r}", pg.inner_text("#local-out") == "<ja-en:お水をください。>" and "端末内の AI" in pg.inner_text("#local-via") and not posts)
    ta.fill("駅はどこですか？お水をください。"); run.click()
    pg.wait_for_function("document.getElementById('local-out').textContent.includes('Where')", timeout=8000)
    check(f"mixed: a remembered sentence from the memory, the rest by the model {pg.inner_text('#local-out')!r}", pg.inner_text("#local-out") == "Where is the station? <ja-en:お水をください。>" and "メモリー＋" in pg.inner_text("#local-via"))
    check("the on-device translation is in the history, marked offline, and not copied into the memory", ev("loadHistory()[0].offline") is True and ev("tmFind('お水をください。','English')") is None)
    check("the result card keeps speak and copy buttons", pg.locator("#local-result [data-local=speak]").is_visible() and pg.locator("#local-result [data-local=copy]").is_visible())
    check("only Japanese ⇄ English works on the device (other pairs report it)", ev("OfflineText.translate('こんにちは', 'Korean')") == {"error": "nopair"})
    ta.fill("Hello there"); run.click(); pg.wait_for_function("!document.getElementById('local-msg').classList.contains('hidden')", timeout=5000)
    check("English text with an English target: nothing to do, explained (no crash)", "日本語と英語" in pg.inner_text("#local-msg"))

    # ---- 4) オンラインでは、今まで通りサーバーに送る ----
    ev("Object.defineProperty(navigator, 'onLine', {get: () => true, configurable: true})")
    posts.clear(); ta.fill("駅はどこですか？"); run.click(); pg.wait_for_timeout(600)
    check("online: the form is sent to the server as before", len(posts) == 1)

    # ---- 5) 設定: スイッチ・件数・消去 ----
    q = ctx.new_page(); q.on("pageerror", lambda e: errs.append(str(e))); q.on("dialog", lambda d: d.accept())
    q.goto(B + "/", wait_until="load"); q.wait_for_timeout(300)
    q.evaluate("tmClear(); tmAdd('a文です','A','English',false); tmAdd('b文です','B','English',false); switchTab('history'); setHistFilter('settings')"); q.wait_for_timeout(300)
    print(q.locator("#set-tm").is_checked(), q.locator("#set-auto-model").is_checked(), repr(q.inner_text("#tm-count")), q.evaluate("tmCount()"), q.evaluate("localStorage.getItem('tl_tm_v1')"))
    check("settings show both switches (memory ON, auto-download OFF) and the count", q.locator("#set-tm").is_checked() and not q.locator("#set-auto-model").is_checked() and "2件" in q.inner_text("#tm-count"))
    q.locator("#set-tm").uncheck(); check("the memory switch is saved", q.evaluate("loadSettings().tm") is False)
    q.locator("#set-tm").check()
    q.click("#tm-clear"); q.wait_for_timeout(200)
    check("clear removes everything and updates the count", q.evaluate("tmCount()") == 0 and "0件" in q.inner_text("#tm-count"))
    q.close()

    # ---- 6) 自動ダウンロード ----
    c2 = new_ctx(br); a = c2.new_page(); a.on("pageerror", lambda e: errs.append(str(e)))
    a.goto(B + "/", wait_until="load"); a.wait_for_timeout(300)
    a.evaluate("switchTab('history'); setHistFilter('settings')"); a.wait_for_timeout(200)
    check("auto-download is off by default: nothing is downloaded after the page has been open for a while", not has_model(a, "ja-en"))
    a.locator("#set-auto-model").check()
    a.wait_for_function("document.querySelectorAll('.omt-del:not(.hidden)').length === 2", timeout=15000)
    check("switching it ON downloads both directions, one after another, with no button pressed", has_model(a, "ja-en") and has_model(a, "en-ja"))
    c2.close()
    c3 = new_ctx(br, init=f"try {{ localStorage.setItem('tl_settings_v1', JSON.stringify({{autoModel: true}})) }} catch (e) {{}}"); b = c3.new_page(); b.on("pageerror", lambda e: errs.append(str(e)))
    b.goto(B + "/", wait_until="load")
    b.wait_for_function("document.querySelectorAll('.omt-del:not(.hidden)').length === 2", timeout=20000)
    check("with it ON, opening the app downloads the missing models by itself", True)
    c3.close()
    c4 = new_ctx(br, cellular=True); d = c4.new_page(); d.on("pageerror", lambda e: errs.append(str(e)))
    d.goto(B + "/", wait_until="load"); d.evaluate(setting("true", "autoModel")); d.evaluate("document.dispatchEvent(new Event('omt-auto-on'))"); d.wait_for_timeout(5000)
    check("on a cellular connection (where the device tells us) it does not start", not has_model(d, "ja-en"))
    c4.close()
    c5 = new_ctx(br); f = c5.new_page(); f.on("pageerror", lambda e: errs.append(str(e)))
    f.goto(B + "/", wait_until="load"); f.evaluate(setting("true", "autoModel")); f.evaluate("Object.defineProperty(navigator, 'onLine', {get: () => false, configurable: true})"); f.evaluate("document.dispatchEvent(new Event('omt-auto-on'))"); f.wait_for_timeout(1500)
    check("offline: it does not start", not has_model(f, "ja-en"))
    c5.close()

    # ---- 7) 見た目（結果カードと設定）----
    for theme, w in (("dark", 390), ("light", 390), ("dark", 320), ("light", 320)):
        c6 = new_ctx(br, width=w, theme=theme); s = c6.new_page(); s.on("pageerror", lambda e: errs.append(str(e)))
        s.goto(B + "/", wait_until="load"); s.wait_for_timeout(300)
        s.evaluate("tmAdd('駅はどこですか？', 'Where is the station? ' + 'x'.repeat(60), 'English', false); Object.defineProperty(navigator, 'onLine', {get: () => false, configurable: true})")
        s.fill("#tab-text textarea", "駅はどこですか？"); s.click("#tab-text button[type=submit]"); s.wait_for_function("!document.getElementById('local-result').classList.contains('hidden')", timeout=5000)
        ow = s.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if w == 390: s.screenshot(path=f"/tmp/local_{theme}.png")
        s.evaluate("switchTab('history'); setHistFilter('settings')"); s.locator("#set-tm").scroll_into_view_if_needed(); s.wait_for_timeout(200)
        ow2 = s.evaluate("document.documentElement.scrollWidth <= innerWidth")
        small = s.evaluate("[...document.querySelectorAll('#tm-clear')].filter(b => b.offsetParent).map(b => b.getBoundingClientRect().height).filter(h => h < 40).length")
        check(f"{theme} {w}px: no overflow on the result card ({ow}) or the settings ({ow2}), clear button tall enough ({small} too small)", ow and ow2 and small == 0)
        c6.close()
    br.close()
check(f"no page errors {errs}", not errs)
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
