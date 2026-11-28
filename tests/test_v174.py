"""v1.7.4: 背景（グラデーション）とアクセント色の選択を取りやめ、ダーク・ライトを v1.7.2 の見た目に戻した。"""
import os

from conftest import ROOT, start


def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def test_version():
    import app as appmod
    assert appmod.APP_VERSION.startswith(("1.7.", "1.8.", "1.9.", "1.10.", "1.11.", "1.12."))


def test_settings_screen_has_no_background_or_accent_choices(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    for needle in ('data-setting="bg"', 'data-setting="accent"', "acc-dot", "背景", "アクセント色"):
        assert needle not in html, needle
    assert 'data-setting="theme"' in html and 'id="set-contrast"' in html          # 配色（ダーク・ライト・自動）と高コントラストは、そのまま


def test_no_trace_of_background_or_accent_in_the_code():
    look = _read("static", "look.css")
    for needle in ("data-bg", "data-accent", "linear-gradient", ".acc-", "#04061A", "#0F2027"):
        assert needle not in look, needle
    st = _read("static", "js", "settings.js")
    assert "bg: [" not in st and "accent: [" not in st and "'#04061A'" not in st
    assert "removeAttribute('data-bg')" in st and "removeAttribute('data-accent')" in st      # v1.7.3 で付いた属性が残らない
    head = _read("templates", "components", "pwa_head.html")
    assert "data-bg" not in head and "data-accent" not in head


def test_theme_css_is_exactly_the_v1_7_2_one():
    css = _read("static", "theme.css")
    assert "--accent-rgb" not in css and "--accent-hi" not in css
    assert "--accent: #7C83F0" in css and "--accent: #2D6A72" in css and "--btn: #5D64E0" in css


def test_labels_for_the_removed_part_are_gone():
    import labels_en
    import labels_ja
    for k in ("set_bg", "bg_ink", "bg_deep", "bg_moon", "set_accent", "acc_auto", "acc_indigo", "acc_teal", "acc_orange", "acc_rose"):
        assert k not in labels_ja.LABELS and k not in labels_en.LABELS, k


def test_what_stays_from_v1_7_3():
    assert "rc-box" in _read("templates", "components", "result.html")
    assert os.path.exists(os.path.join(ROOT, "static", "js", "feel.js"))
    assert "cam-frame" in _read("templates", "components", "camera_full.html")
    assert os.path.exists(os.path.join(ROOT, "tools", "generate_phrasebook.py"))
