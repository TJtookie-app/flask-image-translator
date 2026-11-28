"""v1.11.2: オフライン翻訳に、スペイン語・フランス語・ドイツ語・イタリア語・ロシア語・インドネシア語を追加（英語との両方向、言語パック）。"""
import os
import subprocess

from conftest import ROOT, start

NEW = ["es", "fr", "de", "it", "ru", "id"]


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def test_version():
    import app as appmod
    assert tuple(int(x) for x in appmod.APP_VERSION.split(".")) >= (1, 11, 2)


def test_labels_for_every_new_pair_in_ja_and_en():
    import labels_en
    import labels_ja
    for c in NEW:
        for k in (f"omt_pack_{c}", f"omt_{c}_en", f"omt_en_{c}", f"omt_run_{c}_en", f"omt_run_en_{c}"):
            assert labels_ja.LABELS[k].strip() and labels_en.LABELS[k].strip(), k


def test_models_are_the_xenova_opus_mt_pairs_in_worker_and_main_thread():
    for f in ("offline_mt_worker.js", "offline_mt.js"):
        js = _read("static", "js", f)
        assert "['es', 'fr', 'de', 'it', 'ru', 'id']" in js and "Xenova/opus-mt-' + c + '-en'" in js and "'Xenova/opus-mt-en-' + c" in js, f


def test_settings_have_a_pack_for_each_new_language_and_hide_run_buttons_until_ready(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    for lang in NEW:
        assert f'data-pack="{lang}"' in html and f'data-pair="{lang}-en"' in html and f'data-pair="en-{lang}"' in html, lang
        assert f'data-omt-run="{lang}-en" data-pack="{lang}"' in html and f'data-omt-run="en-{lang}" data-pack="{lang}"' in html
    sel = html.split('id="omt-add-sel"')[1].split("</select>")[0]
    for lang in NEW + ["zh", "ko"]:
        assert f'value="{lang}"' in sel, lang
    assert html.count('data-auto="1"') == 2          # 自動ダウンロードは、日本語⇄英語だけ
    off = c.get("/offline").get_data(as_text=True)
    bar = off.split('id="omt-tab-bar"')[1].split('id="omt-tab-in"')[0]
    for name in ("Spanish", "French", "German", "Italian", "Russian", "Indonesian"):
        assert f'<option value="{name}">' in bar, name


def _node(expr):
    code = ("const fs=require('fs');const src=fs.readFileSync(%r,'utf8');"
            "global.document={addEventListener(){},getElementById(){return null;}};"
            "const O=new Function('tmFind','UI','OfflineMT', src.split('// ---- 通常の画面')[0]+';return OfflineText;')(()=>null,{},undefined);"
            "console.log(JSON.stringify(%s))") % (os.path.join(ROOT, "static", "js", "offline_text.js"), expr)
    return subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout.strip()


def test_routes_through_english_and_latin_text_keeps_the_chosen_language():
    out = _node("[O.route('Japanese','Spanish').map(s=>s.pair), O.route('Spanish','English').map(s=>s.pair), O.route('Russian','Korean'), O.route('French','German').map(s=>s.pair),"
                "O.detect('Hola','', 'Spanish'), O.detect('Hello','', undefined), O.detect('Bonjour','', 'Chinese (Simplified)'), O.detect('Привет'), O.detect('こんにちは','', 'Spanish')]")
    assert out == '[["ja-en","en-es"],["es-en"],null,["fr-en","en-de"],"Spanish","English","English","Russian","Japanese"]'
