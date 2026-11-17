"""Gemini が返した JSON を読み取って整える処理（外から来た値なので、型・長さ・範囲を必ず検査する）"""
import json
import re

from gemini_errors import TranslationError


def _parse(raw):
    raw = (raw or "").strip()
    if not raw:
        raise TranslationError("err_failed")
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {
                "detected_language": str(data.get("detected_language") or "").strip(),
                "source_text": str(data.get("source_text") or "").strip(),
                "translation": str(data.get("translation") or "").strip(),
                "pronunciation": str(data.get("pronunciation") or "").strip(),
            }
    except json.JSONDecodeError:
        pass
    # JSONで返らなかった場合は本文をそのまま訳文として扱う
    return {"detected_language": "", "source_text": "", "translation": raw, "pronunciation": ""}


def _loads_object(raw):
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


MAX_BLOCKS = 60



def clean_blocks(raw):
    """Gemini が返した blocks を検査して整える（位置は0-1000の整数、不正なものは捨てる）"""
    out = []
    if not isinstance(raw, list):
        return out
    for b in raw[:MAX_BLOCKS]:
        if not isinstance(b, dict):
            continue
        text = str(b.get("text") or "").strip()[:500]
        tr = str(b.get("translation") or "").strip()[:1000]
        box = b.get("box_2d")
        if not tr or not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        try:
            y0, x0, y1, x1 = [int(round(float(v))) for v in box]
        except (TypeError, ValueError):
            continue
        y0, y1 = sorted((max(0, min(1000, y0)), max(0, min(1000, y1))))
        x0, x1 = sorted((max(0, min(1000, x0)), max(0, min(1000, x1))))
        if y1 - y0 < 5 or x1 - x0 < 5:
            continue
        out.append({"text": text, "translation": tr, "box": [y0, x0, y1, x1]})
    return out
