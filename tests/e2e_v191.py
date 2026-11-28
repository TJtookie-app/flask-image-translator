"""v1.9.1（オフライン画面のテキスト翻訳）のブラウザ確認。翻訳エンジンとモデルは本物を使わず、同じ形の模擬で、
/offline で「モデル未取得の案内→設定でダウンロード→自動で方向を選んで翻訳→履歴→圏外→失敗」と、見た目を確かめる。
使い方: python tests/e2e_v191.py"""
import os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import rates
from werkzeug.serving import make_server
from app import app

rates._http_get = lambda url: {"result": "success", "time_last_update_unix": 1794900000, "base_code": "USD", "rates": {"USD": 1, "JPY": 154.3}}
srv = make_server("127.0.0.1", 5107, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5107"
LIB = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.5.2"
CORS = {"Access-Control-Allow-Origin": "*"}
FAKE = """
export const env = { allowLocalModels: true, useBrowserCache: false, allowRemoteModels: true, backends: { onnx: { wasm: {} } } };
export async function pipeline(task, model, opts) {
  const c = await caches.open('transformers-cache');
  for (const f of ['onnx/encoder_model_quantized.onnx', 'onnx/decoder_model_merged_quantized.onnx', 'tokenizer.json']) {
    const name = f.split('/').pop();
    opts.progress_callback({ status: 'progress', file: name, loaded: 100, total: 100 });
    await c.put('https://huggingface.co/' + model + '/resolve/main/' + f, new Response('x'));
  }
  const remote = env.allowRemoteModels;
  return async (text) => { if (text.includes('BOOM')) throw new Error('boom'); return [{ translation_text: '[' + model.split('/')[1] + (remote ? '' : ' offline') + '] ' + text }]; };
}
"""
fails, errs = [], []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

from playwright.sync_api import sync_playwright
def new_ctx(br, width=390, theme=None):
    ctx = br.new_context(viewport={"width": width, "height": 900}, service_workers="block")
    def h(r):
        u = r.request.url
        if u.startswith(LIB): r.fulfill(status=200, body=FAKE, headers=CORS, content_type="application/javascript")
        elif u.startswith(B) or u.startswith("data:") or u.startswith("blob:"): r.continue_()
        else: r.abort()
    ctx.route("**/*", h)
    ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
    if theme: ctx.add_init_script("localStorage.setItem('tl_settings_v1', %r)" % ('{"theme":"%s"}' % theme))
    return ctx
def download(pg, pair):
    pg.evaluate("setHistFilter('settings')"); pg.wait_for_timeout(200)
    pg.locator(f'.omt-row[data-pair="{pair}"] .omt-get').click()
    pg.wait_for_function(f"document.querySelector('.omt-row[data-pair=\"{pair}\"] .omt-del:not(.hidden)')", timeout=10000)

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = new_ctx(br); ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=B)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    pg.goto(B + "/offline", wait_until="load"); pg.wait_for_timeout(500)

    # ---- 1) 最初: タブがあり、モデルが無いので案内が出る ----
    check("the text translation tab is on the /offline page, above the history/settings", pg.locator("#omt-tab").is_visible() and pg.evaluate("document.getElementById('omt-tab').compareDocumentPosition(document.getElementById('page-title')) & 4") > 0)
    check("title says 'テキスト'", "テキスト" in pg.inner_text("#omt-tab") or pg.locator(".pt-text", has_text="テキスト").first.is_visible())
    pg.fill("#omt-tab-in", "こんにちは")
    check("no model yet: guidance + open-settings button; run is usable (the memory can still answer)", pg.locator("#omt-tab-need").is_visible() and pg.locator("#omt-tab-run").is_enabled())
    pg.click("#omt-tab-run"); pg.wait_for_function("!document.getElementById('omt-tab-err').classList.contains('hidden')", timeout=5000)
    check("no model and nothing in the memory: says the model is missing", "モデル" in pg.inner_text("#omt-tab-err") and not pg.locator("#omt-tab-result").is_visible())

    # ---- 2) 案内のボタンで設定を開き、ダウンロードする → 戻ると使える ----
    pg.click("#omt-tab-open"); pg.wait_for_timeout(300)
    check("the guidance button opens the settings with the download card", pg.locator("#omt-card").is_visible())
    pg.locator('.omt-row[data-pair="ja-en"] .omt-get').click()
    pg.wait_for_function("document.querySelector('.omt-row[data-pair=\"ja-en\"] .omt-del:not(.hidden)')", timeout=10000)
    pg.wait_for_function("!document.getElementById('omt-tab-need').offsetParent", timeout=5000)
    check("after the download the guidance goes away and run is enabled (no reload)", not pg.locator("#omt-tab-need").is_visible() and pg.locator("#omt-tab-run").is_enabled())

    # ---- 3) 自動: 日本語 → 英語 ----
    pg.fill("#omt-tab-in", "こんにちは。元気ですか？"); pg.click("#omt-tab-run")
    pg.wait_for_function("document.getElementById('omt-tab-out').textContent.includes('opus-mt-ja-en')", timeout=10000)
    out = pg.inner_text("#omt-tab-out")
    check(f"auto picks ja→en for Japanese text {out!r}", out == "[opus-mt-ja-en] こんにちは。 [opus-mt-ja-en] 元気ですか？" and "日本語 → 英語" in pg.inner_text("#omt-tab-label"))
    hist = pg.evaluate("loadHistory()[0]")
    check(f"saved to the history {hist}", hist["mode"] == "text" and hist["src"] == "こんにちは。元気ですか？" and hist["srcLang"] == "Japanese" and hist["tgt"] == "English" and hist["out"] == out)
    pg.evaluate("setHistFilter('all')"); pg.wait_for_timeout(200)
    check("the history list shows it", "元気ですか" in pg.inner_text("#history-section") if pg.locator("#history-section").count() else "元気ですか" in pg.inner_text("body"))

    # ---- 4) 自動: 英語 → 日本語は、モデルが無いので案内に戻る。手動で方向を選べる ----
    pg.fill("#omt-tab-in", "Where is the station?")
    check("English text with auto: the en→ja model is missing → guidance shown", pg.locator("#omt-tab-need").is_visible())
    pg.click('#omt-tab-dirs [data-dir="ja-en"]')
    check("manual direction ja→en overrides auto: runnable, pressed state follows", pg.locator("#omt-tab-run").is_enabled() and pg.get_attribute('#omt-tab-dirs [data-dir="ja-en"]', "aria-pressed") == "true" and pg.get_attribute('#omt-tab-dirs [data-dir="auto"]', "aria-pressed") == "false")
    pg.click("#omt-tab-run"); pg.wait_for_function("document.getElementById('omt-tab-out').textContent.includes('Where')", timeout=10000)
    check("translated with the chosen direction", pg.inner_text("#omt-tab-out").startswith("[opus-mt-ja-en]"))
    pg.click('#omt-tab-dirs [data-dir="auto"]')

    # ---- 5) コピー ----
    pg.click("#omt-tab-copy"); pg.wait_for_timeout(200)
    check("copy puts the result on the clipboard", pg.evaluate("navigator.clipboard.readText()") == pg.inner_text("#omt-tab-out"))

    # ---- 6) 圏外 ----
    pg.goto(B + "/offline", wait_until="load"); pg.wait_for_timeout(500)   # 開き直す（エンジンは、開き直した後の最初の読み込みで、圏外かどうかを見る）
    pg.evaluate("Object.defineProperty(navigator, 'onLine', {get: () => false})")
    pg.fill("#omt-tab-in", "おはよう"); pg.click("#omt-tab-run")
    pg.wait_for_function("document.getElementById('omt-tab-out').textContent.includes('offline')", timeout=10000)
    check("offline: runs without the network", pg.inner_text("#omt-tab-out") == "[opus-mt-ja-en offline] おはよう")

    # ---- 7) 失敗 ----
    pg.fill("#omt-tab-in", "BOOM です"); pg.click("#omt-tab-run")
    pg.wait_for_function("!document.getElementById('omt-tab-err').classList.contains('hidden')", timeout=10000)
    check("failure: error line shown, result hidden, run usable again", not pg.locator("#omt-tab-result").is_visible() and pg.locator("#omt-tab-run").is_enabled())
    pg.fill("#omt-tab-in", "もう一度"); pg.click("#omt-tab-run")
    pg.wait_for_function("document.getElementById('omt-tab-out').textContent.includes('もう一度')", timeout=10000)
    check("the error line goes away after a success", not pg.locator("#omt-tab-err").is_visible())

    # ---- 8) 削除すると案内に戻る ----
    pg.evaluate("setHistFilter('settings')"); pg.wait_for_timeout(200)
    pg.locator('.omt-row[data-pair="ja-en"] .omt-del').click()
    pg.wait_for_function("document.querySelector('.omt-row[data-pair=\"ja-en\"] .omt-get:not(.hidden)')", timeout=5000)
    pg.wait_for_timeout(200)
    check("after deleting the model the tab asks for the download again", pg.locator("#omt-tab-need").is_visible())

    # ---- 9) 見た目 ----
    for theme, w in (("dark", 390), ("light", 390), ("dark", 320), ("light", 320)):
        c2 = new_ctx(br, width=w, theme=theme); q = c2.new_page(); q.on("pageerror", lambda e: errs.append(str(e)))
        q.goto(B + "/offline", wait_until="load"); q.wait_for_timeout(300)
        q.fill("#omt-tab-in", "こんにちは"); q.wait_for_timeout(100)
        ok_w = q.evaluate("document.documentElement.scrollWidth <= innerWidth")
        small = q.evaluate("[...document.querySelectorAll('#omt-tab button')].filter(b => b.offsetParent).map(b => b.getBoundingClientRect().height).filter(h => h < 40).length")
        low = q.evaluate("""(() => { const t = document.querySelector('#omt-tab .text-slate-400'); const c = getComputedStyle(t).color.match(/\\d+/g).map(Number);
            const bg = getComputedStyle(document.body).backgroundColor.match(/\\d+/g).map(Number);
            const L = (a) => a.slice(0,3).map(v => { v/=255; return v<=.03928 ? v/12.92 : Math.pow((v+.055)/1.055, 2.4) }).reduce((s,v,i) => s + v*[.2126,.7152,.0722][i], 0);
            const [a,b] = [L(c)+.05, L(bg)+.05]; return Math.max(a,b)/Math.min(a,b); })()""")
        check(f"{theme} {w}px: no overflow, buttons tall enough, hint readable (contrast {low:.1f})", ok_w and small == 0 and low >= 4.5)
        if w == 390: q.screenshot(path=f"/tmp/omt_tab_{theme}.png")
        c2.close()

    # ---- 10) 通常の画面には出ない / Worker が無い端末 ----
    c3 = new_ctx(br); q = c3.new_page(); q.on("pageerror", lambda e: errs.append(str(e))); q.goto(B + "/", wait_until="load")
    check("the normal page does not have the offline tab", q.locator("#omt-tab").count() == 0)
    c3.close()
    c4 = new_ctx(br); c4.add_init_script("delete window.Worker")
    q = c4.new_page(); q.on("pageerror", lambda e: errs.append(str(e))); q.goto(B + "/offline", wait_until="load"); q.wait_for_timeout(300)
    q.fill("#omt-tab-in", "こんにちは")
    check("no Worker: guidance shown (no crash)", q.locator("#omt-tab-need").is_visible())
    c4.close()
    br.close()
check(f"no page errors {errs}", not errs)
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
