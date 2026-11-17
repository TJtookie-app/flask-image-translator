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


def test_bar_has_six_tabs_and_no_money(env):
    html = page(env)
    bar = html[html.index('id="bottom-nav"'):]
    bar = bar[:bar.index("</nav>")]
    assert len(re.findall(r'id="nav-', bar)) == 6 and 'id="nav-money"' not in bar
    for t in ("text", "image", "voice", "camera", "conversation", "history"):
        assert f"id=\"nav-{t}\"" in bar
    assert "プライバシー" not in bar                                   # リンクはバーの外（本文の末尾）
    assert html.index("プライバシー") < html.index('id="bottom-nav"')
    assert 'class="has-bottom-nav' in html


def test_money_button_is_in_header_before_language_button(env):
    html = page(env)
    head = html[:html.index('id="language-bar-wrapper"')]
    assert 'id="nav-money"' in head and 'fa-coins' in head
    assert head.index('id="nav-money"') < head.index('href="/start"') < head.index('id="open-settings"')
    btn = head[head.index('id="nav-money"'):]; btn = btn[:btn.index("</button>")]
    assert re.sub(r"<[^>]+>", "", btn.split(">", 1)[1]).strip() == ""   # 文字なし（アイコンだけ）
    assert 'aria-label="通貨"' in btn and 'title="通貨"' in btn
    assert 'aria-label="Money"' in page(env, "English")


def test_css_fixed_bar_rules():
    css = read("static", "style.css")
    assert re.search(r"\.bottom-nav \{[^}]*position: fixed[^}]*bottom: 0", css, re.S)
    assert "env(safe-area-inset-bottom" in css.split(".bottom-nav {", 1)[1].split("}", 1)[0]
    assert "body.has-bottom-nav" in css and "body.kb-open .bottom-nav { display: none; }" in css
    assert "--nav-h" in css and ".hdr-money.on" in css and "max-width: 359px" in css
    # 通貨の見えない select は、Tailwind がなくても位置が決まる
    assert re.search(r"\.money-popup \{[^}]*position: absolute", css)


def test_switch_tab_and_keyboard_hook():
    js = read("static", "js", "app.js")
    assert "classList.toggle('on'" in js and "aria-pressed" in js
    assert "kb-open" in js and "pointer: coarse" in js and "focusin" in js


def test_other_pages_have_no_bar(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    for path in ("/privacy", "/offline"):
        assert 'id="bottom-nav"' not in c.get(path).get_data(as_text=True)
