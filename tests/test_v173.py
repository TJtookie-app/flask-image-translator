"""v1.7.3: 結果カード・操作の手ごたえ（背景3種とアクセント色は、v1.7.4 で取りやめた。tests/test_v174.py）。"""
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
    assert appmod.APP_VERSION.startswith(("1.7.", "1.8.", "1.9."))









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


def test_look_css_is_still_linked_after_theme_css(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    assert html.index("theme.css") < html.index("look.css")
    assert c.get("/static/look.css").status_code == 200


def test_reduced_motion_stops_the_new_animations():
    css = _read("static", "look.css")
    block = css[css.index("@media (prefers-reduced-motion: reduce)"):]
    for needle in (".rc-btn .fa-check", ".fav-btn .fa-solid.fa-star", "#start-record-btn", "animation: none !important"):
        assert needle in block, needle
