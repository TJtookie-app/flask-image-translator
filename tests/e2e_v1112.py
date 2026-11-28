"""v1.11.2（スペイン語・フランス語・ドイツ語・イタリア語・ロシア語・インドネシア語を追加）のブラウザ確認。翻訳エンジンとモデルは模擬
（出力に、入力と、使ったモデルの名前が入るので、手順と、中国語の文字の指定が正しいかを確かめられる）。使い方: python tests/e2e_v1112.py"""
import os, sys, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import rates
from werkzeug.serving import make_server
from app import app

rates._http_get = lambda url: {"result": "success", "time_last_update_unix": 1794900000, "base_code": "USD", "rates": {"USD": 1, "JPY": 154.3}}
srv = make_server("127.0.0.1", 5111, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5111"
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
    opts = lambda: pg.evaluate("Array.from(document.querySelectorAll('#omt-add-sel option')).filter(o => o.value && !o.hidden && !o.disabled).map(o => o.value)")
    packs = lambda: pg.evaluate("Array.from(document.querySelectorAll('.omt-pack')).filter(e => e.offsetParent).map(e => e.dataset.pack)")
    # ---- 1) 言語バー・追加の選択肢に6言語 ----
    check("the language bars have the six new languages", all(pg.locator(f"#omt-tab-from option[value='{n}']").count() == 1 for n in ("Spanish", "French", "German", "Italian", "Russian", "Indonesian")))
    pg.evaluate("setHistFilter('settings')"); pg.wait_for_timeout(300)
    check(f"six new languages are offered under 'add a language' {opts()}", all(x in opts() for x in ("es", "fr", "de", "it", "ru", "id")))
    # ---- 2) スペイン語と日本語を追加 → 日本語 → スペイン語は、英語を経由 ----
    pg.locator('.omt-row[data-pair="ja-en"] .omt-get').click()
    pg.wait_for_function("document.querySelector('.omt-row[data-pair=\"ja-en\"] .omt-del:not(.hidden)')", timeout=10000)
    pg.select_option("#omt-add-sel", "es"); pg.click("#omt-add-btn")
    pg.wait_for_function("document.querySelectorAll('.omt-row[data-pair=\"es-en\"] .omt-del:not(.hidden), .omt-row[data-pair=\"en-es\"] .omt-del:not(.hidden)').length === 2", timeout=15000); pg.wait_for_timeout(300)
    check(f"Spanish is listed after the download, gone from the choices {packs()} {opts()}", packs() == ["ja", "es"] and "es" not in opts())
    pg.select_option("#omt-tab-from", "Japanese"); pg.select_option("#omt-tab-to", "Spanish")
    out = run(pg, "こんにちは", "en-es")
    check(f"ja→es goes ja-en then en-es {out!r}", out == "<opus-mt-en-es:<ja-en:こんにちは>>".replace("opus-mt-", ""))
    check("and says it went through English", "英語を経由" in pg.inner_text("#omt-tab-label"))
    # ---- 3) スペイン語を選んで、アルファベットの文を入れても、英語に変わらない ----
    pg.select_option("#omt-tab-from", "Spanish"); pg.select_option("#omt-tab-to", "English")
    pg.fill("#omt-tab-in", "¿Dónde está la estación?")
    check(f"Spanish text typed with Spanish chosen keeps Spanish {bar(pg)}", bar(pg) == ("Spanish", "English"))
    out = run(pg, "¿Dónde está la estación?", "es-en")
    check(f"es→en direct {out!r}", out == "<es-en:¿Dónde está la estación?>")
    pg.select_option("#omt-tab-from", "Japanese"); pg.fill("#omt-tab-in", "Hello")
    check(f"typing English while Japanese is chosen still flips to English {bar(pg)}", bar(pg)[0] == "English")
    # ---- 4) キリル文字は、ロシア語として扱う（モデルが無ければ、案内が出る） ----
    pg.fill("#omt-tab-in", "Привет")
    check(f"Cyrillic text turns From into Russian {bar(pg)}", bar(pg)[0] == "Russian")
    check("Russian is not downloaded: the need box names the missing model", "ロシア語" in pg.inner_text("#omt-tab-need") or "Russian" in pg.inner_text("#omt-tab-need"))
    # ---- 5) 英語 → ドイツ語・フランス語は直接 ----
    for lang in ("de", "fr", "it", "ru", "id"):
        pg.select_option("#omt-add-sel", lang); pg.click("#omt-add-btn")
    pg.wait_for_function("document.querySelectorAll('.omt-del:not(.hidden)').length === 13", timeout=30000); pg.wait_for_timeout(300)
    for lang, name in (("de", "German"), ("fr", "French"), ("it", "Italian"), ("ru", "Russian"), ("id", "Indonesian")):
        pg.select_option("#omt-tab-from", "English"); pg.select_option("#omt-tab-to", name)
        out = run(pg, "Thank you", f"en-{lang}")
        check(f"en→{lang} direct {out!r}", out == f"<en-{lang}:Thank you>")
    # ---- 6) ドイツ語 → フランス語は、英語を経由 ----
    pg.select_option("#omt-tab-from", "German"); pg.select_option("#omt-tab-to", "French")
    out = run(pg, "Danke", "en-fr")
    check(f"de→fr goes de-en then en-fr {out!r}", out == "<en-fr:<de-en:Danke>>")
    # ---- 7) 自動ダウンロードは、日本語⇄英語だけ（新しい言語には広げない） ----
    check("auto-download rows are still only ja-en and en-ja", pg.evaluate("Array.from(document.querySelectorAll('.omt-row[data-auto]')).map(r => r.dataset.pair)") == ["ja-en", "en-ja"])
    check(f"no page errors {errs}", not errs)
    br.close()
print("FAILS:", fails); print("ALL PASS" if not fails else "SOME FAILED"); sys.exit(1 if fails else 0)
