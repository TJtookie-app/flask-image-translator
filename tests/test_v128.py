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
    outer = css.split(".bottom-nav {", 1)[1].split("}", 1)[0]
    assert "position: fixed" in outer and "env(safe-area-inset-bottom" in outer and "pointer-events: none" in outer   # 外側は固定・何も受けない
    assert "translateZ(0)" in outer                                                  # 専用の層（スクロール中にずれない）
    inner = css.split(".bottom-nav-in {", 1)[1].split("}", 1)[0]
    assert "border-radius: 1.75rem" in inner and "pointer-events: auto" in inner and "backdrop-filter" in inner   # カプセル型
    assert "grid-auto-flow: column" in inner and "grid-auto-columns: minmax(0, 1fr)" in inner   # ボタンの数が変わっても均等
    assert "repeat(7" not in css                                                     # 列の数をCSSに固定しない（HTMLとずれると空きが出る）
    assert "body.has-bottom-nav" in css and "body.kb-open .bottom-nav { display: none; }" in css
    assert "--nav-h" in css and "--nav-gap" in css and "max-width: 379px" in css
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


def test_version_label_and_html_not_cached(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    r = c.get("/")
    assert r.headers["Cache-Control"] == "no-cache"          # 古いページと新しい CSS/JS が混ざらないように
    import app as appmod
    assert r.headers["X-App-Version"] == appmod.APP_VERSION
    html = r.get_data(as_text=True)
    assert 'id="app-version"' in html and f"TOOKIE V{appmod.APP_VERSION}" in html
    assert c.get("/api/quota").headers.get("Cache-Control") != "public"
