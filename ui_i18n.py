"""画面の文言（UIラベル）の多言語化。

- 日本語・英語は labels_ja.py / labels_en.py に手書きで用意（languages.UI_LABELS で取り出せる）
- それ以外の言語は ui_labels/<言語コード>.json から読む
- ファイルが無ければ、表示言語の選択時に Gemini で自動翻訳して保存（失敗したら英語で表示）
"""
import json
import os
import re
import threading
import time

import translator
from languages import FIXED_LABELS, LANGUAGES, UI_LABELS, get_lang_code

LABEL_DIR = os.environ.get("UI_LABELS_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_labels")
_lock = threading.Lock()
_mem = {}
_failed_at = {}
RETRY_AFTER = 300  # 生成に失敗した言語は5分間リトライしない（API呼び出しの乱発防止）


def _path(lang):
    return os.path.join(LABEL_DIR, get_lang_code(lang).lower() + ".json")


_PLACEHOLDER = re.compile(r"\{\w+\}")


def _clean(translated, source):
    """翻訳結果から、使えない文言を除く（キーが違う・空・{h} のような差し込み記号が原文と違うもの）。
    除いた分は English で表示される。差し込み記号が崩れると画面に {h} がそのまま出てしまうため"""
    out = {}
    for k, v in (translated or {}).items():
        if k not in source or not isinstance(v, str) or not v.strip():
            continue
        if sorted(_PLACEHOLDER.findall(source[k])) != sorted(_PLACEHOLDER.findall(v)):
            continue
        out[k] = v.strip()
    return out


def _load_cached(lang):
    with _lock:
        if lang in _mem:
            return _mem[lang]
    try:
        with open(_path(lang), encoding="utf-8") as f:
            data = json.load(f)
        data = _clean(data, UI_LABELS["English"])
    except (OSError, ValueError):
        return None
    with _lock:
        _mem[lang] = data
    return data


def get_ui_labels(lang):
    """表示言語のラベル。足りないキーは English で補い、From/To は常に固定"""
    labels = dict(UI_LABELS["English"])
    if lang in UI_LABELS:
        labels.update(UI_LABELS[lang])
    else:
        cached = _load_cached(lang)
        if cached:
            labels.update(cached)
    labels.update(FIXED_LABELS)
    return labels


def _missing(lang):
    """翻訳が必要なキー（FIXED と手書き言語は対象外）"""
    have = _load_cached(lang) or {}
    return {k: v for k, v in UI_LABELS["English"].items() if k not in FIXED_LABELS and k not in have}


def has_labels(lang):
    """文言が（ほぼ）揃っているか。新しいキーが増えたときは False になり、差分だけ翻訳される"""
    if lang in UI_LABELS:
        return True
    return _load_cached(lang) is not None and not _missing(lang)


def _save(lang, translated):
    """既にある文言に translated を足して、メモリと ui_labels/<言語コード>.json に保存する"""
    merged = dict(_load_cached(lang) or {})
    merged.update(translated)
    with _lock:
        _mem[lang] = merged
    try:
        os.makedirs(LABEL_DIR, exist_ok=True)
        tmp = _path(lang) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=1)
        os.replace(tmp, _path(lang))
    except OSError as e:
        print(f"[ui_i18n] could not save labels for {lang}: {e}", flush=True)


def ensure_ui_labels(lang):
    """足りない文言だけ Gemini で翻訳して保存する。揃っていれば True（失敗しても例外は出さない）"""
    if has_labels(lang):
        return True
    if time.time() - _failed_at.get(lang, 0) < RETRY_AFTER:
        return False
    _failed_at[lang] = time.time()
    source = _missing(lang)
    try:
        translated = _clean(translator.translate_labels(source, lang), source)
    except Exception as e:
        print(f"[ui_i18n] could not generate labels for {lang}: {e}", flush=True)
        return False
    if len(translated) < len(source) * 0.8:  # 欠落が多い結果は採用しない
        print(f"[ui_i18n] incomplete labels for {lang}: {len(translated)}/{len(source)}", flush=True)
        return False
    _failed_at.pop(lang, None)
    _save(lang, translated)
    return True


_inflight = set()


def ensure_async(lang):
    """足りない文言を裏で補う（画面は待たせない。次の表示から反映）"""
    if lang in UI_LABELS or lang in _inflight or has_labels(lang):
        return
    if time.time() - _failed_at.get(lang, 0) < RETRY_AFTER:
        return
    _inflight.add(lang)

    def run():
        try:
            ensure_ui_labels(lang)
        finally:
            _inflight.discard(lang)

    threading.Thread(target=run, daemon=True).start()


def build_labels(lang, chunk=60):
    """tools/generate_ui_labels.py 用。足りない文言を翻訳して保存する。戻り値は (今回できた数, まだ足りない数)。
    まず全部を1回で頼み（API の呼び出し回数を節約）、欠けた分だけを chunk 個ずつに分けて頼み直す（最大2周）。
    上限(429)などの例外は、呼び出し側が止められるようにそのまま投げる"""
    source = _missing(lang)
    if not source:
        return 0, 0
    got = _clean(translator.translate_labels(source, lang), source)
    for _ in range(2):
        rest = {k: v for k, v in source.items() if k not in got}
        if not rest or len(got) >= len(source) * 0.98:
            break
        items = list(rest.items())
        for i in range(0, len(items), chunk):
            got.update(_clean(translator.translate_labels(dict(items[i:i + chunk]), lang), rest))
    if got:
        _save(lang, got)
    return len(got), len(source) - len(got)


def audit():
    """全言語の文言の状況。[(言語名, あるキー数, 足りないキー数)]。API は使わない（手書きの日本語・英語は除く）"""
    rows = []
    for name in all_languages():
        if name in UI_LABELS:
            continue
        have = _load_cached(name) or {}
        rows.append((name, len(have), len(_missing(name))))
    return rows


def all_languages():
    return [l["name"] for l in LANGUAGES]
