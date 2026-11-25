"""v1.3.1: 設定タブのボタン列に、「まだ先がある」合図（端のうすれ・小さな矢印）"""
import os

from conftest import ROOT, start


def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def test_chip_row_has_scroll_hint_arrows(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    assert 'id="hist-scroll"' in html and 'id="hist-arrow-l"' in html and 'id="hist-arrow-r"' in html
    assert html.index('id="hist-arrow-l"') < html.index('id="hist-chips"') < html.index('id="hist-arrow-r"') < html.index('id="history-clear-btn"')
    # 矢印は飾り（読み上げ・Tab の対象にしない）
    for i in ("hist-arrow-l", "hist-arrow-r"):
        tag = html[html.index(f'id="{i}"'):].split(">", 1)[0]
        assert 'aria-hidden="true"' in tag and 'tabindex="-1"' in tag


def test_hint_logic_and_css():
    js = _read("static", "js", "history.js")
    assert "function updateChipHints" in js and "function scrollChips" in js
    assert "getComputedStyle(c).direction === 'rtl'" in js            # 右から左の言語でも、見た目の左右で判断
    assert js.count("updateChipHints();") >= 1 and "scrollBy" in js
    css = _read("static", "style.css")
    assert ".hist-scroll.can-l .hist-arrow-l" in css and ".hist-chips.fade-r" in css and "mask-image" in css
    assert "scroll-padding-inline" in css                              # 選んだボタンが矢印の下に隠れない


def test_version_is_1_3_1():
    import app as appmod
    assert appmod.APP_VERSION.startswith(("1.3.1", "1.4", "1.5"))
