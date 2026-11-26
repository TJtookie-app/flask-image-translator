"""v1.5のブラウザ確認: 画像の文字をタップで選ぶ／全画面カメラ／単位変換。使い方: python tests/e2e_v150.py"""
import json, os, re, sys, tempfile, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import translator
from werkzeug.serving import make_server
from app import app
from PIL import Image, ImageDraw

calls = []
def fake(parts, system=None):
    calls.append(system or "")
    if system and "box_2d" in system:
        return json.dumps({"detected_language": "Japanese", "blocks": [
            {"text": "ラーメン", "translation": "Ramen noodles", "box_2d": [100, 100, 250, 600]},
            {"text": "餃子", "translation": "Gyoza", "box_2d": [500, 200, 650, 500]}]})
    return '{"detected_language":"Japanese","source_text":"こんにちは","translation":"Hello","pronunciation":""}'
translator._generate = fake
srv = make_server("127.0.0.1", 5094, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5094"
fails, errs = [], []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

tmp = tempfile.mkdtemp()
img = Image.new("RGB", (1200, 800), "white"); ImageDraw.Draw(img).text((120, 120), "RAMEN", fill="black")
imgpath = os.path.join(tmp, "menu.png"); img.save(imgpath)
cnt = lambda pg, sel: pg.evaluate(f"document.querySelectorAll('{sel}').length")
hidden = lambda pg, sel: pg.evaluate(f"document.querySelector('{sel}').classList.contains('hidden')")

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
    ctx = br.new_context(viewport={"width": 390, "height": 844}, permissions=["clipboard-read", "clipboard-write", "camera"])
    ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(B) else r.abort())
    ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(B + "/", wait_until="domcontentloaded")

    # ================= 画像: タップで選ぶ =================
    pg.click("#nav-image"); pg.set_input_files("#tab-image input[type=file]", imgpath); pg.click("#tab-image button[type=submit]")
    pg.wait_for_selector("#overlay-box:not(.hidden)"); pg.wait_for_function("document.getElementById('overlay-img').complete && document.getElementById('overlay-img').naturalWidth>0")
    check("blocks are drawn as tappable outlines, none replaced yet", cnt(pg, "#overlay-layer .ov-pick") == 2 and cnt(pg, "#overlay-layer .ov-block") == 0)
    check("nothing selected: panel shows everything", "Ramen" in pg.inner_text("#overlay-list") and "Gyoza" in pg.inner_text("#overlay-list"))
    check("main button says 即翻訳; select button says すべて選択", pg.inner_text("#overlay-toggle").strip() == "即翻訳" and pg.inner_text("#overlay-selbtn").strip() == "すべて選択")
    n0 = len(calls)
    pg.click("#overlay-layer .ov-pick >> nth=0")
    check("tapping selects the block", cnt(pg, "#overlay-layer .ov-pick.sel") == 1 and pg.get_attribute("#overlay-layer .ov-pick >> nth=0", "aria-pressed") == "true")
    lst = pg.inner_text("#overlay-list")
    check("panel shows only the selected block (translation + original)", "Ramen noodles" in lst and "ラーメン" in lst and "Gyoza" not in lst)
    pg.click("#overlay-toggle")
    check("即翻訳 replaces only the selected block", cnt(pg, "#overlay-layer .ov-block") == 1 and pg.inner_text("#overlay-layer .ov-block").strip() == "Ramen noodles" and cnt(pg, "#overlay-layer .ov-pick") == 1)
    check("button now offers going back to the original", "元の画像を見る" in pg.inner_text("#overlay-toggle"))
    ok = pg.evaluate("""() => { const e = document.querySelector('#overlay-layer .ov-block'); return e.scrollHeight <= e.clientHeight + 1 && e.scrollWidth <= e.clientWidth + 1; }""")
    check("replaced text fits its box", ok)
    pg.click("#overlay-layer .ov-block")
    check("tapping a replaced block deselects it (back to the original)", cnt(pg, "#overlay-layer .ov-block") == 0 and cnt(pg, "#overlay-layer .ov-pick.sel") == 0)
    pg.click("#overlay-selbtn")
    check("select all (replace mode still on) → both replaced, button offers clearing", cnt(pg, "#overlay-layer .ov-block") == 2 and "選択を解除" in pg.inner_text("#overlay-selbtn") and "元の画像を見る" in pg.inner_text("#overlay-toggle"))
    pg.click("#overlay-toggle")
    check("toggle again restores the original image", cnt(pg, "#overlay-layer .ov-block") == 0 and cnt(pg, "#overlay-layer .ov-pick.sel") == 2)
    pg.click("#overlay-selbtn")
    check("clear selection", cnt(pg, "#overlay-layer .ov-pick.sel") == 0)
    pg.click("#overlay-toggle")
    check("即翻訳 with nothing selected translates everything", cnt(pg, "#overlay-layer .ov-block") == 2)
    check("selecting / replacing never calls the API again", len(calls) == n0)
    pg.click("#overlay-toggle"); pg.click("#overlay-selbtn")
    pg.click("#overlay-layer .ov-pick >> nth=1"); pg.click("#overlay-copy"); pg.wait_for_timeout(200)
    check("copy copies only the selected translation", pg.evaluate("navigator.clipboard.readText()") == "Gyoza")
    pg.click("#overlay-zoom"); pg.wait_for_selector(".ov-zoom")
    check("zoom shows the selected block only", cnt(pg, ".ov-zoom .ov-block") == 1)
    pg.keyboard.press("Escape")

    # ================= カメラ: 全画面 =================
    pg.goto(B + "/", wait_until="domcontentloaded")
    check("camera is not opened by loading the page", hidden(pg, "#cam-full"))
    pg.click("#nav-text"); pg.click("#nav-camera")
    check("camera tab opens as a normal screen (no full-screen camera yet)", hidden(pg, "#cam-full") and not hidden(pg, "#tab-camera"))
    check("「翻訳する」 is disabled until a photo is taken", pg.is_disabled("#camera-submit-btn") and "カメラで撮る" in pg.inner_text("#camera-open-btn"))
    pg.click("#camera-open-btn")
    pg.wait_for_function("document.getElementById('camera-video').videoWidth > 0", timeout=15000)
    check("「カメラで撮る」 opens the full-screen camera", not hidden(pg, "#cam-full"))
    r = pg.evaluate("(() => { const v = document.getElementById('camera-video').getBoundingClientRect(); return [v.left, v.top, v.width, v.height, innerWidth, innerHeight]; })()")
    check(f"video fills the whole screen {r}", r[0] == 0 and r[1] == 0 and abs(r[2] - r[4]) <= 1 and abs(r[3] - r[5]) <= 1)
    b = pg.evaluate("(() => { const a = document.querySelector('.cam-back').getBoundingClientRect(), s = document.getElementById('camera-capture-btn').getBoundingClientRect(); return [a.left, a.top, a.width, s.width, s.bottom, innerHeight]; })()")
    check(f"back arrow at top-left, big shutter at the bottom {b}", b[0] < 40 and b[1] < 40 and b[2] >= 44 and b[3] >= 60 and b[4] <= b[5])
    check("target language shown at the top", pg.inner_text("#cam-pair").startswith("→"))
    pg.click(".cam-back")
    check("back arrow returns to the camera tab without a photo", hidden(pg, "#cam-full") and not hidden(pg, "#tab-camera") and pg.is_disabled("#camera-submit-btn") and hidden(pg, "#camera-preview"))
    check("camera stream stopped after leaving", pg.evaluate("document.getElementById('camera-video').srcObject === null || document.getElementById('camera-video').srcObject.getTracks().every(t => t.readyState === 'ended')"))
    pg.click("#camera-open-btn"); pg.wait_for_function("document.getElementById('camera-video').videoWidth > 0", timeout=15000)
    n1 = len(calls); pg.click("#camera-capture-btn")
    check("shutter → back on the camera tab with a preview, not translated yet", hidden(pg, "#cam-full") and not hidden(pg, "#camera-preview") and len(calls) == n1 and cnt(pg, "#ovc-layer .ov-pick") == 0)
    check("「翻訳する」 is enabled and the button now says 撮り直す", not pg.is_disabled("#camera-submit-btn") and "撮り直す" in pg.inner_text("#camera-open-btn"))
    pg.click("#camera-submit-btn")
    pg.wait_for_selector("#ovc-box:not(.hidden)", timeout=20000); pg.wait_for_function("document.getElementById('ovc-img').complete && document.getElementById('ovc-img').naturalWidth>0")
    check("「翻訳する」 → translated with one API call", cnt(pg, "#ovc-layer .ov-pick") == 2 and len(calls) == n1 + 1)
    pg.click("#camera-open-btn"); pg.wait_for_selector("#cam-full:not(.hidden)")
    pg.set_input_files("#cam-full input[type=file]", imgpath)
    pg.wait_for_function("document.getElementById('cam-full').classList.contains('hidden')", timeout=20000)
    check("album picture goes to the preview, not straight to translation", not hidden(pg, "#camera-preview") and not pg.is_disabled("#camera-submit-btn") and len(calls) == n1 + 1)
    pg.click("#camera-submit-btn"); pg.wait_for_selector("#ovc-layer .ov-pick", timeout=20000)
    check("album picture translated after 「翻訳する」", cnt(pg, "#ovc-layer .ov-pick") == 2 and len(calls) == n1 + 2)

    # ================= 単位変換 =================
    pg.goto(B + "/", wait_until="domcontentloaded"); pg.click("#nav-money")
    pg.wait_for_selector("#unit-cats button")
    num = lambda: float(re.sub(r"[^\d.\-]", "", pg.inner_text("#unit-result").split(" ")[0].replace(",", "")))
    check("five categories", cnt(pg, "#unit-cats button") == 5 and [t.strip() for t in pg.locator("#unit-cats button").all_inner_texts()] == ["長さ", "重さ", "温度", "体積", "面積"])
    check("default: 1 km → mi", pg.input_value("#unit-from") == "km" and pg.input_value("#unit-to") == "mi" and abs(num() - 0.621371) < 1e-5)
    pg.fill("#unit-amount", "100"); check("100 km = 62.1371 mi", abs(num() - 62.1371) < 1e-3)
    pg.fill("#unit-amount", "１００"); check("full-width digits work", abs(num() - 62.1371) < 1e-3)
    pg.fill("#unit-amount", "abc"); check("invalid input shows —", pg.inner_text("#unit-result").strip() == "—")
    pg.click("#unit-cats button >> nth=1"); pg.fill("#unit-amount", "1"); check("1 kg = 2.20462 lb", abs(num() - 2.204623) < 1e-4)
    pg.click("#unit-cats button >> nth=2"); check("temp default 20 °C → 68 °F", pg.input_value("#unit-amount") == "20" and abs(num() - 68) < 1e-9 and pg.inner_text("#unit-result").strip().endswith("°F"))
    pg.click(".money-swap >> nth=1"); check("swap: 20 °F → -6.66667 °C", abs(num() - (-6.666667)) < 1e-4)
    pg.select_option("#unit-from", "K"); pg.select_option("#unit-to", "°C"); pg.fill("#unit-amount", "0"); check("0 K = -273.15 °C", abs(num() + 273.15) < 1e-6)
    pg.click("#unit-cats button >> nth=3"); pg.fill("#unit-amount", "1"); check("1 L = 0.264172 gal", abs(num() - 0.2641721) < 1e-6)
    pg.click("#unit-cats button >> nth=4"); pg.fill("#unit-amount", "1"); check("1 m² = 10.7639 ft²", abs(num() - 10.76391) < 1e-4)
    pg.select_option("#unit-to", "tsubo"); check("1 m² = 0.3025 tsubo", abs(num() - 0.3025) < 1e-4)
    check("no horizontal scroll on the money tab", pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"))
    br.close()
print("page errors:", errs)
check("no page errors", not errs)
print("FAILS:", fails)
sys.exit(1 if fails else 0)
