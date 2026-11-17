"""V12.8: 下のタブバーを固定・通貨ボタンをヘッダーへ（画面の部品の位置）"""
import os
import re

from conftest import start, ROOT


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def page(env, lang="Japanese"):
    app, *_ = env
    c = app.test_client(); start(c, lang)
    return c.get("/").get_data(as_text=True)


def test_bar_has_seven_tabs_history_rightmost_money_second_from_right(env):
    html = page(env)
    bar = html[html.index('id="bottom-nav"'):]
    bar = bar[:bar.index("</nav>")]
    order = re.findall(r'id="nav-(\w+)"', bar)
    assert order == ["text", "image", "voice", "camera", "conversation", "money", "history"]   # 履歴が一番右、通貨は右から2番目
    assert "プライバシー" not in bar                                   # リンクはバーの外（本文の末尾）
    assert html.index("プライバシー") < html.index('id="bottom-nav"')
    assert 'class="has-bottom-nav' in html


def test_header_has_no_money_button(env):
    html = page(env)
    head = html[:html.index('id="language-bar-wrapper"')]
    assert 'id="nav-money"' not in head and "fa-coins" not in head     # 通貨はヘッダーではなく下のバー
    assert head.index('href="/start"') < head.index('id="open-settings"')


def test_css_fixed_bar_rules():
    css = read("static", "style.css")
    assert re.search(r"\.bottom-nav \{[^}]*position: fixed[^}]*bottom: 0", css, re.S)
    assert "env(safe-area-inset-bottom" in css.split(".bottom-nav {", 1)[1].split("}", 1)[0]
    assert "body.has-bottom-nav" in css and "body.kb-open .bottom-nav { display: none; }" in css
    assert "--nav-h" in css and "repeat(7, minmax(0, 1fr))" in css and "max-width: 379px" in css
    assert ".hdr-money" not in css
    # 通貨の見えない select は、Tailwind がなくても位置が決まる
    assert re.search(r"\.money-popup \{[^}]*position: absolute", css)


def test_switch_tab_and_keyboard_hook():
    js = read("static", "js", "app.js")
    assert "kb-open" in js and "pointer: coarse" in js and "focusin" in js


def test_other_pages_have_no_bar(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    for path in ("/privacy", "/offline"):
        assert 'id="bottom-nav"' not in c.get(path).get_data(as_text=True)
