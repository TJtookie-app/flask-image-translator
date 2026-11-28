"""v1.11.1: 設定の「オフライン翻訳」を言語パック方式に（ダウンロード済みの言語だけを並べ、「言語を追加」から足す）。"""
import os

from conftest import ROOT, start

KEYS = ["omt_pack_ja", "omt_pack_zh", "omt_pack_ko", "omt_add_title", "omt_add_ph", "omt_add_btn"]


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def test_version():
    import app as appmod
    assert tuple(int(x) for x in appmod.APP_VERSION.split(".")) >= (1, 11, 1)


def test_labels_ja_en():
    import labels_en
    import labels_ja
    for k in KEYS:
        assert labels_ja.LABELS[k].strip() and labels_en.LABELS[k].strip(), k


def test_template_has_packs_and_only_japanese_is_shown_first(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    assert html.count('class="omt-pack ') == 9   # v1.11.2: ja zh ko es fr de it ru id
    ja = html.split('data-pack="ja"')[0].rsplit("<div", 1)[1]
    assert "hidden" not in ja and 'data-base="1"' in html.split('data-pack="ja"')[1][:30]
    for pk in ("zh", "ko", "es", "id"):
        tag = html.split(f'data-pack="{pk}"')[0].rsplit("<div", 1)[1]
        assert " hidden" in tag, pk
    # 「言語を追加」: 選択欄には日本語を入れない
    sel = html.split('id="omt-add-sel"')[1].split("</select>")[0]
    assert 'value="zh"' in sel and 'value="ko"' in sel and 'value="id"' in sel and 'value="ja"' not in sel
    assert 'id="omt-add-btn"' in html and "言語を追加" in html
    # 各方向の行は、その言語パックの中にある
    zh = html.split('data-pack="zh"')[1].split('data-pack="ko"')[0]
    assert 'data-pair="zh-en"' in zh and 'data-pair="en-zh"' in zh and 'data-pair="ko-en"' not in zh
    for pk, pair in (("ja", "ja-en"), ("ja", "en-ja"), ("zh", "zh-en"), ("zh", "en-zh"), ("ko", "ko-en")):
        assert f'data-omt-run="{pair}" data-pack="{pk}"' in html, pair
    off = c.get("/offline").get_data(as_text=True)
    assert 'id="omt-add-btn"' in off


def test_js_logic_present_and_small():
    js = _read("static", "js", "offline_mt_ui.js")
    for needle in ("paintPacks", "addPack", "omt-add-sel", "added.delete"):
        assert needle in js, needle
    assert len(js.splitlines()) <= 200
    assert "innerHTML" not in js
