"""解説・口調・要約・返信の提案・辞書と文法: 結果カードの「…」メニューから呼ぶ、短い補助の呼び出し。
Gemini の呼び出し本体は translator.py（ここでは translator._call を使う）。translator からも再公開しているので、translator.xxx で今まで通り使える"""
import translator as T
from gemini_errors import TranslationError
from json_reply import _loads_object
from languages import AUTO
from prompts import (
    DICT_SYSTEM, EXPLAIN_SYSTEM, REPLY_SYSTEM, SUMMARY_SYSTEM, TONE_SYSTEM,
    dict_prompt, explain_prompt, reply_prompt,
)


def explain_text(text, text_lang, explain_lang):
    """スラング・略語・ニュアンスの解説を explain_lang で返す"""
    prompt = explain_prompt(text, text_lang, explain_lang)
    data = _loads_object(T._call([prompt], system=EXPLAIN_SYSTEM))
    if data is None:
        raise TranslationError("err_failed")
    raw_text = str(data.get("explanation") or "").strip()
    if not raw_text:
        raise TranslationError("err_failed")
    return raw_text


REPLY_COUNT = 3


def reply_suggestions(message, msg_lang, reader_lang, formality="auto", context=""):
    """受け取った文への返信案を REPLY_COUNT 個。[{"kind", "text", "meaning"}]（text は相手の言語、kind と meaning は読む人の言語）。
    text が空のものは捨てる。1つも残らなければ失敗にする"""
    prompt = reply_prompt(message, msg_lang, reader_lang, REPLY_COUNT, T.FORMALITY_HINTS.get(formality, ""), context)
    data = _loads_object(T._call([prompt], system=REPLY_SYSTEM))
    items = data.get("replies") if isinstance(data, dict) else None
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or "").strip()[:500]
        if text:
            out.append({"kind": str(it.get("kind") or "").strip()[:40], "text": text, "meaning": str(it.get("meaning") or "").strip()[:500]})
    if not out:
        raise TranslationError("err_failed")
    return out[:REPLY_COUNT]


def dictionary_notes(text, text_lang, explain_lang):
    """大事な単語（読み・品詞・意味・例文・語源）と文法のポイントを explain_lang で返す。{"words": [...], "grammar": [...]}
    単語も文法も空なら失敗にする"""
    data = _loads_object(T._call([dict_prompt(text, text_lang, explain_lang)], system=DICT_SYSTEM))
    if not isinstance(data, dict):
        raise TranslationError("err_failed")
    words = []
    for w in data.get("words") if isinstance(data.get("words"), list) else []:
        if not isinstance(w, dict):
            continue
        word, meaning = str(w.get("word") or "").strip()[:80], str(w.get("meaning") or "").strip()[:200]
        if word and meaning:
            words.append({k: str(w.get(k) or "").strip()[:200] for k in ("reading", "pos", "example", "origin")} | {"word": word, "meaning": meaning})
    grammar = []
    for g in data.get("grammar") if isinstance(data.get("grammar"), list) else []:
        if isinstance(g, dict) and str(g.get("point") or "").strip() and str(g.get("note") or "").strip():
            grammar.append({"point": str(g["point"]).strip()[:120], "note": str(g["note"]).strip()[:400]})
    if not words and not grammar:
        raise TranslationError("err_failed")
    return {"words": words[:6], "grammar": grammar[:3]}


TONES = ("formal", "neutral", "casual")


def tone_translations(text, translation, source_lang, target_lang):
    """同じ原文の訳を、3つの口調（丁寧・標準・くだけた）で1回の呼び出しで返す。{"formal": ..., "neutral": ..., "casual": ...}
    3つとも空でない文字列が返らなければ失敗にする（半端な結果で今の訳を置き換えない）"""
    src = "the source language (detect it)" if source_lang == AUTO else source_lang
    prompt = (
        f"The text between <text> tags is in {src}. It was translated into {target_lang} as: {translation}\n"
        f"Write that same translation in {target_lang} in three registers, with exactly the same meaning and information: "
        "formal = polite and courteous (honorific forms where the language has them); "
        "neutral = standard, neutral everyday wording; "
        "casual = relaxed and friendly, as between friends. "
        "If the language has no clear formal/casual forms, vary word choice and phrasing slightly. "
        "Keep line breaks. Do not add or drop information."
        "\n<text>\n" + text + "\n</text>"
    )
    data = _loads_object(T._call([prompt], system=TONE_SYSTEM))
    if not isinstance(data, dict):
        raise TranslationError("err_failed")
    out = {}
    for k in TONES:
        v = str(data.get(k) or "").strip()
        if not v:
            raise TranslationError("err_failed")
        out[k] = v
    return out


def summarize_text(text, summary_lang):
    """長い文章の要約を summary_lang で返す（箇条書き3〜5個。原文の言語は問わない）"""
    prompt = (
        f"Summarize the text between <text> tags in {summary_lang}. "
        "Write 3 to 5 short bullet points, each starting with \"- \", covering the main points only "
        "(about 120 words or fewer in total). Do not add information that is not in the text.\n"
        "<text>\n" + text + "\n</text>"
    )
    data = _loads_object(T._call([prompt], system=SUMMARY_SYSTEM))
    summary = str((data or {}).get("summary") or "").strip()
    if not summary:
        raise TranslationError("err_failed")
    return summary
