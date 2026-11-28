"""v1.11.1（設定の「言語パック」方式: ダウンロード済みの言語だけを並べ、「言語を追加」から足す）のブラウザ確認。翻訳エンジンとモデルは模擬
（出力に、入力と、使ったモデルの名前が入るので、手順と、中国語の文字の指定が正しいかを確かめられる）。使い方: python tests/e2e_v1111.py"""
import os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import rates
from werkzeug.serving import make_server
from app import app

rates._http_get = lambda url: {"result": "success", "time_last_update_unix": 1794900000, "base_code": "USD", "rates": {"USD": 1, "JPY": 154.3}}
srv = make_server("127.0.0.1", 5110, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5110"
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
def new_ctx(br):
    ctx = br.new_context(viewport={"width": 390, "height": 900}, service_workers="block")
    def h(r):
        u = r.request.url
        if u.startswith(LIB): r.fulfill(status=200, body=FAKE, headers=CORS, content_type="application/javascript")
        elif u.startswith(B) or u.startswith("data:") or u.startswith("blob:"): r.continue_()
        else: r.abort()
    ctx.route("**/*", h)
    ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
    return ctx
def settings(pg):
    pg.goto(B + "/", wait_until="networkidle")
    pg.evaluate("if (document.getElementById('nav-history')) switchTab('history'); setHistFilter('settings')"); pg.wait_for_timeout(500)
vis = lambda pg, sel: pg.locator(sel).is_visible()
packs = lambda pg: pg.evaluate("Array.from(document.querySelectorAll('.omt-pack')).filter(e => e.offsetParent).map(e => e.dataset.pack)")
opts = lambda pg: pg.evaluate("Array.from(document.querySelectorAll('#omt-add-sel option')).filter(o => o.value && !o.hidden && !o.disabled).map(o => o.value)")

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = new_ctx(br); pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    settings(pg)
    # ---- 1) 最初: 日本語⇄英語だけが並び、ほかは「言語を追加」の中 ----
    check(f"only the Japanese pack is listed at first {packs(pg)}", packs(pg) == ["ja"])
    check("the add box is shown, with zh and ko to choose from", vis(pg, "#omt-add") and opts(pg) == ["zh", "ko"])
    check("the add button waits for a choice", pg.locator("#omt-add-btn").is_disabled())
    check("the test box is hidden while nothing is downloaded", not vis(pg, "#omt-test"))
    # ---- 2) 中国語を追加 → 両方向が順に入り、並ぶ ----
    pg.select_option("#omt-add-sel", "zh")
    check("choosing a language enables the button", not pg.locator("#omt-add-btn").is_disabled())
    pg.click("#omt-add-btn")
    pg.wait_for_function("document.querySelectorAll('.omt-row[data-pair=\"zh-en\"] .omt-del:not(.hidden), .omt-row[data-pair=\"en-zh\"] .omt-del:not(.hidden)').length === 2", timeout=15000)
    pg.wait_for_timeout(300)
    check(f"Chinese is listed with both directions downloaded {packs(pg)}", packs(pg) == ["ja", "zh"])
    check(f"Chinese is gone from the choices {opts(pg)}", opts(pg) == ["ko"])
    check("run buttons: Japanese ones and the new Chinese ones, not Korean", pg.evaluate("Array.from(document.querySelectorAll('.omt-run')).filter(b => b.offsetParent).map(b => b.dataset.omtRun)") == ["ja-en", "en-ja", "zh-en", "en-zh"])
    # ---- 3) 再読み込み: ダウンロード済みの言語だけが並ぶ（追加した覚えがなくても） ----
    settings(pg)
    check(f"after a reload the downloaded Chinese pack is still listed, Korean is not {packs(pg)}", packs(pg) == ["ja", "zh"] and opts(pg) == ["ko"])
    # ---- 4) 韓国語を追加 → 追加欄が消える ----
    pg.select_option("#omt-add-sel", "ko"); pg.click("#omt-add-btn")
    pg.wait_for_function("document.querySelector('.omt-row[data-pair=\"ko-en\"] .omt-del:not(.hidden)')", timeout=15000); pg.wait_for_timeout(300)
    check(f"all three listed, add box hidden {packs(pg)}", packs(pg) == ["ja", "zh", "ko"] and not vis(pg, "#omt-add"))
    # ---- 5) 削除すると、基本以外の言語は、並びから消えて、追加欄に戻る ----
    pg.once("dialog", lambda d: d.accept())
    pg.locator('.omt-row[data-pair="ko-en"] .omt-del').click(); pg.wait_for_timeout(600)
    check(f"deleting the only Korean model removes it from the list and back into the choices {packs(pg)} {opts(pg)}", packs(pg) == ["ja", "zh"] and opts(pg) == ["ko"] and vis(pg, "#omt-add"))
    pg.once("dialog", lambda d: d.accept())
    pg.locator('.omt-row[data-pair="en-zh"] .omt-del').click(); pg.wait_for_timeout(600)
    check(f"one Chinese direction left: still listed (so the other can be fetched again) {packs(pg)}", "zh" in packs(pg))
    pg.once("dialog", lambda d: d.accept())
    pg.locator('.omt-row[data-pair="zh-en"] .omt-del').click(); pg.wait_for_timeout(600)
    check(f"Chinese removed completely: gone from the list {packs(pg)}", packs(pg) == ["ja"] and opts(pg) == ["zh", "ko"])
    # ---- 6) 日本語は、未ダウンロードでも並ぶ（最初に入れる言語） ----
    check("the Japanese pack stays listed even when nothing is downloaded", "ja" in packs(pg) and pg.locator('.omt-row[data-pair="ja-en"] .omt-get').is_visible())
    # ---- 7) 途中で失敗: 追加した言語は並んだまま、ボタンで続きができる ----
    fail_ctx = new_ctx(br); fail_ctx.unroute("**/*")
    def h2(r):
        u = r.request.url
        if u.startswith(LIB): r.fulfill(status=200, body="export const env={backends:{onnx:{wasm:{}}}};export async function pipeline(){throw new Error('boom')}", headers=CORS, content_type="application/javascript")
        elif u.startswith(B) or u.startswith("data:") or u.startswith("blob:"): r.continue_()
        else: r.abort()
    fail_ctx.route("**/*", h2)
    q = fail_ctx.new_page(); settings(q)
    q.select_option("#omt-add-sel", "ko"); q.click("#omt-add-btn"); q.wait_for_timeout(1500)
    check(f"a failed download keeps the added language listed, with its download button {packs(q)}", packs(q) == ["ja", "ko"] and q.locator('.omt-row[data-pair="ko-en"] .omt-get').is_visible() and vis(q, "#omt-err"))
    # ---- 8) 英語表示でも崩れない ----
    ctx.request.post(B + "/set-display-language", form={"ui_lang": "English"})
    e = ctx.new_page(); settings(e)
    check("English UI: the pack titles and the add box are in English", "Add a language" in e.inner_text("#omt-add") and "Japanese ⇄ English" in e.inner_text("#omt-card"))
    check(f"no page errors {errs}", not errs)
    br.close()
print("FAILS:", fails); print("ALL PASS" if not fails else "SOME FAILED"); sys.exit(1 if fails else 0)
