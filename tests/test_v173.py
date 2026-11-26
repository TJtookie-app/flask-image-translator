"""v1.7.3: 背景のグラデーション3種（カードを少し透かす）・アクセント色・結果カード・操作の手ごたえ。文字の読みやすさは、色から計算して確かめる。"""
import os
import re

from conftest import ROOT, start


def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def _lin(c):
    c /= 255
    return c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4


def _rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _lum(rgb):
    return .2126 * _lin(rgb[0]) + .7152 * _lin(rgb[1]) + .0722 * _lin(rgb[2])


def _ratio(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + .05) / (min(la, lb) + .05)


def _over(fg, alpha, bg):
    return [round(fg[i] * alpha + bg[i] * (1 - alpha)) for i in range(3)]


def _vars(rule):
    return dict(re.findall(r"(--[\w-]+):\s*([^;}]+?)\s*(?:;|$|\})", rule))


def _rules(css):
    return re.findall(r"([^{}]+)\{([^{}]*)\}", css)


def test_version():
    import app as appmod
    assert appmod.APP_VERSION == "1.7.3"


def test_look_css_is_linked_after_theme_css_on_every_page(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    for path in ("/", "/privacy", "/start", "/offline"):
        html = c.get(path).get_data(as_text=True)
        assert html.index("theme.css") < html.index("look.css"), path
    assert c.get("/static/look.css").status_code == 200


def test_three_backgrounds_match_the_pictures_and_only_body_has_a_gradient():
    css = _read("static", "look.css")
    for needle in ("#04061A", "#0A1240", "#15308A", "#0F2027", "#203A43", "#2C5364"):
        assert needle in css, needle
    for sel, _body in _rules(css):
        if "linear-gradient" in _body:
            assert all(part.strip().endswith((" body", " body.bg-slate-950")) for part in sel.split(",")), sel      # グラデーションは、背景（body）だけ
    assert "linear-gradient" not in _read("static", "theme.css").split("sk-line::after")[0].replace("--glass", "")   # ボタン・バーは単色のまま


def test_standard_background_and_accent_change_nothing():
    st = _read("static", "js", "settings.js")
    assert "bg: 'ink', accent: 'auto'" in st
    assert re.search(r"st\.bg !== 'ink'\) d\.setAttribute\('data-bg'", st) and re.search(r"st\.accent !== 'auto'\) d\.setAttribute\('data-accent'", st)
    head = _read("templates", "components", "pwa_head.html")
    assert "data-bg" in head and "data-accent" in head                        # 描画前に反映（ちらつき防止）


def test_settings_screen_has_background_and_accent_choices(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    bg = html[html.index('data-setting="bg"'):]
    assert re.findall(r'data-v="(\w+)"', bg[:bg.index("</div>")]) == ["ink", "deep", "moon"]
    acc = html[html.index('data-setting="accent"'):]
    acc = acc[:acc.index("</div>")]
    assert re.findall(r'data-v="(\w+)"', acc) == ["auto", "indigo", "teal", "orange", "rose"]
    assert acc.count("aria-label=") == 5 and "ティール" in acc and "ローズ" in acc    # 色だけに頼らず、名前も付ける


def test_new_labels_exist_in_ja_and_en():
    import labels_en
    import labels_ja
    keys = ["set_bg", "bg_ink", "bg_deep", "bg_moon", "set_accent", "acc_auto", "acc_indigo", "acc_teal", "acc_orange", "acc_rose"]
    for k in keys:
        assert labels_ja.LABELS[k] and labels_en.LABELS[k], k


def test_accent_colors_are_readable_in_dark_and_light():
    css = _read("static", "look.css")
    dark_card, light_card = _rgb("#121A2E"), _rgb("#FBF9F4")
    seen = {"dark": 0, "light": 0}
    for sel, body in _rules(css):
        v = _vars(body)
        if "--btn" not in v:
            continue
        light = "data-theme=light]" in sel and ":not([data-theme=light])" not in sel
        btn = _rgb(v["--btn"])
        assert _ratio([255, 255, 255], btn) >= 4.5, (sel, "white on button")
        text = _rgb(v["--accent-text"]) if "--accent-text" in v else None
        if text:
            if light:
                assert _ratio(text, light_card) >= 7, (sel, "accent text on the light card")
                if "--accent-soft" in v and v["--accent-soft"].startswith("#"):
                    assert _ratio(text, _rgb(v["--accent-soft"])) >= 6, (sel, "accent text on the soft tint")
            else:
                assert _ratio(text, dark_card) >= 7, (sel, "accent text on the dark card")
        seen["light" if light else "dark"] += 1
    assert seen["dark"] >= 4 and seen["light"] >= 4 + 3     # 暗い4（インディゴ・ティール・オレンジ・ローズ）／明るい4＋高コントラスト3


def test_text_stays_readable_on_the_translucent_card_over_every_gradient_stop():
    css = _read("static", "look.css")
    dark = {"text": _rgb("#D7DCEA"), "text3": _rgb("#8D98B4")}
    light = {"text": _rgb("#34302A"), "text3": _rgb("#5B5348"), "text4": _rgb("#6B6256")}
    stops = re.findall(r"linear-gradient\(135deg, (#\w+) 0%, (#\w+) 55%, (#\w+) 100%\)", css)
    assert len(stops) == 4
    for i, row in enumerate(stops):
        is_light = i >= 2
        for stop in row:
            under = _rgb(stop)
            card = _over(_rgb("#FBF9F4") if is_light else _rgb("#121A2E"), .88 if is_light else .86, under)
            for name, col in (light if is_light else dark).items():
                need = 4.5 if name in ("text3", "text4") else 7
                assert _ratio(col, card) >= need, (stop, name, round(_ratio(col, card), 2))
    assert "rgba(var(--card-rgb), .86)" in css and "rgba(var(--card-rgb), .88) !important" in css


def test_result_card_has_accent_line_and_chip():
    html = _read("templates", "components", "result.html")
    assert 'class="rc-box ' in html and 'class="rc-tag ' in html
    css = _read("static", "look.css")
    assert "inset-inline-start: 0" in css and "var(--accent)" in css                 # 右から左の言語では、線も右へ


def test_feel_js_and_camera_frame():
    js = _read("static", "js", "feel.js")
    assert "navigator.vibrate" in js and "prefers-reduced-motion" in js and len(js.splitlines()) <= 200
    html = _read("templates", "components", "scripts.html")
    tags = re.findall(r"js/(\w+)\.js", html)
    assert tags.index("app") < tags.index("feel") and tags.index("media") < tags.index("feel")
    cam = _read("templates", "components", "camera_full.html")
    assert 'class="cam-frame" aria-hidden="true"' in cam and cam.count("<i></i>") == 4
    assert re.search(r"\.cam-frame \{[^}]*pointer-events: none", _read("static", "look.css"))


def test_reduced_motion_stops_the_new_animations():
    css = _read("static", "look.css")
    block = css[css.index("@media (prefers-reduced-motion: reduce)"):]
    for needle in (".rc-btn .fa-check", ".fav-btn .fa-solid.fa-star", "#start-record-btn", "animation: none !important"):
        assert needle in block, needle
