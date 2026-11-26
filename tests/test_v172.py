"""v1.7.2: 「翻訳する」ボタンと進捗バーは単色（アプリ全体でグラデーションなし）／どの画面も左上に同じ形のタイトル。"""
import os
import re

from conftest import ROOT, start


def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def test_version_is_1_7_2():
    import app as appmod
    assert appmod.APP_VERSION.startswith(("1.7.", "1.8."))


def test_no_color_gradients_left_in_theme_css():
    css = _read("static", "theme.css")
    assert "--grad-btn" not in css and "--grad-ring" not in css
    assert re.search(r'from-indigo-600"\]\s*\{\s*background-image: none; background-color: var\(--btn\)', css)
    assert re.search(r"\.pbar:not\(\.pbar-done\):not\(\.pbar-error\):not\(\.pbar-stopped\) \.pbar-fill \{ background: var\(--accent\)", css)


def test_title_row_sits_between_logo_and_language_bar(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    assert html.index("hdr-brand") < html.index('id="page-title"') < html.index('id="language-bar-wrapper"')
    for i in ("page-title-icon", "page-title-text", "page-title-act", "history-clear-btn"):
        assert f'id="{i}"' in html, i
    # 履歴を消去は、タイトル行の右端へ移った（設定の上のボタン列には、もう無い）
    assert html.index('id="page-title"') < html.index('id="history-clear-btn"') < html.index('id="language-bar-wrapper"')


def test_old_duplicate_headings_are_gone():
    assert "money_title" not in _read("templates", "components", "money_tab.html")
    assert "filter_settings" not in _read("templates", "components", "history_tab.html").split('id="settings-section"')[1].split("set_group_translate")[0]


def test_titles_use_existing_labels_only():
    js = _read("static", "js", "page_title.js")
    keys = set(re.findall(r"'((?:nav|filter)_\w+|money_title)'", js))
    assert keys == {"nav_text", "nav_image", "nav_voice", "nav_camera", "nav_conversation", "money_title", "filter_settings", "nav_history",
                    "filter_fav", "filter_glossary", "filter_phrases", "filter_study", "filter_trash"}
    from labels_ja import LABELS
    assert all(k in LABELS for k in keys)
    assert len(js.splitlines()) <= 200


def test_page_title_js_loads_after_motion_js(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    tags = re.findall(r'<script src="[^"]*/js/(\w+)\.js', html)
    assert tags.index("app") < tags.index("motion") < tags.index("page_title")


def test_initial_title_is_rendered_by_the_server(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    assert re.search(r'id="page-title-text"[^>]*>テキスト<', html)


def test_title_css_is_rtl_safe_and_scales():
    css = _read("static", "style.css")
    block = css[css.index("/* ---- v1.7.2"):]
    assert "text-overflow: ellipsis" in block and "min-width: 0" in block
    assert "margin-left" not in block and "padding-left" not in block and "text-align: left" not in block
    assert re.search(r"font-size: 1\.05rem", block)                          # 文字の大きさは rem（設定の文字サイズに合わせて大きくなる）
