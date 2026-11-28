"""v1.12.0: オフラインで写真の文字を読み取って訳す（試作）。Tesseract.js 6.0.1 を端末内で動かし、読んだ文字をオフライン翻訳につなぐ。"""
import os
import re
import shutil
import subprocess

import pytest
from conftest import ROOT, start

LABELS = ["ocr_row", "ocr_intro", "ocr_photo_btn", "ocr_reading", "ocr_need", "ocr_empty", "ocr_err", "ocr_unsupported", "ocr_state_none"]
PACKS = ["ja", "zh", "ko", "es", "fr", "de", "it", "ru", "id"]


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def test_version():
    import app as appmod
    assert tuple(int(x) for x in appmod.APP_VERSION.split(".")) >= (1, 12, 0)


def test_labels_ja_en_and_fallback():
    import labels_en
    import labels_ja
    for k in LABELS:
        assert labels_ja.LABELS[k].strip() and labels_en.LABELS[k].strip(), k
    assert "{l}" in labels_ja.LABELS["ocr_need"] and "{l}" in labels_en.LABELS["ocr_need"]


def test_engine_is_pinned_and_data_comes_from_the_npm_data_packages():
    js = _read("static", "js", "offline_ocr.js")
    assert "tesseract.js@6.0.1/dist/tesseract.min.js" in js and "@tesseract.js-data/" in js and "4.0.0_best_int" in js
    assert "innerHTML" not in js
    for f in ("offline_ocr", "offline_ocr_ui", "offline_photo"):
        assert len(_read("static", "js", f + ".js").splitlines()) <= 200, f


def test_service_worker_stores_the_ocr_engine_and_data():
    js = _read("templates", "sw.js")
    for p in ("'/npm/tesseract.js@'", "'/npm/tesseract.js-core@'", "'/npm/@tesseract.js-data/'"):
        assert p in js, p
    assert js.lower().count("cdn") == 1           # 外部の名前は、1か所だけ（OMT_HOST）


def test_scripts_are_in_order_on_both_pages():
    for tpl in (("templates", "components", "scripts.html"), ("templates", "offline.html")):
        order = re.findall(r"js/([a-z_0-9]+)\.js", _read(*tpl))
        assert order.index("offline_ocr") < order.index("offline_mt") and order.index("offline_mt") + 1 == order.index("offline_mt_ui")
        assert order.index("offline_mt_ui") < order.index("offline_ocr_ui") < order.index("pwa"), tpl
    off = re.findall(r"js/([a-z_0-9]+)\.js", _read("templates", "offline.html"))
    assert off.index("offline_mt_tab") < off.index("offline_photo") < off.index("pwa")
    assert "offline_photo" not in _read("templates", "components", "scripts.html")      # 写真から訳すのは、オフライン画面だけ


def test_settings_have_an_ocr_row_in_every_pack_and_the_offline_screen_has_the_photo_button(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    for pk in PACKS:
        pack = html.split(f'data-pack="{pk}"', 1)[1].split('data-pack=', 1)[0]
        assert f'data-ocr-pack="{pk}"' in pack, pk
    assert html.count('class="ocr-row ') == 9 and 'id="ocr-err"' in html and "写真の文字認識" in html
    off = c.get("/offline").get_data(as_text=True)
    assert 'id="omt-photo"' in off and 'accept="image/*"' in off and 'id="omt-photo-msg"' in off and "写真から読み取る" in off
    assert 'id="omt-photo"' not in html


def _ocr(expr):
    src = os.path.join(ROOT, "static", "js", "offline_ocr.js")
    code = "const O=new Function(require('fs').readFileSync(%r,'utf8')+';return OfflineOCR;')();console.log(JSON.stringify(%s))" % (src, expr)
    return subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout.strip()


@pytest.mark.skipif(shutil.which("node") is None, reason="node がない")
def test_every_offline_language_has_ocr_data_and_every_pack_lists_english_too():
    out = _ocr("[Object.keys(O.CODE).length, O.codeFor('Japanese'), O.codeFor('Chinese (Traditional)'), O.codeFor('Klingon'), Object.keys(O.PACK).join(','), Object.values(O.PACK).every(a => a.indexOf('eng') >= 0)]")
    assert out == '[11,"jpn","chi_tra","","ja,zh,ko,es,fr,de,it,ru,id",true]'
    names = re.findall(r"'([A-Za-z() ]+)': \{ code:", _read("static", "js", "offline_text.js"))
    assert sorted(names) == sorted(_ocr("Object.keys(O.CODE)").strip("[]").replace('"', "").split(","))


@pytest.mark.skipif(shutil.which("node") is None, reason="node がない")
def test_clean_removes_gaps_between_cjk_characters_but_keeps_word_spaces():
    out = _ocr(r"[O.clean('駅 は ど こ で す か ？\n\n  Hello  world \r\n한국어 문장'), O.clean(''), O.clean(null)]")
    assert out == '["駅はどこですか？\\nHello  world\\n한국어 문장","",""]'
