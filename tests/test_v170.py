"""v1.7: 配色（ダーク「ナイト・インク」／ライト「クリア・ミント」）、ガラス風、控えめな動き、自動切り替え、高コントラスト"""
import os
import re

from conftest import ROOT, start


def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def test_theme_css_is_linked_after_style_css(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    assert html.index("style.css") < html.index("theme.css")
    assert c.get("/static/theme.css").status_code == 200


def test_palette_variables_for_dark_light_and_high_contrast():
    css = _read("static", "theme.css")
    for needle in ("--bg: #0B1020", "--card: #121A2E", "--text: #D7DCEA", "--accent: #7C83F0",     # ダーク（ナイト・インク）
                   "--bg: #F4F0E8", "--text: #34302A", "--accent: #2D6A72",                           # ライト（クリア・ミント）
                   "html[data-contrast=high]", "html[data-theme=light][data-contrast=high]"):
        assert needle in css, needle


def _luminance(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _ratio(a, b):
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_text_colors_are_readable():
    # ダーク: カード上の文字
    assert _ratio("#D7DCEA", "#121A2E") >= 10 and _ratio("#8D98B4", "#121A2E") >= 5.5 and _ratio("#6F7A96", "#121A2E") >= 3.5
    # ダーク: ボタン（白い文字）
    assert _ratio("#FFFFFF", "#5D64E0") >= 4.5
    # ライト「ウォーム・サンド」: 屋外でも読める濃さ（本文 12:1 以上、補助の文字も 6.5:1 以上）、ボタンの白い文字
    assert _ratio("#34302A", "#FBF9F4") >= 12 and _ratio("#5B5348", "#FBF9F4") >= 7 and _ratio("#5B5348", "#F4F0E8") >= 6.5
    assert _ratio("#6B6256", "#FBF9F4") >= 5.5 and _ratio("#1F5961", "#FBF9F4") >= 7 and _ratio("#FFFFFF", "#2D6A72") >= 6
    # 高コントラスト（ライト）
    assert _ratio("#1A1612", "#FFFEFB") >= 16 and _ratio("#3A342B", "#E8E0D0") >= 9 and _ratio("#174A52", "#E8F1F0") >= 8


def test_glass_only_on_three_places_and_has_fallbacks():
    css = _read("static", "theme.css")
    assert ".bottom-nav-in, .rc-menu, .undo-toast" in css and "backdrop-filter" in css
    assert "@supports not" in css and "prefers-reduced-transparency" in css
    for rule in css.split("}"):                                          # 本文のカード（bg-slate-900）には、ガラスを使わない
        if "bg-slate-9" in rule.split("{")[0]:
            assert "backdrop-filter" not in rule


def test_motion_is_subtle_and_respects_reduced_motion():
    css = _read("static", "theme.css")
    for needle in ("@keyframes tl-fade", "@keyframes tl-pop", "@keyframes tl-sheen", ".tab-content:not(.hidden)", ".is-busy"):
        assert needle in css, needle
    assert re.search(r"prefers-reduced-motion: reduce\)\s*\{[^}]*animation: none !important", css, re.S)
    assert "is-busy" in _read("static", "js", "app.js")                     # 翻訳中のボタンで光が流れる


def test_gradients_only_on_the_main_button_and_progress_bar():
    css = _read("static", "theme.css")
    for needle in (".pbar-fill", "--grad-btn", "--grad-ring", "from-indigo-600"):
        assert needle in css, needle
    assert ".hdr-brand img" not in css and ".nav-btn.text-indigo-400::after" not in css      # v1.7.1: ロゴの縁とタブの上の線は取った


def test_light_palette_is_warm_sand_not_pink():
    css = _read("static", "theme.css")
    light = css[css.index("html[data-theme=light] {"):css.index("/* 高コントラスト")]
    for needle in ("--bg: #F4F0E8", "--card: #FBF9F4", "--text: #34302A", "--accent: #2D6A72", "--btn: #2D6A72"):
        assert needle in light, needle


def test_motion_js_and_css():
    js = _read("static", "js", "motion.js")
    for needle in ("function movePill", "--pill-x", "swapping", "sk-box", "pageshow", "defaultPrevented"):
        assert needle in js, needle
    assert js.count("\n") <= 200 and "innerHTML" not in js
    css = _read("static", "theme.css")
    for needle in (".max-w-xl, .max-w-md { animation: tl-fade", ".bottom-nav-in::before", ".pill-ready", "#swap-lang-container.swapping", ".sk-box", ".sk-line"):
        assert needle in css, needle
    scripts = _read("templates", "components", "scripts.html")
    assert scripts.index("js/app.js") < scripts.index("js/motion.js")                # switchTab を包むので、app.js のあと


def test_settings_offer_auto_theme_and_high_contrast(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    box = html[html.index('data-setting="theme"'):]
    box = box[:box.index("</div>")]
    assert re.findall(r'data-v="(\w+)"', box) == ["dark", "light", "auto"]
    assert 'id="set-contrast"' in html and "高コントラスト" in html
    js = _read("static", "js", "settings.js")
    for needle in ("'auto'", "effectiveTheme", "prefers-color-scheme", "contrast", "data-contrast", "set-contrast", "#0B1020", "#F4F0E8"):
        assert needle in js, needle
    head = _read("templates", "components", "pwa_head.html")
    assert "prefers-color-scheme" in head and "data-contrast" in head and "#0B1020" in head   # 描画前に反映（ちらつき防止）


def test_old_theme_values_still_valid():
    js = _read("static", "js", "settings.js")
    assert "theme: 'dark'" in js and "contrast: false" in js                # 既定は今まで通りダーク


def test_manifest_colors_follow_the_dark_palette(env):
    app, *_ = env
    c = app.test_client()
    m = c.get("/manifest.webmanifest").get_json()
    assert m["theme_color"] == "#0B1020" and m["background_color"] == "#0B1020"


def test_new_label_in_ja_and_en():
    import labels_en, labels_ja
    assert labels_ja.LABELS["set_contrast"].strip() and labels_en.LABELS["set_contrast"].strip()
