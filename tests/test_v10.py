"""V10: 文言・favicon・設定へのデータ統合"""
import re

import os

from conftest import ROOT, start


def test_image_tab_wording_mentions_pdf(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    assert "画像・PDFを翻訳する" in html and "画像またはPDFを選択" in html
    assert "画像を翻訳する" not in html


def test_favicon(env):
    app, *_ = env
    c = app.test_client()
    r = c.get("/favicon.ico")
    assert r.status_code == 200 and r.mimetype == "image/png" and r.data.startswith(b"\x89PNG")
    start(c)
    assert 'rel="icon"' in c.get("/").get_data(as_text=True)
    assert 'rel="icon"' in c.get("/start").get_data(as_text=True)


def test_data_lives_inside_settings_on_main(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    assert 'id="hf-data"' not in html                                          # 「データ」ボタンは無い（設定の中にある）
    for pill in ("hf-settings", "hf-all", "hf-fav", "hf-gl", "hf-phrases", "hf-study"):
        assert f'id="{pill}"' in html, pill
    s = html.index('id="settings-section"')
    e = html.index('id="glossary-section"')
    block = html[s:e]
    for needle in ('id="data-section"', "exportBackup()", "importBackup(this)", "deleteAllData()", 'id="set-pron"', 'data-setting="theme"'):
        assert needle in block, needle
    # データ欄は設定の中で常に表示（hidden ではない）
    assert not re.search(r'id="data-section" class="[^"]*hidden', html)


def test_offline_page_has_a_settings_pill(env):
    app, *_ = env
    c = app.test_client()
    off = c.get("/offline").get_data(as_text=True)
    assert 'id="hf-settings"' in off and 'id="data-section"' in off and 'id="hf-data"' not in off


def test_vocab_counts_in_backup_labels():
    import languages
    for lang in ("Japanese", "English"):
        L = languages.UI_LABELS[lang]
        for k in ("data_counts_v", "import_confirm_v", "import_done_v"):
            assert "{v}" in L[k], (lang, k)
        assert L["btn_file_translate"] and L["file_input_label"]
        assert L["set_group_translate"] and L["set_group_display"]


def test_settings_tab_chips_order_and_default(env):
    """v1.1: 設定タブの中の並びは、設定 → 履歴 → お気に入り → ... 。最初に見せるのは設定"""
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    ids = [html.index(f'id="{p}"') for p in ("hf-settings", "hf-all", "hf-fav", "hf-gl")]
    assert ids == sorted(ids)
    chip = html[html.index('id="hf-all"'):]
    assert "履歴" in chip[:chip.index("</button>")] and "すべて" not in chip[:chip.index("</button>")]
    js = open(os.path.join(ROOT, "static", "js", "history.js"), encoding="utf-8").read()
    assert "let histFilter = 'settings'" in js
    assert "openSettings" not in open(os.path.join(ROOT, "static", "js", "settings.js"), encoding="utf-8").read()
