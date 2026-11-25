"""v1.5: 画像の文字をタップで選ぶ・全画面カメラ・単位変換（組み立ての確認。動きは tests/e2e_v150.py）"""
import os
import re

from conftest import ROOT, start


def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def _page(env, lang="Japanese"):
    app, *_ = env
    c = app.test_client(); start(c, lang)
    return c.get("/").get_data(as_text=True)


def test_overlay_box_has_select_instant_copy_and_panel_below(env):
    html = _page(env)
    for p in ("overlay", "ovc"):
        for a in ("toggle", "select", "copy", "zoom", "save"):
            assert f"ovAction('{p}', '{a}')" in html, (p, a)
        assert f"ovAction('{p}', 'list')" not in html                         # 一覧ボタンは、常に下に出るパネルに変わった
        assert html.index(f'id="{p}-stage"') < html.index(f'id="{p}-toggle"') < html.index(f'id="{p}-list"')
    assert "訳したい文字をタップして選びます" in html


def test_selection_logic_exists():
    js = _read("static", "js", "overlay_pick.js")
    for needle in ("function ovPicked", "function pickRender", "function ovToggleSel", "function ovSelectAll", "function ovToggleOn", "ov-pick", "ov-picked", "aria-pressed"):
        assert needle in js, needle
    assert "_generate" not in js and "fetch(" not in js                       # 選び直しで API は呼ばない
    st = _read("static", "js", "overlay.js")
    assert "sel: new Set()" in st and "on: false" in st                        # 読み取り直後は、何も選ばれていない・置き換えていない


def test_zoom_and_save_use_the_picked_blocks():
    assert "ovPicked(st)" in _read("static", "js", "overlay_zoom.js")
    assert "ovPicked(st)" in _read("static", "js", "overlay_save.js")


def test_full_screen_camera_markup(env):
    html = _page(env)
    box = html[html.index('id="cam-full"'):]
    box = box[:box.index("</nav>") if "</nav>" in box else len(box)]
    for needle in ('id="camera-video"', 'id="camera-canvas"', 'class="cam-btn cam-back"', 'id="camera-capture-btn"', 'id="cam-torch"', 'type="file"', 'cameraFromFile'):
        assert needle in box, needle
    assert 'onclick="closeCameraFull()"' in box and 'onclick="captureCamera()"' in box
    # 小さなプレビュー枠は無くなり、タブには「カメラ起動」だけが残る
    tab = html[html.index('id="tab-camera"'):html.index('id="tab-conversation"')]
    assert "aspect-video" not in tab and 'id="camera-open-btn"' in tab and 'id="camera-form"' in tab
    assert 'id="camera-video"' not in tab


def test_full_screen_camera_js_and_css():
    js = _read("static", "js", "camera_full.js")
    for needle in ("function openCameraFull", "function closeCameraFull", "function toggleTorch", "function cameraFromFile", "camPrevTab", "getCapabilities", "torch", "srcObject = null", "Escape"):
        assert needle in js, needle
    assert "nav-camera" in js and "DOMContentLoaded" in js                       # タブを押した瞬間に開く
    assert "function startCamera" not in _read("static", "js", "media.js")      # 古いカメラ処理は media.js から移した
    css = _read("static", "style.css")
    assert ".cam-full" in css and "100dvh" in css and "safe-area-inset-bottom" in css and "object-fit: cover" in css


def test_unit_converter_markup_and_script(env):
    html = _page(env)
    money = html[html.index('id="tab-money"'):]
    assert 'id="unit-card"' in money and 'id="unit-amount"' in money and 'id="unit-from"' in money and 'id="unit-to"' in money and 'id="unit-result"' in money
    assert "単位変換" in html
    js = _read("static", "js", "units.js")
    for needle in ("UNIT_SETS", "function unitConvert", "function unitParse", "tsubo", "0.45359237", "1609.344", "°F", "K:"):
        assert needle in js, needle
    assert "fetch(" not in js
    order = re.findall(r"js/([a-z_0-9]+)\.js", _read("templates", "components", "scripts.html"))
    assert "units" in order and "camera_full" in order and order.index("overlay_pick") == order.index("overlay") + 1


def test_new_labels_in_ja_and_en():
    import labels_en, labels_ja
    new = ["ov_pick_hint", "ov_instant", "ov_select_all", "ov_select_none", "cam_gallery", "cam_light", "cam_hint",
           "unit_title", "unit_length", "unit_weight", "unit_temp", "unit_volume", "unit_area"]
    for k in new:
        assert labels_ja.LABELS[k].strip() and labels_en.LABELS[k].strip(), k
