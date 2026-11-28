"""v1.9.0（オフライン翻訳の試作）のブラウザ確認。翻訳エンジンとモデルは本物を使わず、同じ形の模擬で、
ダウンロード→保存→翻訳→削除→圏外→エラー→非対応の動きと、画面の見た目を確かめる。使い方: python tests/e2e_v190.py
（本物のエンジンとモデルでの確認は、通信できる端末で、設定の「オフライン翻訳（試作）」から行う）"""
import os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import rates
from werkzeug.serving import make_server
from app import app

rates._http_get = lambda url: {"result": "success", "time_last_update_unix": 1794900000, "base_code": "USD", "rates": {"USD": 1, "JPY": 154.3}}
srv = make_server("127.0.0.1", 5106, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5106"
LIB = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.5.2"
CORS = {"Access-Control-Allow-Origin": "*"}
FAKE = """
export const env = { allowLocalModels: true, useBrowserCache: false, allowRemoteModels: true, backends: { onnx: { wasm: {} } } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export async function pipeline(task, model, opts) {
  const c = await caches.open('transformers-cache');
  for (const f of ['onnx/encoder_model_quantized.onnx', 'onnx/decoder_model_merged_quantized.onnx', 'tokenizer.json']) {
    const name = f.split('/').pop();
    opts.progress_callback({ status: 'progress', file: name, loaded: 40, total: 100 }); await sleep(120);
    opts.progress_callback({ status: 'progress', file: name, loaded: 100, total: 100 });
    await c.put('https://huggingface.co/' + model + '/resolve/main/' + f, new Response('x'));
  }
  const remote = env.allowRemoteModels;
  return async (text) => [{ translation_text: '[' + model.split('/')[1] + (remote ? '' : ' offline') + '] ' + text }];
}
"""
fails, errs = [], []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

from playwright.sync_api import sync_playwright
def open_settings(pg, path="/"):
    pg.goto(B + path, wait_until="load"); pg.wait_for_timeout(300)
    pg.evaluate("switchTab('history')"); pg.evaluate("setHistFilter('settings')"); pg.wait_for_timeout(300)
def new_ctx(br, lib="ok", width=390, theme=None):
    ctx = br.new_context(viewport={"width": width, "height": 900}, service_workers="block", accept_downloads=False)
    def h(r):
        u = r.request.url
        if u.startswith(LIB):
            if lib == "ok": r.fulfill(status=200, body=FAKE, headers=CORS, content_type="application/javascript")
            else: r.fulfill(status=404, body="nope", headers=CORS)
        elif u.startswith(B) or u.startswith("data:") or u.startswith("blob:"): r.continue_()
        else: r.abort()
    ctx.route("**/*", h)
    ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
    if theme: ctx.add_init_script("localStorage.setItem('tl_settings_v1', %r)" % ('{"theme":"%s"}' % theme))
    return ctx

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = new_ctx(br)
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda d: d.accept())
    open_settings(pg)
    row = lambda pair: pg.locator(f'.omt-row[data-pair="{pair}"]')

    # ---- 1) 最初の状態 ----
    check("card is in the settings view with both directions", pg.locator("#omt-card").is_visible() and pg.locator(".omt-row").count() == 2)
    check("both directions start as 'not downloaded' with a download button", all("未ダウンロード" in row(x).locator(".omt-state").inner_text() and row(x).locator(".omt-get").is_visible() and not row(x).locator(".omt-del").is_visible() for x in ("ja-en", "en-ja")))
    check("test box is hidden until something is downloaded", not pg.locator("#omt-test").is_visible())
    check("diagnostics show the environment", "Worker/WASM/caches: true/true/true" in pg.locator("#omt-diag").text_content())

    # ---- 2) ダウンロード（進み具合が出て、終わると使える） ----
    row("ja-en").locator(".omt-get").click(); pg.wait_for_timeout(150)
    check("while downloading: state + progress bar, no double start", "ダウンロード中" in row("ja-en").locator(".omt-state").inner_text() and row("ja-en").locator(".omt-bar").is_visible()
          and row("en-ja").locator(".omt-get").is_disabled())
    pg.wait_for_function("document.querySelector('.omt-row[data-pair=\"ja-en\"] .omt-del:not(.hidden)')", timeout=10000)
    check("after download: 'downloaded' + delete button, bar hidden", "ダウンロード済み" in row("ja-en").locator(".omt-state").inner_text() and row("ja-en").locator(".omt-del").is_visible() and not row("ja-en").locator(".omt-bar").is_visible())
    check("test box appears; only the downloaded direction can run", pg.locator("#omt-test").is_visible() and pg.locator('[data-omt-run="ja-en"]').is_enabled() and pg.locator('[data-omt-run="en-ja"]').is_disabled())
    check("diagnostics list the steps", all(s in pg.locator("#omt-diag").text_content() for s in ("翻訳エンジン: 読み込み完了", "モデルの準備完了", "ダウンロード完了: ja-en")))

    # ---- 3) 翻訳（文ごとに訳して、つなぐ） ----
    pg.fill("#omt-in", "こんにちは。元気ですか？\n駅はどこ？"); pg.click('[data-omt-run="ja-en"]')
    pg.wait_for_function("document.getElementById('omt-out').textContent.includes('opus-mt-ja-en')", timeout=10000)
    out = pg.inner_text("#omt-out")
    check(f"translates sentence by sentence, keeps line breaks {out!r}", out == "[opus-mt-ja-en] こんにちは。 [opus-mt-ja-en] 元気ですか？\n[opus-mt-ja-en] 駅はどこ？")

    # ---- 4) 開き直しても「ダウンロード済み」が残る ----
    open_settings(pg)
    pg.wait_for_function("document.querySelector('.omt-row[data-pair=\"ja-en\"] .omt-del:not(.hidden)')", timeout=5000)
    check("downloaded state survives a reload (from the device storage)", "ダウンロード済み" in row("ja-en").locator(".omt-state").inner_text() and row("en-ja").locator(".omt-get").is_visible())

    # ---- 5) 圏外（navigator.onLine=false）: 通信しない設定でモデルを読む ----
    pg.evaluate("Object.defineProperty(navigator, 'onLine', {get: () => false})")
    pg.fill("#omt-in", "こんにちは"); pg.click('[data-omt-run="ja-en"]')
    pg.wait_for_function("document.getElementById('omt-out').textContent.includes('opus-mt-ja-en')", timeout=10000)
    check(f"offline: the engine is told not to use the network {pg.inner_text('#omt-out')!r}", pg.inner_text("#omt-out") == "[opus-mt-ja-en offline] こんにちは")

    # ---- 6) 削除 ----
    row("ja-en").locator(".omt-del").click()
    pg.wait_for_function("document.querySelector('.omt-row[data-pair=\"ja-en\"] .omt-get:not(.hidden)')", timeout=5000)
    left = pg.evaluate("(async()=>{const c=await caches.open('transformers-cache');return (await c.keys()).length})()")
    check(f"delete: back to 'not downloaded', files removed from the device ({left} left)", left == 0 and not pg.locator("#omt-test").is_visible())

    # ---- 7) 見た目（ダーク・ライト、狭い画面）----
    for theme, w in (("dark", 390), ("light", 390), ("dark", 320), ("light", 320)):
        c2 = new_ctx(br, width=w, theme=theme); q = c2.new_page(); q.on("pageerror", lambda e: errs.append(str(e)))
        open_settings(q); q.locator("#omt-card").scroll_into_view_if_needed()
        q.locator('.omt-row[data-pair="ja-en"] .omt-get').click(); q.wait_for_function("document.querySelector('.omt-del:not(.hidden)')", timeout=10000)
        q.wait_for_timeout(200)
        ok_w = q.evaluate("document.documentElement.scrollWidth <= innerWidth")
        small = q.evaluate("[...document.querySelectorAll('#omt-card button')].filter(b => b.offsetParent).map(b => b.getBoundingClientRect().height).filter(h => h < 40).length")
        low = q.evaluate("""(() => { const t = document.querySelector('#omt-card .text-slate-400'); const c = getComputedStyle(t).color.match(/\\d+/g).map(Number);
            const bg = getComputedStyle(document.body).backgroundColor.match(/\\d+/g).map(Number);
            const L = (a) => a.slice(0,3).map(v => { v/=255; return v<=.03928 ? v/12.92 : Math.pow((v+.055)/1.055, 2.4) }).reduce((s,v,i) => s + v*[.2126,.7152,.0722][i], 0);
            const [a,b] = [L(c)+.05, L(bg)+.05]; return Math.max(a,b)/Math.min(a,b); })()""")
        check(f"{theme} {w}px: no horizontal overflow, buttons tall enough, note text readable (contrast {low:.1f})", ok_w and small == 0 and low >= 4.5)
        if w == 390: q.screenshot(path=f"/tmp/omt_{theme}.png", full_page=False)
        c2.close()

    # ---- 8) 圏外画面（/offline）にも、同じカードがある ----
    c3 = new_ctx(br); q = c3.new_page(); q.on("pageerror", lambda e: errs.append(str(e)))
    q.goto(B + "/offline", wait_until="load"); q.wait_for_timeout(400)
    q.evaluate("setHistFilter('settings')"); q.wait_for_timeout(200)
    check("the /offline page also has the card", q.locator("#omt-card").is_visible())
    c3.close()

    # ---- 9) エンジンが取れないとき: エラー表示と診断、状態は元のまま ----
    c4 = new_ctx(br, lib="bad"); q = c4.new_page(); q.on("pageerror", lambda e: errs.append(str(e)))
    open_settings(q); q.locator('.omt-row[data-pair="en-ja"] .omt-get').click()
    q.wait_for_function("!document.getElementById('omt-err').classList.contains('hidden')", timeout=10000)
    check("engine failure: error shown, diagnostics have the reason, still 'not downloaded'",
          "エラー" in q.text_content("#omt-diag") and "未ダウンロード" in q.locator('.omt-row[data-pair="en-ja"] .omt-state').inner_text() and q.locator('.omt-row[data-pair="en-ja"] .omt-get').is_enabled())
    c4.close()

    # ---- 10) Worker が使えない端末 ----
    c5 = new_ctx(br); c5.add_init_script("delete window.Worker")
    q = c5.new_page(); q.on("pageerror", lambda e: errs.append(str(e))); open_settings(q)
    check("no Worker: shows the 'not available' note and hides the buttons", q.locator("#omt-unsupported").is_visible() and not q.locator("#omt-rows").is_visible())
    c5.close()
    br.close()
check(f"no page errors {errs}", not errs)
print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
