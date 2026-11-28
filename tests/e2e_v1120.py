"""v1.12.0（オフラインで、写真の文字を読み取って訳す・試作）のブラウザ確認。文字認識とモデルは模擬。翻訳エンジンとモデルは模擬
（出力に、入力と、使ったモデルの名前が入るので、手順と、中国語の文字の指定が正しいかを確かめられる）。使い方: python tests/e2e_v1120.py"""
import os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import rates
from werkzeug.serving import make_server
from app import app

rates._http_get = lambda url: {"result": "success", "time_last_update_unix": 1794900000, "base_code": "USD", "rates": {"USD": 1, "JPY": 154.3}}
srv = make_server("127.0.0.1", 5112, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5112"
LIB = "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.5.2"
OCR_LIB = "https://cdn.jsdelivr.net/npm/tesseract.js@6.0.1/dist/tesseract.min.js"
OCR_DATA = "https://cdn.jsdelivr.net/npm/@tesseract.js-data/"
FAKE_OCR = """
window.__ocr = { urls: [], size: null, text: '駅 は\\nど こ で す か ？', fail: false };
window.Tesseract = { createWorker: async (lang, oem, opts) => {
  if (window.__ocr.fail) throw new Error('boom');
  const r = await fetch(opts.langPath + '/' + lang + '.traineddata.gz'); await r.arrayBuffer(); window.__ocr.urls.push(r.url);
  opts.logger({ status: 'loading language traineddata', progress: 1 });
  return { recognize: async (c) => { window.__ocr.size = c.width + 'x' + c.height + ':' + lang; return { data: { text: window.__ocr.text } }; }, terminate: async () => {} };
} };
"""
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
        elif u == OCR_LIB: r.fulfill(status=200, body=FAKE_OCR, headers=CORS, content_type="application/javascript")
        elif u.startswith(OCR_DATA): r.fulfill(status=200, body="x", headers=CORS, content_type="application/gzip")
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
    if pg.locator(f'.omt-row[data-pair="{pair}"] .omt-del:not(.hidden)').count(): return
    if not pg.locator(f'.omt-row[data-pair="{pair}"]').is_visible():       # v1.11.1: 言語パック。追加した言語の、すべての方向が入る
        pk = pair.replace("en", "").replace("-", ""); pg.select_option("#omt-add-sel", pk); pg.click("#omt-add-btn")
    else: pg.locator(f'.omt-row[data-pair="{pair}"] .omt-get').click()
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
    flags = lambda: pg.evaluate("Object.keys(JSON.parse(localStorage.getItem('tl_ocr_v1') || '{}')).sort()")
    state = lambda pk: pg.inner_text(f'.ocr-row[data-ocr-pack="{pk}"] .ocr-state')
    def photo(w=3600, h=1800):
        pg.evaluate("""([w, h]) => new Promise((ok) => { const c = document.createElement('canvas'); c.width = w; c.height = h; c.getContext('2d').fillRect(0, 0, 50, 50);
            c.toBlob((b) => { const dt = new DataTransfer(); dt.items.add(new File([b], 'a.png', { type: 'image/png' })); const i = document.getElementById('omt-photo'); i.files = dt.files; i.dispatchEvent(new Event('change')); ok(); }); })""", [w, h])
    # ---- 1) 設定: 日本語のパックに、写真の文字認識の行。入れる ----
    pg.evaluate("setHistFilter('settings')"); pg.wait_for_timeout(300)
    check(f"the Japanese pack has a photo-recognition row, not downloaded yet {state('ja')!r}", "未ダウンロード" in state("ja") and flags() == [])
    pg.locator('.ocr-row[data-ocr-pack="ja"] .ocr-get').click()
    pg.wait_for_function("document.querySelector('.ocr-row[data-ocr-pack=\"ja\"] .ocr-del:not(.hidden)')", timeout=10000)
    urls = pg.evaluate("window.__ocr.urls")
    check(f"jpn + eng downloaded from the pinned data packages {urls}", flags() == ["eng", "jpn"] and any("@tesseract.js-data/jpn/4.0.0_best_int/jpn.traineddata.gz" in u for u in urls) and any("/eng/4.0.0_best_int/eng.traineddata.gz" in u for u in urls))
    check("the state says downloaded", "ダウンロード済み" in state("ja"))
    pg.locator('.omt-row[data-pair="ja-en"] .omt-get').click()
    pg.wait_for_function("document.querySelector('.omt-row[data-pair=\"ja-en\"] .omt-del:not(.hidden)')", timeout=10000)
    # ---- 2) 写真 → 読み取り（空白を除いて、改行は残す）→ そのまま翻訳。大きい写真は縮める ----
    pg.select_option("#omt-tab-from", "Japanese"); pg.select_option("#omt-tab-to", "English")
    photo()
    pg.wait_for_function("document.getElementById('omt-tab-out').textContent.includes('ja-en')", timeout=10000)
    check(f"text read, cleaned and put in the box {pg.input_value('#omt-tab-in')!r}", pg.input_value("#omt-tab-in") == "駅は\nどこですか？")
    out = pg.inner_text("#omt-tab-out")
    check(f"and translated right away {out!r}", out == "<ja-en:駅は> <ja-en:どこですか？>".replace("> <", ">\n<") or "ja-en" in out)
    check(f"the photo was shrunk to 1800 on the long side and read as jpn {pg.evaluate('window.__ocr.size')}", pg.evaluate("window.__ocr.size") == "1800x900:jpn")
    check("the progress message is cleared", not pg.is_visible("#omt-photo-msg"))
    # ---- 3) 認識データが無い言語 ----
    pg.select_option("#omt-tab-from", "Korean"); pg.evaluate("window.__ocr.size = null"); photo(200, 100)
    pg.wait_for_function("!document.getElementById('omt-photo-msg').classList.contains('hidden')", timeout=5000)
    msg = pg.inner_text("#omt-photo-msg")
    check(f"no data for Korean: says which language and does not read {msg!r}", "한국어" in msg and pg.evaluate("window.__ocr.size") is None)
    # ---- 4) 文字が読めなかったとき ----
    pg.select_option("#omt-tab-from", "Japanese"); pg.evaluate("window.__ocr.text = ''"); photo(200, 100)
    pg.wait_for_function("document.getElementById('omt-photo-msg').textContent.includes('読み取れませんでした')", timeout=5000)
    check("empty result: a how-to-shoot hint", "明るい" in pg.inner_text("#omt-photo-msg"))
    # ---- 5) エラー: 理由を添えて出す ----
    pg.evaluate("window.__ocr.fail = true"); photo(200, 100)
    pg.wait_for_function("document.getElementById('omt-photo-msg').textContent.includes('boom')", timeout=5000)
    check("engine error is shown with its reason", "うまくいきませんでした" in pg.inner_text("#omt-photo-msg"))
    pg.evaluate("window.__ocr.fail = false; window.__ocr.text = 'x'")
    # ---- 6) 言語パックを追加すると、文字認識のデータも続けて入る。削除のとき、英語は他に残る間は消さない ----
    pg.evaluate("setHistFilter('settings')"); pg.wait_for_timeout(200)
    pg.select_option("#omt-add-sel", "es"); pg.click("#omt-add-btn")
    pg.wait_for_function("document.querySelector('.ocr-row[data-ocr-pack=\"es\"] .ocr-del:not(.hidden)')", timeout=20000)
    check(f"adding Spanish also downloads its photo data {flags()}", flags() == ["eng", "jpn", "spa"])
    pg.locator('.ocr-row[data-ocr-pack="ja"] .ocr-del').click(); pg.wait_for_timeout(300)
    check(f"deleting Japanese's keeps English (Spanish still needs it) {flags()}", flags() == ["eng", "spa"] and "未ダウンロード" in state("ja"))
    pg.locator('.ocr-row[data-ocr-pack="es"] .ocr-del').click(); pg.wait_for_timeout(300)
    check(f"deleting the last one removes English too {flags()}", flags() == [])
    # ---- 7) 通常の画面の設定にも、行がある ----
    pg2 = ctx.new_page(); pg2.on("pageerror", lambda e: errs.append(str(e)))
    pg2.goto(B + "/", wait_until="networkidle"); pg2.evaluate("if (document.getElementById('nav-history')) switchTab('history'); setHistFilter('settings')"); pg2.wait_for_timeout(400)
    check("the main page settings also show the photo row (and no photo button there)", pg2.locator(".ocr-row").count() == 9 and pg2.locator("#omt-photo").count() == 0)
    check(f"no page errors {errs}", not errs)
    br.close()
print("FAILS:", fails); print("ALL PASS" if not fails else "SOME FAILED"); sys.exit(1 if fails else 0)
