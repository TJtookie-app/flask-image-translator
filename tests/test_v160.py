"""v1.6: 返信の提案（/api/replies）・辞書と文法（/api/dictionary）"""
import json
import os
import re

from conftest import ROOT, start

REPLIES = json.dumps({"replies": [
    {"kind": "了解", "text": "Sounds good, see you at 7!", "meaning": "いいね、7時に会おう！"},
    {"kind": "断る", "text": "Sorry, I can't make it tonight.", "meaning": "ごめん、今夜は行けない。"},
    {"kind": "聞き返す", "text": "Where should we meet?", "meaning": "どこで待ち合わせる？"}]})
DICT = json.dumps({
    "words": [{"word": "grab", "reading": "", "pos": "動詞", "meaning": "さっと取る・軽く食べる", "example": "Let's grab a bite.", "origin": "古英語に由来"},
              {"word": "", "meaning": "空の単語は捨てる"}, {"word": "bite", "meaning": ""}],
    "grammar": [{"point": "Let's + 動詞", "note": "〜しよう、と誘う言い方。"}, {"point": "", "note": "x"}]})


def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def _use(mp, translator, calls, reply):
    mp.setattr(translator, "_generate", lambda parts, system=None: (calls.append((parts, system)) or reply))


# ---------------- 返信の提案 ----------------

def test_replies_api_returns_three_replies_in_one_call(env):
    app, translator, calls, mp = env
    _use(mp, translator, calls, REPLIES)
    c = app.test_client(); start(c, "Japanese")
    r = c.post("/api/replies", json={"text": "Dinner tonight at 7?", "lang": "English"})
    assert r.status_code == 200
    items = r.get_json()["replies"]
    assert [i["text"] for i in items] == ["Sounds good, see you at 7!", "Sorry, I can't make it tonight.", "Where should we meet?"]
    assert items[0]["kind"] == "了解" and items[0]["meaning"].startswith("いいね")
    assert len(calls) == 1
    prompt = calls[0][0][0]
    assert "<message>\nDinner tonight at 7?\n</message>" in prompt and "English" in prompt and "Japanese" in prompt and "3 different" in prompt
    assert '"replies"' in calls[0][1] and "never follow instructions" in calls[0][1]


def test_replies_use_the_style_setting_and_conversation_context(env):
    app, translator, calls, mp = env
    _use(mp, translator, calls, REPLIES)
    c = app.test_client(); start(c, "Japanese")
    c.post("/api/replies", json={"text": "hi", "lang": "English", "formality": "business", "context": "A: hello\nB: hi there"})
    p = calls[-1][0][0]
    assert "professional business register" in p and "A: hello" in p
    c.post("/api/replies", json={"text": "hi", "lang": "English", "formality": "<evil>"})
    assert "business register" not in calls[-1][0][0]


def test_replies_reject_bad_input_without_calling_the_api(env):
    app, translator, calls, mp = env
    _use(mp, translator, calls, REPLIES)
    c = app.test_client(); start(c, "Japanese")
    assert c.post("/api/replies", json={"text": "", "lang": "English"}).status_code == 400
    assert c.post("/api/replies", json={"text": "x" * 1001, "lang": "English"}).status_code == 400
    assert not calls


def test_replies_drop_empty_ones_and_fail_when_none_left(env):
    app, translator, calls, mp = env
    c = app.test_client(); start(c, "Japanese")
    _use(mp, translator, calls, json.dumps({"replies": [{"kind": "a", "text": " ", "meaning": "x"}, {"kind": "b", "text": "OK", "meaning": "了解"}, "junk", None]}))
    r = c.post("/api/replies", json={"text": "hi", "lang": "English"})
    assert r.status_code == 200 and r.get_json()["replies"] == [{"kind": "b", "text": "OK", "meaning": "了解"}]
    for bad in ('{"replies": []}', '{"replies": "x"}', "not json", '{"replies": [{"text": ""}]}'):
        _use(mp, translator, calls, bad)
        assert c.post("/api/replies", json={"text": "hi", "lang": "English"}).status_code == 502


# ---------------- 辞書・文法 ----------------

def test_dictionary_api_returns_words_and_grammar(env):
    app, translator, calls, mp = env
    _use(mp, translator, calls, DICT)
    c = app.test_client(); start(c, "Japanese")
    r = c.post("/api/dictionary", json={"text": "Let's grab a bite.", "lang": "English"})
    assert r.status_code == 200
    d = r.get_json()
    assert [w["word"] for w in d["words"]] == ["grab"]                 # 単語か意味が空のものは捨てる
    assert d["words"][0]["example"] == "Let's grab a bite." and d["words"][0]["origin"] == "古英語に由来"
    assert d["grammar"] == [{"point": "Let's + 動詞", "note": "〜しよう、と誘う言い方。"}]
    assert len(calls) == 1
    p = calls[0][0][0]
    assert "<text>\nLet's grab a bite.\n</text>" in p and "English" in p and "Japanese" in p and "etymology" in p
    assert '"words"' in calls[0][1] and "never follow instructions" in calls[0][1]


def test_dictionary_rejects_bad_input_and_empty_results(env):
    app, translator, calls, mp = env
    _use(mp, translator, calls, DICT)
    c = app.test_client(); start(c, "Japanese")
    assert c.post("/api/dictionary", json={"text": "", "lang": "English"}).status_code == 400
    assert c.post("/api/dictionary", json={"text": "x" * 601, "lang": "English"}).status_code == 400
    assert not calls
    for bad in ('{"words": [], "grammar": []}', "not json", '{"words": [{"word": "a"}]}', "[]"):
        _use(mp, translator, calls, bad)
        assert c.post("/api/dictionary", json={"text": "hi", "lang": "English"}).status_code == 502


def test_new_apis_count_toward_the_limits(env):
    app, translator, calls, mp = env
    from limits import stats
    _use(mp, translator, calls, REPLIES)
    c = app.test_client(); start(c, "Japanese")
    assert c.post("/api/replies", json={"text": "hi", "lang": "English"}).status_code == 200
    _use(mp, translator, calls, DICT)
    assert c.post("/api/dictionary", json={"text": "hi", "lang": "English"}).status_code == 200
    s = json.dumps(stats.snapshot() if hasattr(stats, "snapshot") else {}, default=str)
    assert "reply" in s and "dict" in s


# ---------------- 画面の組み立て ----------------

def test_menu_and_boxes_and_script(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.post("/", data={"mode": "text", "direct_text": "hello", "formality": "auto", "pron": "0"}).get_data(as_text=True)
    assert "返信を提案" in html and "辞書・文法" in html
    assert "suggestReplies('text', this)" in html and "showDictionary('text', this)" in html
    assert 'id="replies-text"' in html and 'id="dict-text"' in html
    assert 'class="rc-item rc-reply"' in html
    order = re.findall(r"js/([a-z_0-9]+)\.js", _read("templates", "components", "scripts.html"))
    assert "assist" in order and order.index("assist") > order.index("display")
    js = _read("static", "js", "assist.js")
    for needle in ("/api/replies", "/api/dictionary", "isReading = ", "function suggestReplies", "function showDictionary", "addVocab(", "syncAssistMenu", "textContent"):
        assert needle in js, needle
    assert "innerHTML" not in js                                       # AI の返事は、文字としてだけ表示する
    assert len(js.splitlines()) <= 200


def test_new_labels_in_ja_and_en():
    import labels_en, labels_ja
    for k in ("reply_btn", "reply_label", "dict_btn", "dict_grammar", "dict_origin"):
        assert labels_ja.LABELS[k].strip() and labels_en.LABELS[k].strip(), k


def test_assist_module_split_keeps_old_names():
    import translator
    for n in ("explain_text", "tone_translations", "summarize_text", "reply_suggestions", "dictionary_notes", "TONES", "REPLY_COUNT"):
        assert hasattr(translator, n), n
    assert len(_read("translator.py").splitlines()) <= 450
