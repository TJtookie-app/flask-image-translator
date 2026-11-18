"""V12.5: 画像・カメラの結果表示（拡大・保存・一覧）、PDFの進捗バーと履歴、単語帳の逆引き"""
import base64
import io
import json
import os
import re

from conftest import start, ROOT

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
BLOCKS_JSON = json.dumps({"detected_language": "Japanese", "blocks": [
    {"text": "ラーメン", "translation": "Ramen", "box_2d": [100, 50, 200, 400]},
    {"text": "餃子", "translation": "Gyoza", "box_2d": [300, 60, 380, 300]}]})


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def read_js(*names):
    """分割したJSをまとめて読む（V12.11 で money.js / overlay.js を複数ファイルに分けた）"""
    return "\n".join(read("static", "js", n + ".js") for n in names)


MONEY_JS = ("money", "money_start", "money_where", "money_view")
OVERLAY_JS = ("overlay", "overlay_zoom", "overlay_save", "overlay_boot")


def test_image_tab_has_the_four_tools(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    for p in ("overlay", "ovc"):   # 画像タブとカメラタブ
        for part in ("box", "stage", "img", "layer", "list", "toggle", "listbtn", "zoom", "save"):
            assert f'id="{p}-{part}"' in html, f"{p}-{part}"
        for action in ("toggle", "list", "zoom", "save"):
            assert f"ovAction('{p}', '{action}')" in html
    assert "拡大" in html and "画像を保存" in html


def test_camera_posts_overlay_and_gets_blocks(env):
    app, translator, calls, mp = env
    mp.setattr(translator, "_generate", lambda parts, system=None: (calls.append((parts, system)) or BLOCKS_JSON))
    c = app.test_client(); start(c, "Japanese")
    page = c.get("/").get_data(as_text=True)
    assert re.search(r'id="camera-form".*?name="overlay" value="1"', page, re.S)   # カメラのフォームが重ね翻訳を要求する
    data_url = "data:image/png;base64," + base64.b64encode(PNG).decode()
    r = c.post("/", data={"mode": "camera", "overlay": "1", "camera_data": data_url})
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "box_2d" in calls[-1][1]
    assert "const OVERLAY_BLOCKS = [{" in html and "Gyoza" in html
    assert 'const INITIAL_TAB = "camera"' in html
    assert "Ramen\nGyoza" in html   # 結果欄にも訳文が入る


def test_camera_without_overlay_still_works(env):
    app, translator, calls, _ = env
    c = app.test_client(); start(c)
    data_url = "data:image/png;base64," + base64.b64encode(PNG).decode()
    r = c.post("/", data={"mode": "camera", "camera_data": data_url})
    assert "const OVERLAY_BLOCKS = null;" in r.get_data(as_text=True)


def test_scripts_loaded_and_precached(env):
    app, *_ = env
    c = app.test_client(); start(c)
    html = c.get("/").get_data(as_text=True)
    assert html.index("js/overlay.js") < html.index("js/pdf.js") < html.index("js/status.js")
    assert "js/pdf.js" in c.get("/sw.js").get_data(as_text=True)


def test_overlay_js_wiring():
    js = read_js(*OVERLAY_JS)
    for needle in ("function openZoom", "function saveOverlayImage", "function renderOverlayBlob", "function wrapLines",
                   "tl_last_img_camera", "OV_VIEWS", "AbortError", "ZOOM_LEVELS", "Escape"):
        assert needle in js, needle
    # 保存はスマホでは共有シート、PCではダウンロード
    assert "pointer: coarse" in js and "navigator.canShare" in js and "a.download" in js
    media = read("static", "js", "media.js")
    assert "storeLastImage($('camera_data').value, 'camera')" in media


def test_pdf_js_progress_and_history():
    js = read("static", "js", "pdf.js")
    for needle in ("makeProgressBar", "role", "progressbar", "aria-valuenow", "savePdfHistory", "state('done')", "state('error')", "state('stopped')", "finally"):
        assert needle in js, needle
    # 履歴1件の訳文は、バックアップの読み込み上限（5000字）に収める
    m = re.search(r"PDF_HIST_MAX = (\d+)", js)
    assert m and int(m.group(1)) < 5000
    backup = read("static", "js", "backup.js")
    assert "str(e.out, 5000)" in backup
    # 履歴の表示: PDF は「PDF → 言語」、「もう一度使う」は出さない
    hist = read("static", "js", "history.js")
    assert "e.mode === 'pdf' ? 'PDF'" in hist and "OFFLINE_PAGE || e.mode === 'pdf'" in hist


def test_study_reverse_wiring(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    for needle in ("study-dir-fwd", "study-dir-rev", "study-front-pron", "study-front-speak", "原文 → 訳", "訳 → 原文"):
        assert needle in html, needle
    # オフライン画面でも同じ画面部品を使う
    off = c.get("/offline").get_data(as_text=True)
    assert "study-dir-rev" in off
    js = read("static", "js", "study.js")
    for needle in ("function setStudyDir", "rbox", "rdue", "tl_study_dir_v1", "function studyFace"):
        assert needle in js, needle
    backup = read("static", "js", "backup.js")
    assert "rbox:" in backup and "rdue:" in backup


def test_new_labels_in_both_languages():
    import languages
    keys = ["ov_list", "ov_list_hide", "ov_zoom", "ov_zoom_in", "ov_zoom_out", "ov_save", "ov_saved", "ov_save_fail",
            "pdf_hist_pages", "study_dir_fwd", "study_dir_rev", "study_dir_hint"]
    ja, en = languages.UI_LABELS["Japanese"], languages.UI_LABELS["English"]
    for k in keys:
        assert ja.get(k) and en.get(k), k
    assert "{n}" in ja["pdf_hist_pages"] and "{n}" in en["pdf_hist_pages"]


def test_css_for_new_parts():
    css = read("static", "style.css")
    for needle in (".ov-tool", ".ov-zoom", ".ov-zoom-bar", ".pbar", ".pbar-fill", "@keyframes pbar-slide", "prefers-reduced-motion"):
        assert needle in css, needle
    # 操作ボタンは指で押しやすい高さ（2.75rem = 44px 以上）
    assert re.search(r"\.ov-tool \{[^}]*min-height: 2\.75rem", css)
