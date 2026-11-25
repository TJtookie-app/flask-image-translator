"""V12.5のブラウザ確認（画像の結果: 一覧・拡大・保存 / カメラの結果表示 / PDFの進捗バーと履歴 / 単語帳の逆引き）。
CDN(Tailwind等)は遮断するため、表示の有無は hidden クラスと文言で確認する。使い方: python tests/e2e_v125.py"""
import json, os, re, sys, threading, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import translator
from werkzeug.serving import make_server
from app import app
from PIL import Image, ImageDraw
from pypdf import PdfWriter

PDF_DELAY = {"s": 0.0}
def fake(parts, system=None):
    prompt = parts[-1] if parts else ""
    if system and "box_2d" in system:
        return json.dumps({"detected_language": "Japanese", "blocks": [
            {"text": "ラーメン", "translation": "Ramen noodles", "box_2d": [100, 100, 250, 600]},
            {"text": "餃子", "translation": "Gyoza", "box_2d": [500, 200, 650, 500]}]})
    if system and "pages" in system:
        time.sleep(PDF_DELAY["s"])
        m = re.search(r"pages (\d+) to (\d+)", prompt)
        a, b = int(m.group(1)), int(m.group(2))
        return json.dumps({"pages": [{"page": n, "translation": f"Translated page {n}"} for n in range(a, b + 1)]})
    return '{"detected_language":"Japanese","source_text":"こんにちは","translation":"Hello","pronunciation":"Hello (pron)"}'
translator._generate = fake
srv = make_server("127.0.0.1", 5085, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5085"
errs, fails = [], []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

tmp = tempfile.mkdtemp()
img = Image.new("RGB", (1200, 800), "white"); d = ImageDraw.Draw(img)
d.text((120, 120), "RAMEN", fill="black")
imgpath = os.path.join(tmp, "menu.png"); img.save(imgpath)
w = PdfWriter()
for _ in range(7): w.add_blank_page(width=200, height=200)
pdfpath = os.path.join(tmp, "doc.pdf"); w.write(open(pdfpath, "wb"))

hidden = lambda pg, sel: pg.evaluate(f"document.querySelector('{sel}').classList.contains('hidden')")

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    br = p.chromium.launch(args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"])
    ctx = br.new_context(viewport={"width": 390, "height": 900}, accept_downloads=True, permissions=["camera"])
    ctx.route("**/*", lambda r: r.abort() if not r.request.url.startswith(B) else r.continue_())
    pg = ctx.new_page()
    pg.add_init_script("Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{speak(){window.__spoken=(window.__spoken||[]).concat([[arguments[0].text,arguments[0].lang]])},cancel(){},getVoices(){return[]}}});window.SpeechSynthesisUtterance=function(t){this.text=t}")
    pg.on("pageerror", lambda e: errs.append(str(e)))
    ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})

    # ================= 画像タブ: 結果の操作ボタン =================
    pg.goto(B + "/", wait_until="domcontentloaded"); pg.click("#nav-image")
    pg.set_input_files("#tab-image input[type=file]", imgpath)
    pg.click("#tab-image button[type=submit]")
    pg.wait_for_selector("#overlay-box:not(.hidden)")
    pg.wait_for_function("document.getElementById('overlay-img').complete && document.getElementById('overlay-img').naturalWidth>0")
    check("5 tool buttons visible (toggle/select/copy/zoom/save)", all(not hidden(pg, f"#overlay-{b}") for b in ("toggle", "selbtn", "copy", "zoom", "save")))
    check("buttons are tall enough to tap (>=44px)", pg.evaluate("[...document.querySelectorAll('#overlay-box .ov-tool')].every(b => b.getBoundingClientRect().height >= 43)"))

    # 一覧で見る
    check("panel under the image shows translations and originals", not hidden(pg, "#overlay-list") and "Gyoza" in pg.inner_text("#overlay-list") and "餃子" in pg.inner_text("#overlay-list"))
    check("image stays visible next to the panel", not hidden(pg, "#overlay-stage"))
    check("fallback note not shown when the image exists", "表示できませんでした" not in pg.inner_text("#overlay-list"))

    # 拡大
    pg.click("#overlay-toggle")   # 即翻訳（何も選んでいなければ全部）
    pg.click("#overlay-zoom")
    pg.wait_for_selector(".ov-zoom")
    check("zoom viewer opens with both blocks", pg.evaluate("document.querySelectorAll('.ov-zoom .ov-block').length") == 2)
    w1 = pg.evaluate("document.querySelector('.ov-zoom-stage').style.width")
    pg.click(".ov-zoom-btn[aria-label='大きくする']")
    w2 = pg.evaluate("document.querySelector('.ov-zoom-stage').style.width")
    check(f"zoom in widens the image ({w1} -> {w2})", w1 == "100%" and w2 == "150%")
    pg.click(".ov-zoom-btn[aria-label='小さくする']")
    check("zoom out narrows it again", pg.evaluate("document.querySelector('.ov-zoom-stage').style.width") == "100%")
    pg.keyboard.press("Escape")
    check("Escape closes the zoom viewer", pg.evaluate("document.querySelector('.ov-zoom')") is None)

    # 保存
    with pg.expect_download() as dl:
        pg.click("#overlay-save")
    path = dl.value.path()
    check(f"download name {dl.value.suggested_filename}", re.fullmatch(r"tookie-\d{8}-\d{4}\.jpg", dl.value.suggested_filename) is not None)
    out = Image.open(path).convert("RGB")
    check(f"saved image keeps the size {out.size}", out.size == (1200, 800))
    px = out.getpixel((125, 85))   # 1つ目の訳文ブロック(左上の角)。元画像は白
    check(f"translation block is painted on the saved image {px}", sum(px) < 200)
    far = out.getpixel((1100, 700))
    check(f"outside the blocks the photo is unchanged {far}", sum(far) > 700)
    # 文字（白）が描かれている
    box = out.crop((120, 80, 720, 200))
    check("white text exists inside the block", box.getextrema()[0][1] > 200)   # 枠は暗い色で塗られるので、明るい点があれば文字
    check("save label returns to normal after saving", (time.sleep(2.6), "画像を保存" in pg.inner_text("#overlay-save"))[1])

    # 長い訳文でも枠からはみ出さず描ける（折り返し）
    r = pg.evaluate("""async () => {
        const blob = await renderOverlayBlob([{text:'x', translation:'これはとても長い翻訳文で、小さな枠の中に折り返して収める必要があります。This is a very long translation that must wrap.', box:[100,100,160,400]}], lastImage('image'));
        return blob.size;
    }""")
    check(f"long text renders ({r} bytes)", r > 1000)
    # 画像を保持できなかったとき（HEIC など）は一覧になり、保存・拡大は出ない
    pg.evaluate("storeLastImage('', 'image')")
    pg.reload(wait_until="domcontentloaded")
    check("reload without the stored image is OK", True)

    # ================= カメラタブ =================
    pg.goto(B + "/", wait_until="domcontentloaded"); pg.click("#nav-camera")
    check("camera tab overlay hidden before translating", hidden(pg, "#ovc-box"))
    pg.evaluate("startCamera()")
    pg.wait_for_function("document.getElementById('camera-video').videoWidth > 0", timeout=15000)
    pg.click("#camera-capture-btn")
    pg.wait_for_selector("#ovc-box:not(.hidden)", timeout=20000)
    pg.wait_for_function("document.getElementById('ovc-img').complete && document.getElementById('ovc-img').naturalWidth>0")
    check("camera result is shown on the camera tab", pg.is_visible("#tab-camera") and "Ramen" in pg.inner_text("#resultText-camera"))
    check("camera photo is shown with the translation laid over it", pg.evaluate("document.getElementById('ovc-img').src.startsWith('data:image/jpeg')") and pg.evaluate("document.querySelectorAll('#ovc-layer .ov-pick').length") == 2)
    check("image tab overlay not touched", hidden(pg, "#overlay-box"))
    check("camera panel lists the translations", not hidden(pg, "#ovc-list") and "Gyoza" in pg.inner_text("#ovc-list"))
    with pg.expect_download() as dl2:
        pg.click("#ovc-save")
    check("camera photo can be saved", dl2.value.suggested_filename.endswith(".jpg") and Image.open(dl2.value.path()).size[0] > 100)
    check("camera result is saved to history with mode camera", pg.evaluate("loadHistory()[0].mode") == "camera")

    # ================= PDF: 進捗バーと履歴 =================
    PDF_DELAY["s"] = 1.0
    pg.goto(B + "/", wait_until="domcontentloaded"); pg.click("#nav-image")
    pg.set_input_files("#tab-image input[type=file]", pdfpath)
    pg.click("#tab-image button[type=submit]")
    pg.wait_for_selector("#pdf-result .pbar")
    check("progress bar is moving before the first answer", pg.evaluate("document.querySelector('#pdf-result .pbar').classList.contains('ind')"))
    pg.wait_for_function("document.querySelectorAll('#pdf-result .p-3').length === 3")
    mid = pg.evaluate("Number(document.querySelector('#pdf-result .pbar').getAttribute('aria-valuenow'))")
    check(f"progress after the first 3 of 7 pages is about 43% ({mid})", 40 <= mid <= 46 and not pg.evaluate("document.querySelector('#pdf-result .pbar').classList.contains('ind')"))
    check("status shows percent", "%" in pg.inner_text("#pdf-result [role=status]"))
    pg.wait_for_function("document.querySelectorAll('#pdf-result .p-3').length === 7", timeout=20000)
    pg.wait_for_function("document.querySelector('#pdf-result .pbar').classList.contains('pbar-done')")
    check("bar reaches 100% and turns done", pg.evaluate("document.querySelector('#pdf-result .pbar').getAttribute('aria-valuenow')") == "100")
    PDF_DELAY["s"] = 0.0
    h = pg.evaluate("loadHistory()[0]")
    check(f"PDF saved to history ({h['src']})", h["mode"] == "pdf" and "doc.pdf" in h["src"] and "7" in h["src"] and "Translated page 7" in h["out"])
    pg.click("#nav-history"); pg.click("#hf-all")
    card = pg.inner_text("#history-list > div:first-child")
    check("history card shows PDF → target", "PDF →" in card and "doc.pdf" in card)
    check("PDF history card has no 'reuse as text' button", pg.evaluate("[...document.querySelectorAll('#history-list > div:first-child button')].filter(b => b.getAttribute('aria-label') === UI.reuse).length") == 0 and pg.evaluate("[...document.querySelectorAll('#history-list > div:nth-child(5) button')].length") >= 0)
    # 履歴1件の長さは、バックアップの上限(5000字)以内
    pg.evaluate("savePdfHistory({name:'big.pdf'}, ['あ'.repeat(3000), 'い'.repeat(3000)])")
    check("long PDF history entry is capped under 5000 chars", len(pg.evaluate("loadHistory()[0].out")) <= 4801)
    check("capped entry survives backup validation", pg.evaluate("cleanHistoryItem(loadHistory()[0]) !== null && cleanHistoryItem(loadHistory()[0]).out.length > 4000"))
    # 中止しても、翻訳できたぶんは履歴に残る
    PDF_DELAY["s"] = 1.0
    pg.click("#nav-image")
    pg.set_input_files("#tab-image input[type=file]", pdfpath)
    pg.click("#tab-image button[type=submit]")
    pg.wait_for_function("document.querySelectorAll('#pdf-result .p-3').length === 3", timeout=15000)
    pg.click("#pdf-result button >> text=中止")
    pg.wait_for_function("document.querySelector('#pdf-result .pbar').classList.contains('pbar-stopped')")
    h = pg.evaluate("loadHistory()[0]")
    check(f"stopped PDF keeps the translated pages ({h['src']})", h["mode"] == "pdf" and "3" in h["src"])
    PDF_DELAY["s"] = 0.0

    # ================= 単語帳: 逆引き復習 =================
    pg.goto(B + "/", wait_until="domcontentloaded")
    pg.evaluate("localStorage.removeItem('tl_vocab_v1'); localStorage.removeItem('tl_study_dir_v1')")
    pg.fill("textarea[name=direct_text]", "こんにちは")
    pg.click("#tab-text button[type=submit]")
    pg.wait_for_selector("#resultText-text")
    pg.click("#tab-text .rc-more"); pg.click("#tab-text button[onclick*=saveVocabCurrent]")
    pg.click("#nav-history"); pg.click("#hf-study")
    check("direction buttons exist, forward selected by default", pg.get_attribute("#study-dir-fwd", "aria-pressed") == "true" and pg.get_attribute("#study-dir-rev", "aria-pressed") == "false")
    pg.click("#study-dir-rev")
    check("reverse selected and remembered", pg.get_attribute("#study-dir-rev", "aria-pressed") == "true" and pg.evaluate("localStorage.getItem('tl_study_dir_v1')") == "rev")
    check("1 card due in reverse", "1" in pg.inner_text("#study-stats"))
    pg.click("#study-start")
    check("reverse: the translation is the question", pg.inner_text("#study-front") == "Hello" and not pg.is_visible("#study-back"))
    check("reverse: pronunciation of the question is shown", "Hello (pron)" in pg.inner_text("#study-front-pron") and pg.is_visible("#study-front-speak"))
    pg.click("#study-reveal")
    check("reverse: the original is the answer", pg.inner_text("#study-answer") == "こんにちは" and pg.is_visible("#study-grade"))
    spoken = pg.evaluate("window.__spoken || []")
    check(f"reverse: the answer is read in the original language {spoken[-1:]}", bool(spoken) and spoken[-1][0] == "こんにちは" and spoken[-1][1].lower().startswith("ja"))
    pg.click("#study-grade button >> nth=1")   # 覚えた
    v = pg.evaluate("JSON.parse(localStorage.getItem('tl_vocab_v1'))[0]")
    check(f"reverse progress is stored separately (rbox={v.get('rbox')}, box={v['box']})", v.get("rbox") == 1 and v.get("rdue", 0) > 0 and v["box"] == 0 and v["due"] == 0)
    check("reverse session ends", not pg.is_visible("#study-card") and "今日の復習は終わり" in pg.inner_text("#study-msg"))
    pg.click("#study-dir-fwd")
    check("forward still has the card due", "1" in pg.inner_text("#study-stats") and pg.is_visible("#study-start"))
    pg.click("#study-start")
    check("forward: the original is the question again", pg.inner_text("#study-front") == "こんにちは" and not pg.is_visible("#study-front-speak"))
    pg.click("#study-dir-rev")
    check("switching direction mid-study closes the card", not pg.is_visible("#study-card"))
    check("backup keeps the reverse progress", pg.evaluate("collectBackup().data.vocab[0].rbox") == 1 and pg.evaluate("parseBackup(JSON.stringify(collectBackup())).vocab[0].rbox") == 1)
    pg.reload(wait_until="domcontentloaded"); pg.click("#nav-history"); pg.click("#hf-study")
    check("direction survives a reload", pg.get_attribute("#study-dir-rev", "aria-pressed") == "true")

    check("no JS errors", not errs)
    if errs: print(errs)
    br.close()
srv.shutdown()
print("FAILED:", fails) if fails else print("ALL OK")
sys.exit(1 if fails else 0)
