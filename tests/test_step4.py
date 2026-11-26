"""ステップ4: 丁寧さ・読み方・別の言い方・同じ言語の警告・設定"""
import json
import os

import pytest

from conftest import start

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _prompt(calls):
    return calls[-1][0][0]


def test_formality_and_pron_in_prompt(env):
    app, translator, calls, _ = env
    translator.translate_text("hi", "English", "Japanese", formality="formal", pronunciation=True)
    p = _prompt(calls)
    assert "polite, formal" in p and "romanized reading" in p
    translator.translate_text("hi", "English", "Japanese", formality="business")
    p = _prompt(calls)
    assert "business" in p.lower() and "romanized" not in p
    translator.translate_text("hi", "English", "Japanese", formality="auto")
    assert "register" not in _prompt(calls)


def test_clean_formality(env):
    _, translator, _, _ = env
    assert translator.clean_formality("formal") == "formal"
    assert translator.clean_formality("<script>") == "auto"
    assert translator.clean_formality(None) == "auto"


def test_parse_pronunciation(env):
    _, translator, _, _ = env
    r = translator._parse('{"detected_language":"English","source_text":"a","translation":"こんにちは","pronunciation":"konnichiwa"}')
    assert r["pronunciation"] == "konnichiwa"
    assert translator._parse("plain text")["pronunciation"] == ""


def test_index_post_passes_options_and_shows_reading(env):
    app, translator, calls, mp = env
    mp.setattr(translator, "_generate", lambda parts, system=None: (calls.append((parts, system)) or
        '{"detected_language":"English","source_text":"hello","translation":"こんにちは","pronunciation":"konnichiwa"}'))
    c = app.test_client()
    start(c, "Japanese")
    r = c.post("/", data={"mode": "text", "direct_text": "hello", "formality": "formal", "pron": "1"})
    html = r.get_data(as_text=True)
    assert "konnichiwa" in html and 'id="pron-text"' in html
    assert "polite, formal" in _prompt(calls) and "romanized reading" in _prompt(calls)
    # 不正値は無視される
    c.post("/", data={"mode": "text", "direct_text": "hello", "formality": "evil", "pron": "0"})
    assert "romanized" not in _prompt(calls) and "evil" not in _prompt(calls)


def test_api_translate_text_options(env):
    app, translator, calls, mp = env
    mp.setattr(translator, "_generate", lambda parts, system=None: (calls.append((parts, system)) or
        '{"detected_language":"English","source_text":"hi","translation":"やあ","pronunciation":"yaa"}'))
    c = app.test_client()
    start(c)
    r = c.post("/api/translate-text", json={"text": "hi", "source": "English", "target": "Japanese", "formality": "business", "pron": True})
    assert r.status_code == 200 and r.get_json()["pronunciation"] == "yaa"
    assert "business" in _prompt(calls).lower()


def test_alternatives_api(env):
    app, translator, calls, mp = env
    mp.setattr(translator, "_generate", lambda parts, system=None: (calls.append((parts, system)) or
        '{"alternatives":["Hi there","Hello","Hello","Hey"]}'))
    c = app.test_client()
    start(c)
    r = c.post("/api/alternatives", json={"text": "こんにちは", "translation": "Hello", "source": "Japanese", "target": "English"})
    assert r.status_code == 200
    # 今の訳と同じもの・重複は除く
    assert r.get_json()["alternatives"] == ["Hi there", "Hey"]
    assert "Hello" in _prompt(calls)


def test_alternatives_validation(env):
    app, translator, calls, mp = env
    c = app.test_client()
    start(c)
    assert c.post("/api/alternatives", json={"text": "", "translation": "x", "target": "English"}).status_code == 400
    assert c.post("/api/alternatives", json={"text": "a", "translation": "b", "target": "Klingon"}).status_code == 400
    assert not calls   # APIは呼ばれない
    mp.setattr(translator, "_generate", lambda parts, system=None: "not json")
    assert c.post("/api/alternatives", json={"text": "a", "translation": "b", "target": "English"}).status_code == 502


def test_alternatives_counts_toward_limits(env):
    app, translator, calls, mp = env
    from limits import limiter
    mp.setattr(limiter, "check", lambda ip: "err_rate")
    c = app.test_client()
    start(c)
    assert c.post("/api/alternatives", json={"text": "a", "translation": "b", "target": "English"}).status_code == 429


def test_same_language_warning(env):
    app, translator, calls, _ = env
    c = app.test_client()
    start(c, "Japanese")
    with c.session_transaction() as s:
        s["source_lang"], s["target_lang"] = "Japanese", "Japanese"
    assert 'id="same-lang-warning"' in c.get("/").get_data(as_text=True)
    with c.session_transaction() as s:
        s["source_lang"], s["target_lang"] = "English", "Japanese"
    assert 'id="same-lang-warning"' not in c.get("/").get_data(as_text=True)
    with c.session_transaction() as s:
        s["source_lang"], s["target_lang"] = "Auto", "Japanese"
    assert 'id="same-lang-warning"' not in c.get("/").get_data(as_text=True)


def test_detected_same_as_target_note(env):
    app, translator, calls, mp = env
    mp.setattr(translator, "_generate", lambda parts, system=None:
        '{"detected_language":"Japanese","source_text":"こんにちは","translation":"こんにちは","pronunciation":""}')
    c = app.test_client()
    start(c, "Japanese")   # From=Auto / To=Japanese
    html = c.post("/", data={"mode": "text", "direct_text": "こんにちは"}).get_data(as_text=True)
    assert "role=\"status\"" in html and "すでに翻訳先と同じ言語" in html


def test_ui_has_step4_controls_and_assets(env):
    app, *_ = env
    c = app.test_client()
    start(c, "English")
    html = c.get("/").get_data(as_text=True)
    for needle in ("settings-section", "set-pron", "js/settings.js", "js/display.js", "tl_settings_v1", 'name="formality"', "conv-warn"):
        assert needle in html, needle
    off = c.get("/offline").get_data(as_text=True)
    assert "settings-section" in off and "js/settings.js" in off
    sw = c.get("/sw.js").get_data(as_text=True)
    assert "js/settings.js" in sw and "js/display.js" in sw


def test_step4_labels_exist_in_both_languages():
    import languages
    keys = ["filter_settings", "set_formality", "set_pron", "set_fontsize", "set_theme", "big_show", "big_close",
            "alts_btn", "alts_label", "pron_label", "warn_same_lang", "warn_detected_same", "warn_same_chat"]
    for lang in ("Japanese", "English"):
        for k in keys:
            assert languages.UI_LABELS[lang].get(k), (lang, k)


def test_header_has_no_gear_and_nav_ends_with_settings(env):
    """v1.1: 右上の歯車は無い。設定は、下のナビの右端（歯車アイコン）のタブの中"""
    app, *_ = env
    c = app.test_client()
    start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    head = html[:html.index('id="language-bar-wrapper"')]
    assert 'id="open-settings"' not in html and "openSettings" not in html and "fa-gear" not in head
    nav = html[html.index('id="bottom-nav"'):]
    nav = nav[:nav.index("</nav>")]
    assert nav.rindex('id="nav-history"') > nav.index('id="nav-money"')                 # 右端は今までどおり
    last = nav[nav.index('id="nav-history"'):]
    assert "fa-gear" in last and "設定" in last and "履歴" not in last and "fa-clock-rotate-left" not in last
