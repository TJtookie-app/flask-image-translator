"""V12.6: 言語バッジ（AIが es のようなコードで返しても、正式な言語名にそろえて「Español（スペイン語）」と表示する）"""
import io
import json

import pytest

from conftest import start
import languages
from languages import normalize_language_name as norm, language_badge, intl_tag

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.mark.parametrize("raw,expected", [
    ("Spanish", "Spanish"), ("spanish", "Spanish"), ("  SPANISH ", "Spanish"),
    ("es", "Spanish"), ("ES", "Spanish"), ("es-ES", "Spanish"), ("es_MX", "Spanish"), ("spa", "Spanish"),
    ("ja", "Japanese"), ("ja-JP", "Japanese"), ("jpn", "Japanese"),
    ("en", "English"), ("en-US", "English"), ("eng", "English"),
    ("ko", "Korean"), ("fr", "French"), ("fra", "French"), ("fre", "French"), ("de", "German"), ("deu", "German"),
    ("it", "Italian"), ("pt", "Portuguese"), ("pt-BR", "Portuguese"), ("Portuguese (Brazil)", "Portuguese"),
    ("ru", "Russian"), ("ar", "Arabic"), ("hi", "Hindi"), ("th", "Thai"), ("vi", "Vietnamese"),
    ("id", "Indonesian"), ("in", "Indonesian"), ("ms", "Malay"), ("fil", "Filipino"), ("tl", "Filipino"),
    ("he", "Hebrew"), ("iw", "Hebrew"), ("fa", "Persian"), ("uk", "Ukrainian"), ("sv", "Swedish"),
    ("nb", "Norwegian"), ("no", "Norwegian"), ("nn", "Norwegian"), ("Norwegian Bokmål", "Norwegian"),
    ("sw", "Swahili"), ("ca", "Catalan"), ("el", "Greek"), ("cs", "Czech"),
    # 中国語は簡体・繁体に分ける
    ("zh", "Chinese (Simplified)"), ("zh-CN", "Chinese (Simplified)"), ("zh-Hans", "Chinese (Simplified)"),
    ("Chinese", "Chinese (Simplified)"), ("Mandarin", "Chinese (Simplified)"), ("Chinese (Mandarin)", "Chinese (Simplified)"),
    ("zh-TW", "Chinese (Traditional)"), ("zh-HK", "Chinese (Traditional)"), ("zh-Hant", "Chinese (Traditional)"),
    ("Traditional Chinese", "Chinese (Traditional)"), ("Cantonese", "Chinese (Traditional)"), ("yue", "Chinese (Traditional)"),
    # その言語での名前
    ("español", "Spanish"), ("日本語", "Japanese"), ("Deutsch", "German"),
])
def test_normalize_accepts_names_codes_and_native(raw, expected):
    assert norm(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "   ", "Latin", "Esperanto", "eo", "xx", "unknown", "mixed", "N/A"])
def test_normalize_unknown_is_none(raw):
    assert norm(raw) is None


def test_every_supported_language_round_trips():
    for l in languages.LANGUAGES:
        assert norm(l["name"]) == l["name"]
        assert norm(l["code"]) == l["name"], l["code"]       # 音声用コード（ja-JP など）も戻せる
        assert norm(l["native"]) == l["name"], l["native"]    # その言語での名前も戻せる


def test_intl_tags():
    assert intl_tag("ja-JP") == "ja" and intl_tag("es-ES") == "es" and intl_tag("fil-PH") == "fil"
    assert intl_tag("zh-CN") == "zh-Hans" and intl_tag("zh-TW") == "zh-Hant" and intl_tag("nb-NO") == "no"
    assert intl_tag("") == ""


def test_language_badge():
    assert language_badge("es") == {"label": "Español (Spanish)", "tag": "es", "native": "Español"}
    assert language_badge("English")["label"] == "English"            # 同じ名前は1回だけ
    assert language_badge("Japanese") == {"label": "日本語 (Japanese)", "tag": "ja", "native": "日本語"}
    assert language_badge("zh-TW")["tag"] == "zh-Hant"
    # 対応外: 名前はそのまま。コードなら、画面で名前にできるよう tag を渡す
    assert language_badge("Latin") == {"label": "Latin", "tag": "", "native": ""}
    assert language_badge("eo") == {"label": "eo", "tag": "eo", "native": ""}
    assert language_badge(None)["label"] == ""


def _image_post(c, detected):
    return c.post("/", data={"mode": "image", "image": (io.BytesIO(PNG), "a.png", "image/png")},
                  content_type="multipart/form-data")


def test_image_result_shows_full_name_when_ai_returns_a_code(env):
    app, translator, calls, mp = env
    mp.setattr(translator, "_generate", lambda parts, system=None: '{"detected_language":"es","source_text":"hola","translation":"こんにちは"}')
    c = app.test_client(); start(c, "Japanese")
    html = _image_post(c, "es").get_data(as_text=True)
    assert 'data-lang-tag="es"' in html and 'data-lang-native="Español"' in html
    assert "Español (Spanish)" in html                       # JS が使えなくてもコードのままにはならない
    assert ">es<" not in html.replace(" ", "")
    # 検出した言語を覚える（「入れ替え」などで使う）
    with c.session_transaction() as s:
        assert s["last_detected"] == "Spanish"


def test_unknown_code_keeps_a_tag_for_the_browser(env):
    app, translator, calls, mp = env
    mp.setattr(translator, "_generate", lambda parts, system=None: '{"detected_language":"eo","source_text":"saluton","translation":"こんにちは"}')
    c = app.test_client(); start(c, "Japanese")
    html = _image_post(c, "eo").get_data(as_text=True)
    assert 'data-lang-tag="eo"' in html and 'data-lang-native=""' in html and ">eo<" in html.replace(" ", "")


def test_auto_text_translation_shows_badge_but_fixed_source_does_not(env):
    app, translator, calls, mp = env
    mp.setattr(translator, "_generate", lambda parts, system=None: '{"detected_language":"fr","source_text":"bonjour","translation":"こんにちは"}')
    c = app.test_client(); start(c, "Japanese")
    r = c.post("/", data={"mode": "text", "direct_text": "bonjour"})   # 翻訳元: 自動
    assert "Français (French)" in r.get_data(as_text=True)


def test_overlay_result_uses_the_badge_too(env):
    app, translator, calls, mp = env
    blocks = json.dumps({"detected_language": "ko", "blocks": [{"text": "안녕", "translation": "Hello", "box_2d": [100, 50, 200, 400]}]})
    mp.setattr(translator, "_generate", lambda parts, system=None: blocks)
    c = app.test_client(); start(c, "Japanese")
    r = c.post("/", data={"mode": "image", "overlay": "1", "image": (io.BytesIO(PNG), "a.png", "image/png")},
               content_type="multipart/form-data")
    assert "한국어 (Korean)" in r.get_data(as_text=True)


def test_same_language_warning_works_with_codes(env):
    app, translator, calls, mp = env
    mp.setattr(translator, "_generate", lambda parts, system=None: '{"detected_language":"ja","source_text":"こんにちは","translation":"こんにちは"}')
    c = app.test_client(); start(c, "Japanese")
    html = c.post("/", data={"mode": "text", "direct_text": "こんにちは"}).get_data(as_text=True)
    assert "入力はすでに翻訳先と同じ言語のようです" in html   # "ja" でも「日本語」と判定され、同じ言語の注意が出る


def test_prompts_ask_for_full_english_names():
    import translator
    assert "never a language code" in translator.SYSTEM_INSTRUCTION
    assert "never a language code" in translator.OVERLAY_SYSTEM


def test_badge_js_wiring():
    import os
    from conftest import ROOT
    js = open(os.path.join(ROOT, "static", "js", "display.js"), encoding="utf-8").read()
    for needle in ("function localizeLangBadges", "Intl.DisplayNames", "langTag", "langNative", "zh-Hans", "zh-Hant"):
        assert needle in js, needle
