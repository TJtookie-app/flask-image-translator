"""v1.10.1: オフライン画面のテキスト翻訳の言語バーを、オンラインの画面と同じ形（翻訳元 ⇄ 翻訳先）にする。"""
import os

from conftest import ROOT, start


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def test_version():
    import app as appmod
    assert tuple(int(x) for x in appmod.APP_VERSION.split(".")) >= (1, 10, 1)


def test_offline_tab_has_the_same_language_bar_as_the_online_screen(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    off = c.get("/offline").get_data(as_text=True)
    bar = off.split('id="omt-tab-bar"')[1].split('id="omt-tab-in"')[0]
    assert bar.index('id="omt-tab-from"') < bar.index('id="omt-tab-swap"') < bar.index('id="omt-tab-to"')
    assert "fa-arrow-right-arrow-left" in bar and ">From<" in bar and ">To<" in bar          # オンラインの画面と同じ言葉（ui.source_label / ui.target_label）
    assert 'data-dir=' not in off and 'id="omt-tab-dirs"' not in off          # 旧: 自動／日本語→英語／英語→日本語のボタン


def test_tab_js_follows_the_text_and_swaps():
    js = _read("static", "js", "offline_mt_tab.js")
    assert "omt-tab-swap" in js and "follow(" in js and len(js.splitlines()) <= 200
    assert "'auto'" not in js
