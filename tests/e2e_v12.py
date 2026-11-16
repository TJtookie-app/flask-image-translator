"""V12のブラウザ確認（翻訳が遅いときの案内・戻るボタンでの復元・今日の残り回数）。
CDN(Tailwind等)は遮断するため、hidden クラスの付け外しと文言で確認する。使い方: python tests/e2e_v12.py"""
import os, sys, threading, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
os.environ["SITE_DAILY_LIMIT"] = "16"
import translator
from werkzeug.serving import make_server
from app import app

DELAY = {"s": 0.0}
def fake(parts, system=None):
    time.sleep(DELAY["s"])
    return '{"detected_language":"English","source_text":"Hello","translation":"こんにちは","pronunciation":"Konnichiwa"}'
translator._generate = fake
srv = make_server("127.0.0.1", 5083, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5083"
errs, fails = [], []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 390, "height": 844})
    ctx.route("**/*", lambda r: r.abort() if not r.request.url.startswith(B) else r.continue_())
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
    pg.goto(B + "/", wait_until="domcontentloaded")
    pg.wait_for_function("typeof startWaitNotice==='function' && typeof refreshQuota==='function'")

    # ---- 今日の残り回数 ----
    pg.wait_for_function("document.getElementById('quota-note').textContent.includes('16')")
    check("quota note shows 16 and is visible", "hidden" not in pg.get_attribute("#quota-note", "class") and "あと16回" in pg.inner_text("#quota-note"))

    # ---- 速い翻訳では、案内は出ない ----
    pg.fill("textarea[name=direct_text]", "Hello")
    pg.click("#tab-text button[type=submit]")
    pg.wait_for_selector(".rc-actions")
    check("no wait note after a fast translation", pg.evaluate("[...document.querySelectorAll('.wait-note')].every(n => n.classList.contains('hidden'))"))
    pg.wait_for_function("document.getElementById('quota-note').textContent.includes('15')")
    check("quota went down to 15 after one translation", "あと15回" in pg.inner_text("#quota-note"))

    # ---- 遅い翻訳（8秒）では、6秒後に案内が出る ----
    DELAY["s"] = 8.0
    pg.fill("textarea[name=direct_text]", "Hello again")
    # 送信後のページ移動中は Playwright から画面を読めないので、画面内のタイマーで状態を記録しておき、結果ページで読む
    pg.evaluate("""() => {
        sessionStorage.removeItem('probe');
        const snap = (k) => {
            const n = document.querySelector('.wait-note');
            const b = document.querySelector('#tab-text button[type=submit]');
            const p = JSON.parse(sessionStorage.getItem('probe') || '{}');
            p[k] = {note: !!n && !n.classList.contains('hidden'), text: n ? n.textContent : '', disabled: b.disabled, label: b.textContent.trim(), t: performance.now()};
            sessionStorage.setItem('probe', JSON.stringify(p));
        };
        document.querySelector('#tab-text form').addEventListener('submit', () => {
            setTimeout(() => snap('s3'), 3000);     // 3秒後
            setTimeout(() => snap('s7'), 7000);     // 7秒後（6秒の案内が出ているはず）
        });
    }""")
    pg.click("#tab-text button[type=submit]", no_wait_after=True)
    pg.wait_for_selector(".rc-actions", timeout=20000)
    probe = pg.evaluate("JSON.parse(sessionStorage.getItem('probe') || '{}')")
    print("probe:", probe)
    check("no wait note at 3 seconds", bool(probe.get("s3")) and not probe["s3"]["note"])
    check("wait note appears by 7 seconds", bool(probe.get("s7")) and probe["s7"]["note"] and "1分" in probe["s7"]["text"])
    check("submit button is disabled and says translating", bool(probe.get("s7")) and probe["s7"]["disabled"] and "翻訳中" in probe["s7"]["label"])
    check("result arrived after the slow translation", "こんにちは" in pg.inner_text("#resultText-text"))
    DELAY["s"] = 0.0

    # ---- 戻るボタンで画面が復元されたとき、押せる状態に戻る ----
    pg.goto(B + "/", wait_until="domcontentloaded")
    pg.wait_for_function("typeof resetSubmitButtons==='function'")
    pg.evaluate("document.querySelector('#tab-text form').addEventListener('submit', e => e.preventDefault())")
    pg.fill("textarea[name=direct_text]", "x")
    pg.click("#tab-text button[type=submit]")
    check("button disabled after submit", pg.evaluate("document.querySelector('#tab-text button[type=submit]').disabled"))
    pg.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")
    check("button is enabled again after pageshow(persisted)", pg.evaluate("(() => { const b = document.querySelector('#tab-text button[type=submit]'); return !b.disabled && !b.classList.contains('opacity-60'); })()"))
    check("button label restored", pg.evaluate("document.querySelector('#tab-text .btn-label').textContent.trim()") == "翻訳する")
    check("wait note hidden again", pg.evaluate("[...document.querySelectorAll('.wait-note')].every(n => n.classList.contains('hidden'))"))

    # ---- 枠が尽きたら、赤い案内になる ----
    import limits
    limits.limiter.site_day = 16
    pg.evaluate("refreshQuota()")
    pg.wait_for_function("document.getElementById('quota-note').classList.contains('none')")
    check("quota note says used up", "終わりました" in pg.inner_text("#quota-note"))
    limits.limiter.site_day = 14
    pg.evaluate("refreshQuota()")
    pg.wait_for_function("document.getElementById('quota-note').classList.contains('low')")
    check("quota note is amber when 3 or fewer", "あと2回" in pg.inner_text("#quota-note"))
    # 上限が大きい設定では出さない
    os.environ["SITE_DAILY_LIMIT"] = "3000"
    pg.evaluate("refreshQuota()")
    pg.wait_for_function("document.getElementById('quota-note').classList.contains('hidden')")
    check("quota note hidden when the limit is large", True)
    check("no JS page errors (%s)" % errs, not errs)
    br.close()
print("\nFAILS:", fails)
sys.exit(1 if fails else 0)
