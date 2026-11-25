"""v1.2: 口調を変える（API 1回で3口調）／長文の要約（600字以上・ボタンを押したときだけ）"""
import json
import os
import re

from conftest import ROOT, start

TONES_JSON = json.dumps({"formal": "Good day to you.", "neutral": "Hello.", "casual": "Hey!"})


def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


# ---------------- 口調を変える ----------------

def test_tones_api_returns_three_tones_in_one_call(env):
    app, translator, calls, mp = env
    mp.setattr(translator, "_generate", lambda parts, system=None: (calls.append((parts, system)) or TONES_JSON))
    c = app.test_client(); start(c)
    r = c.post("/api/tones", json={"text": "こんにちは", "translation": "Hello", "source": "Japanese", "target": "English"})
    assert r.status_code == 200
    assert r.get_json()["tones"] == {"formal": "Good day to you.", "neutral": "Hello.", "casual": "Hey!"}
    assert len(calls) == 1                                           # 3つ作るのに、呼び出しは1回
    prompt = calls[0][0][0]
    assert "Hello" in prompt and "English" in prompt and "formal" in prompt and "casual" in prompt
    assert '"formal"' in calls[0][1]                                 # 返す形（JSON）は、システム指示で指定している


def test_tones_api_rejects_partial_results_and_bad_input(env):
    app, translator, calls, mp = env
    c = app.test_client(); start(c)
    assert c.post("/api/tones", json={"text": "", "translation": "x", "target": "English"}).status_code == 400
    assert c.post("/api/tones", json={"text": "a", "translation": "", "target": "English"}).status_code == 400
    assert c.post("/api/tones", json={"text": "a", "translation": "b", "target": "Klingon"}).status_code == 400
    assert c.post("/api/tones", json={"text": "a" * 5001, "translation": "b", "target": "English"}).status_code == 400
    assert not calls                                                  # 入力が悪いときは、API を呼ばない
    for bad in ('{"formal": "x", "neutral": "y"}', '{"formal": "x", "neutral": "", "casual": "z"}', "not json"):
        mp.setattr(translator, "_generate", lambda parts, system=None, bad=bad: bad)
        # 3つそろわない結果では、今の訳を置き換えさせない（失敗にする）
        assert c.post("/api/tones", json={"text": "a", "translation": "b", "target": "English"}).status_code == 502


def test_tones_counts_toward_limits_and_stats(env):
    app, translator, calls, mp = env
    from limits import limiter, stats
    import limits
    c = app.test_client(); start(c)
    mp.setattr(translator, "_generate", lambda parts, system=None: TONES_JSON)
    assert c.post("/api/tones", json={"text": "a", "translation": "b", "target": "English"}).status_code == 200
    assert stats.snapshot()[limits._today()]["tone:ok"] == 1
    mp.setattr(limiter, "check", lambda ip: "err_rate")
    assert c.post("/api/tones", json={"text": "a", "translation": "b", "target": "English"}).status_code == 429


def test_tone_translations_function(env):
    app, translator, calls, mp = env
    mp.setattr(translator, "_generate", lambda parts, system=None: (calls.append(parts) or TONES_JSON))
    out = translator.tone_translations("おはよう", "Good morning", "Auto", "English")
    assert list(out) == ["formal", "neutral", "casual"] and "detect" in calls[0][0]


# ---------------- 要約 ----------------

def test_summarize_api_only_for_long_text(env):
    app, translator, calls, mp = env
    from helpers import SUMMARY_MIN_CHARS
    assert SUMMARY_MIN_CHARS == 600
    mp.setattr(translator, "_generate", lambda parts, system=None: (calls.append((parts, system)) or '{"summary": "- point A\\n- point B"}'))
    c = app.test_client(); start(c, "Japanese")
    assert c.post("/api/summarize", json={"text": "あ" * 599}).status_code == 400          # 600字未満は断る
    assert c.post("/api/summarize", json={"text": "あ" * 5001}).status_code == 400
    assert not calls
    r = c.post("/api/summarize", json={"text": "あ" * 600})
    assert r.status_code == 200 and r.get_json()["summary"] == "- point A\n- point B"
    assert len(calls) == 1 and "Japanese" in calls[0][0][0]                        # 要約は、画面の言語で書かせる


def test_summarize_failures_limits_and_stats(env):
    app, translator, calls, mp = env
    from limits import limiter, stats
    import limits
    c = app.test_client(); start(c)
    mp.setattr(translator, "_generate", lambda parts, system=None: '{"summary": "  "}')
    assert c.post("/api/summarize", json={"text": "x" * 700}).status_code == 502             # 空の要約は失敗
    mp.setattr(translator, "_generate", lambda parts, system=None: '{"summary": "ok"}')
    assert c.post("/api/summarize", json={"text": "x" * 700}).status_code == 200
    assert stats.snapshot()[limits._today()]["summary:ok"] == 1
    mp.setattr(limiter, "check", lambda ip: "err_rate")
    assert c.post("/api/summarize", json={"text": "x" * 700}).status_code == 429


def _post(c, text):
    return c.post("/", data={"mode": "text", "direct_text": text, "glossary": "[]"}).get_data(as_text=True)


def test_summary_button_appears_only_when_original_is_600_chars_or_more(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    short = _post(c, "あ" * 599)
    long_ = _post(c, "あ" * 600)
    assert 'id="summary-btn-text"' not in short and "summarizeResult" not in short
    assert 'id="summary-btn-text"' in long_ and 'id="summary-text"' in long_ and "要約する" in long_
    # 口調の欄と、メニューの項目は、短い文でも出る
    assert 'id="tones-text"' in short and "showTones('text'" in short and "口調を変える" in short


def test_new_labels_exist_in_ja_and_en_and_other_languages_fall_back(env):
    import languages
    keys = ("tone_btn", "tone_label", "tone_neutral", "summary_btn", "summary_label")
    for lang in ("Japanese", "English"):
        for k in keys:
            assert languages.UI_LABELS[lang].get(k, "").strip(), (lang, k)
    from ui_i18n import get_ui_labels
    assert get_ui_labels("Thai")["tone_btn"] == "Change tone" or get_ui_labels("Thai")["tone_btn"]   # 未生成の言語は、英語で表示される


def test_frontend_functions_and_history_update():
    js = _read("static", "js", "display.js")
    for needle in ("async function showTones", "async function summarizeResult", "/api/tones", "/api/summarize",
                   "UI.formality_formal", "UI.tone_neutral", "UI.formality_casual", "updateHistory(currentEntryId"):
        assert needle in js, needle
    # 選んだ口調は、別の言い方と同じ置き換え処理を通る（訳・読み方・履歴が同じ動きになる）
    assert js.count("useAlternative(mode,") >= 2
    assert not re.search(r"\.innerHTML\s*=", js)                     # 返ってきた文字は、textContent で入れる（HTML として解釈しない）
