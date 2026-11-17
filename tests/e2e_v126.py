"""V12.6のブラウザ確認: 言語バッジが「Español（スペイン語）」のように出る（画面の言語ごと）。使い方: python tests/e2e_v126.py"""
import json, os, sys, threading, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "tests"))
import conftest  # noqa: F401
import translator
from werkzeug.serving import make_server
from app import app
from PIL import Image

DETECTED = {"v": "es"}
def fake(parts, system=None):
    if system and "box_2d" in system:
        return json.dumps({"detected_language": DETECTED["v"], "blocks": [{"text": "hola", "translation": "Hello", "box_2d": [100, 100, 250, 600]}]})
    return json.dumps({"detected_language": DETECTED["v"], "source_text": "hola", "translation": "Hello"})
translator._generate = fake
srv = make_server("127.0.0.1", 5086, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = "http://127.0.0.1:5086"
errs, fails = [], []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

tmp = tempfile.mkdtemp(); imgpath = os.path.join(tmp, "a.png"); Image.new("RGB", (600, 400), "white").save(imgpath)

from playwright.sync_api import sync_playwright
def badge(pg, ui, detected, via="image"):
    DETECTED["v"] = detected
    pg.context.request.post(B + "/set-display-language", form={"ui_lang": ui})
    pg.goto(B + "/", wait_until="domcontentloaded"); pg.click("#nav-image")
    pg.set_input_files("#tab-image input[type=file]", imgpath)
    pg.click("#tab-image button[type=submit]")
    pg.wait_for_selector(".lang-badge")
    return pg.inner_text(".lang-badge").replace("🌐", "").strip()

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 390, "height": 900})
    ctx.route("**/*", lambda r: r.abort() if not r.request.url.startswith(B) else r.continue_())
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))

    t = badge(pg, "Japanese", "es");           check(f"JA screen, code 'es' -> {t}", t == "Español（スペイン語）")
    t = badge(pg, "Japanese", "Spanish");      check(f"JA screen, name 'Spanish' -> {t}", t == "Español（スペイン語）")
    t = badge(pg, "English", "es");            check(f"EN screen -> {t}", t == "Español (Spanish)")
    t = badge(pg, "English", "English");       check(f"same names shown once -> {t}", t == "English")
    t = badge(pg, "Japanese", "ja");           check(f"JA screen, Japanese -> {t}", t == "日本語")
    t = badge(pg, "Japanese", "zh-TW");        check(f"Traditional Chinese -> {t}", t.startswith("繁體中文（") and "繁" in t)
    t = badge(pg, "Japanese", "ko");           check(f"Korean -> {t}", t == "한국어（韓国語）")
    t = badge(pg, "Japanese", "eo");           check(f"unsupported code gets a localized name -> {t}", t != "eo" and "エスペラント" in t)
    t = badge(pg, "Japanese", "Latin");        check(f"unsupported name is kept -> {t}", t == "Latin")
    t = badge(pg, "English", "fr"); check(f"French on EN screen -> {t}", t == "Français (French)")

    # 重ね翻訳（画像タブ）でも同じ
    DETECTED["v"] = "es"
    ctx.request.post(B + "/set-display-language", form={"ui_lang": "Japanese"})
    pg.goto(B + "/", wait_until="domcontentloaded"); pg.click("#nav-image")
    pg.set_input_files("#tab-image input[type=file]", imgpath)
    check("overlay mode used", pg.evaluate("document.querySelector('#tab-image input[name=overlay]') !== null"))
    check("no JS errors", not errs)
    if errs: print(errs)
    br.close()
srv.shutdown()
print("FAILED:", fails) if fails else print("ALL OK")
sys.exit(1 if fails else 0)
