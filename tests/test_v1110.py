"""v1.11.0: 圏外の翻訳に、中国語・韓国語を追加（英語を軸にしたモデル。他の言語どうしは英語を経由）。言語のバーは、選べる形。"""
import os
import re

from conftest import ROOT, start

LABELS = ["omt_zh_en", "omt_en_zh", "omt_ko_en", "omt_run_zh_en", "omt_run_en_zh", "omt_run_ko_en", "ot_missing", "lo_via_pivot"]
PAIRS = ["ja-en", "en-ja", "zh-en", "en-zh", "ko-en"]


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def test_version():
    import app as appmod
    assert tuple(int(x) for x in appmod.APP_VERSION.split(".")) >= (1, 11, 0)


def test_labels_ja_en_and_fallback():
    import labels_en
    import labels_ja
    for k in LABELS:
        assert labels_ja.LABELS[k].strip() and labels_en.LABELS[k].strip(), k
    assert "{m}" in labels_ja.LABELS["ot_missing"] and "{m}" in labels_en.LABELS["ot_missing"]
    from ui_i18n import get_ui_labels
    assert get_ui_labels("Thai")["omt_zh_en"] == labels_en.LABELS["omt_zh_en"]


def test_models_are_the_agreed_xenova_ones_in_both_the_worker_and_the_page():
    expected = {"ja-en": "Xenova/opus-mt-ja-en", "en-ja": "Xenova/opus-mt-en-jap", "zh-en": "Xenova/opus-mt-zh-en",
                "en-zh": "Xenova/opus-mt-en-zh", "ko-en": "Xenova/opus-mt-ko-en"}
    for f in ("offline_mt_worker", "offline_mt"):
        js = _read("static", "js", f + ".js")
        for pair, model in expected.items():
            assert f"'{pair}': '{model}'" in js, (f, pair)
    assert "Xenova/opus-mt-en-ko" not in _read("static", "js", "offline_mt_worker.js")      # 英語→韓国語は、使えるモデルが見つかっていない


def test_worker_prefixes_the_chinese_script_marker_and_keeps_one_model():
    w = _read("static", "js", "offline_mt_worker.js")
    assert "pipe(pre + s.trim()" in w and "prefix + ' '" in w
    assert "releaseOthers" in w and ".dispose" in w
    t = _read("static", "js", "offline_text.js")
    assert "'>>cmn_Hans<<'" in t and "'>>cmn_Hant<<'" in t


def test_route_table_in_the_page_script():
    """offline_text.js の route() は、英語を軸にする。ブラウザなしでも確かめられるよう、node があれば実行する。"""
    import shutil
    import subprocess
    if not shutil.which("node"):
        return
    code = ("global.document={addEventListener(){}};global.UI={};global.tmFind=()=>null;"
            "(0,eval)(require('fs').readFileSync(%r,'utf8')+';globalThis.OT=OfflineText;');"
            "const r=(a,b)=>{const x=OT.route(a,b);return x?x.map(s=>s.pair+s.prefix).join('+'):null};"
            "console.log(JSON.stringify([r('Japanese','English'),r('English','Japanese'),r('Japanese','Chinese (Simplified)'),"
            "r('Korean','Japanese'),r('Japanese','Korean'),r('English','Korean'),r('Chinese (Simplified)','Chinese (Traditional)'),"
            "r('Chinese (Traditional)','Japanese'),r('English','Chinese (Traditional)'),r('Japanese','Japanese')]))" % os.path.join(ROOT, "static", "js", "offline_text.js"))
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == ('["ja-en","en-ja","ja-en+en-zh>>cmn_Hans<<","ko-en+en-ja",null,null,null,"zh-en+en-ja","en-zh>>cmn_Hant<<",null]')


def test_settings_card_and_offline_tab_render_the_five_directions(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    for p in PAIRS:
        assert f'data-pair="{p}"' in html and f'data-omt-run="{p}"' in html, p
    assert html.count('data-auto="1"') == 2 and 'data-pair="ja-en" data-auto="1"' in html and 'data-pair="en-ja" data-auto="1"' in html
    off = c.get("/offline").get_data(as_text=True)
    bar = off.split('id="omt-tab-bar"')[1].split('id="omt-tab-in"')[0]
    assert bar.count("<option") == 10 and '<select id="omt-tab-from"' in bar and '<select id="omt-tab-to"' in bar
    for name in ("Japanese", "English", "Chinese (Simplified)", "Chinese (Traditional)", "Korean"):
        assert f'<option value="{name}">' in bar, name
    assert 'id="omt-tab-missing"' in off


def test_auto_download_still_only_the_two_main_directions():
    js = _read("static", "js", "offline_mt_ui.js")
    assert "!r.dataset.auto" in js


def test_js_files_stay_short_and_have_no_innerhtml():
    for n in ("offline_text", "offline_mt_tab", "offline_mt_ui", "offline_mt", "offline_mt_worker"):
        js = _read("static", "js", n + ".js")
        assert len(js.splitlines()) <= 200, n
        assert "innerHTML" not in js, n
