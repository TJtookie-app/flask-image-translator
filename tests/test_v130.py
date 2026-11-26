"""v1.3: 見た目の整え（設定タブのボタン列を1行に・下のナビ／ヘッダーが狭い画面で重ならない）"""
import os
import re

from conftest import ROOT, start


def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def test_settings_tab_chips_are_one_scrolling_row(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    assert 'class="hist-bar"' in html and 'id="hist-chips"' in html
    row = html[html.index('id="hist-chips"'):]
    row = row[:row.index('id="hist-arrow-r"')]
    chips = re.findall(r'<button type="button" id="hf-(\w+)"', row)
    assert chips[:4] == ["settings", "all", "fav", "gl"] and chips[-1] == "trash" and "study" in chips
    assert row.count('class="hist-chip ') == len(chips)                       # 全部が、折り返さないボタンの部品
    assert "flex-wrap" not in row                                             # Tailwind の折り返し指定は、もう無い
    # 「履歴を消去」は、ボタン列の外（下の行）にある
    assert html.index('id="history-clear-btn"') < html.index('id="hf-trash"')   # v1.7.2: 「履歴を消去」は、上のタイトル行へ移った
    css = _read("static", "style.css")
    rule = css.split(".hist-chips {", 1)[1].split("}", 1)[0]
    assert "flex-wrap: nowrap" in rule and "overflow-x: auto" in rule


def test_active_chip_keeps_its_class_and_scrolls_into_view():
    js = _read("static", "js", "history.js")
    assert "'hist-chip px-3 py-1.5" in js                                     # 選び直しても、クラスが消えない
    assert "scrollIntoView({ block: 'nearest', inline: 'nearest' })" in js     # 縦のスクロールは動かさない


def test_nav_labels_and_header_fit_narrow_screens():
    css = _read("static", "style.css")
    nav = css.split("下のナビの文字", 1)[1]
    assert "clamp(9px, 2.7vw, 11px)" in nav and "html[data-fs=xl] .bottom-nav .nav-btn span" in nav
    assert "text-overflow: ellipsis" in nav
    assert re.search(r"@media \(max-width: 349px\) \{ \.hdr-brand > div > span:nth-child\(2\) \{ display: none; \} \}", css)
