"""v1.4: 翻訳スタイル（7種）・ニュアンスと使い方の解説"""
import os
import re

import pytest

from conftest import ROOT, start

STYLES = ["auto", "natural", "literal", "formal", "business"]


def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def test_styles_reach_the_prompt(env):
    app, translator, calls, _ = env
    expect = {"natural": "natural everyday spoken", "literal": "as literally and faithfully", "business": "business register"}
    for k, needle in expect.items():
        translator.translate_text("hi", "English", "Japanese", formality=k)
        assert needle in calls[-1][0][0], k
    translator.translate_text("hi", "English", "Japanese", formality="auto")
    assert "register" not in calls[-1][0][0]


def test_styles_also_reach_alternatives_images_and_pdf(env):
    _, translator, _, _ = env
    for fn in ("alternative_translations", "translate_image_blocks", "translate_pdf_pages"):
        assert "FORMALITY_HINTS" in _read("translator.py")
    assert set(translator.FORMALITY_HINTS) == {"formal", "natural", "literal", "business"}


def test_clean_formality_accepts_only_known_styles(env):
    _, translator, _, _ = env
    for k in STYLES:
        assert translator.clean_formality(k) == k
    for bad in ("evil", "", None, "SLANG ", "<b>"):
        assert translator.clean_formality(bad) == "auto"


def test_style_is_sent_from_the_form_to_the_prompt(env):
    app, translator, calls, _ = env
    c = app.test_client(); start(c, "Japanese")
    c.post("/", data={"mode": "text", "direct_text": "hello", "formality": "literal", "pron": "0"})
    assert "as literally and faithfully" in calls[-1][0][0]
    c.post("/", data={"mode": "text", "direct_text": "hello", "formality": "slang", "pron": "0"})   # 削った設定が来ても、自動として扱う
    assert "register" not in calls[-1][0][0] and "slang" not in calls[-1][0][0]
    r = c.post("/api/translate-text", json={"text": "hi", "source": "English", "target": "Japanese", "formality": "business"})
    assert r.status_code == 200 and "business register" in calls[-1][0][0]


def test_settings_page_offers_five_styles_and_js_accepts_them(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    box = html[html.index('data-setting="formality"'):]
    box = box[:box.index("</div>")]
    assert re.findall(r'data-v="(\w+)"', box) == ["auto", "natural", "literal", "formal", "business"]
    for lab in ("自然な会話", "直訳", "ビジネス", "翻訳スタイル"):
        assert lab in html
    js = _read("static", "js", "settings.js")
    assert all(f"'{k}'" in js.split("SETTING_CHOICES")[1].split("\n")[0] for k in STYLES)


def test_old_saved_settings_still_valid():
    js = _read("static", "js", "settings.js")
    assert "formality: 'auto'" in js            # 既定は今まで通り「自動」


def test_new_labels_in_ja_and_en():
    import labels_en, labels_ja
    new = ["set_style", "formality_natural", "formality_literal", "formality_business", "explain_usage"]
    for k in new:
        assert labels_ja.LABELS[k].strip() and labels_en.LABELS[k].strip(), k


def test_explain_prompt_covers_usage_and_manners(env):
    _, translator, calls, _ = env
    import prompts
    p = prompts.explain_prompt("what's up", "English", "Japanese")
    for needle in ("situations", "rude", "friends, colleagues or superiors", "regional", "Japanese"):
        assert needle in p, needle
    assert "<text>\nwhat's up\n</text>" in p
    assert "explain_prompt(" in _read("assist.py")


def test_explain_menu_label_and_side(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    r = c.post("/", data={"mode": "text", "direct_text": "hello", "formality": "auto", "pron": "0"})
    assert "ニュアンス・使い方を解説" in r.get_data(as_text=True)
    js = _read("static", "js", "app.js")
    body = js.split("function explainResult")[1].split("}\n\nfunction")[0]
    assert "UI_LANG" in body and "RESULT.out, RESULT.tgt" in body        # 自分の言語で入力 → 訳文（相手に言う側）を解説
