"""v1.0: 画面文言の作成ツール（tools/generate_ui_labels.py）と、文言ファイルの検査"""
import glob
import json
import os
import re
import sys

import pytest

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
PH = re.compile(r"\{\w+\}")


@pytest.fixture
def lab(monkeypatch, tmp_path):
    import translator
    import ui_i18n
    monkeypatch.setattr(ui_i18n, "LABEL_DIR", str(tmp_path))
    monkeypatch.setattr(translator, "translate_labels", translator.translate_labels)   # 終わったら元に戻す
    ui_i18n._mem.clear()
    yield ui_i18n, translator, tmp_path
    ui_i18n._mem.clear()


def _tr(labels, lang=None):
    return {k: "T" + v for k, v in labels.items()}


def test_clean_drops_broken_placeholders_and_empty(lab):
    ui_i18n, *_ = lab
    src = {"a": "Hello {h}", "b": "Plain", "c": "Go {g} {c}"}
    out = ui_i18n._clean({"a": "Hola", "b": "  ", "c": "Ir {c} {g}", "zz": "x"}, src)
    assert out == {"c": "Ir {c} {g}"}                     # {h} が消えた a・空の b・知らないキー zz は使わない（順序違いは可）


def test_build_labels_one_call_then_fill_gaps_in_chunks(lab):
    ui_i18n, translator, tmp = lab
    from languages import FIXED_LABELS, UI_LABELS
    need = [k for k in UI_LABELS["English"] if k not in FIXED_LABELS]
    calls = []

    def fake(labels, lang):
        calls.append(len(labels))
        if len(calls) == 1:                                # 1回目は半分しか返らない（出力が途中で切れた想定）
            return {k: "T" + v for k, v in list(labels.items())[: len(labels) // 2]}
        return _tr(labels)
    translator.translate_labels = fake
    got, left = ui_i18n.build_labels("Thai")
    assert calls[0] == len(need) and got == len(need) and left == 0
    assert sum(calls[1:]) == len(need) - len(need) // 2   # 2回目以降は、欠けた分だけ頼んでいる
    assert ui_i18n.has_labels("Thai") and (tmp / "th-th.json").exists()


def test_run_check_without_api_and_missing_key(lab, monkeypatch, capsys):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    assert g.run(["--check", "--only", "Thai"]) == 1       # 足りない → 1
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert g.run(["--only", "Thai"]) == 2                  # キーがない → API は呼ばない
    assert g.run(["--only", "Klingon"]) == 2               # 知らない言語名
    out = capsys.readouterr().out
    assert "GEMINI_API_KEY" in out and "Klingon" in out and "sk-" not in out


def test_run_generates_and_pauses_politely(lab, monkeypatch):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    translator.translate_labels = lambda labels, lang: _tr(labels)
    slept = []
    t = [100.0]
    code = g.run(["--only", "Thai,Dutch"], now=lambda: t[0], sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)))
    assert code == 0
    assert (tmp / "th-th.json").exists() and (tmp / "nl-nl.json").exists()
    assert len(slept) >= 1 and all(s <= g.PACE_SEC + 0.01 for s in slept)   # 2回目の呼び出し前に待っている
    assert g.run(["--check", "--only", "Thai,Dutch"]) == 0
    assert g.run(["--only", "Thai,Dutch"], sleep=lambda s: None) == 0       # 揃っていれば何も呼ばない


def test_run_stops_safely_when_daily_quota_is_used(lab, monkeypatch):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    from gemini_errors import TranslationError
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    n = {"i": 0}

    def fake(labels, lang):
        n["i"] += 1
        if n["i"] > 1:
            raise TranslationError("err_quota")
        return _tr(labels)
    translator.translate_labels = fake
    code = g.run(["--only", "Thai,Dutch,Polish"], sleep=lambda s: None)
    assert code == 1
    assert (tmp / "th-th.json").exists()                   # 作れた分は残る
    assert not (tmp / "nl-nl.json").exists() and not (tmp / "pl-pl.json").exists()
    assert n["i"] == 2                                     # 上限になったら、それ以上は呼ばない


def test_committed_label_files_are_valid():
    """ui_labels/ にあるファイル: 知らないキー・空・差し込み記号 {h} の崩れがない"""
    from languages import LANGUAGES, UI_LABELS
    codes = {l["code"].lower() for l in LANGUAGES if l["name"] not in UI_LABELS}
    for p in sorted(glob.glob(os.path.join(ROOT, "ui_labels", "*.json"))):
        code = os.path.basename(p)[:-5]
        assert code in codes, code
        data = json.load(open(p, encoding="utf-8"))
        for k, v in data.items():
            assert k in UI_LABELS["English"], (code, k)
            assert isinstance(v, str) and v.strip(), (code, k)
            assert sorted(PH.findall(v)) == sorted(PH.findall(UI_LABELS["English"][k])), (code, k, v)


def test_version_is_1_0_x():
    import app as appmod
    assert appmod.APP_VERSION.startswith("1.0")


def test_timeout_falls_back_to_small_chunks_and_keeps_partial(lab, monkeypatch):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    from gemini_errors import TranslationError
    from languages import FIXED_LABELS, UI_LABELS
    need = [k for k in UI_LABELS["English"] if k not in FIXED_LABELS]
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    sizes = []

    def fake(labels, lang):
        sizes.append(len(labels))
        if len(labels) > 40:                               # 大きな依頼は時間切れ
            raise TranslationError("err_timeout")
        return _tr(labels)
    translator.translate_labels = fake
    code = g.run(["--only", "Thai"], sleep=lambda s: None)
    assert code == 0 and ui_i18n.has_labels("Thai")
    assert sizes[0] == len(need) and max(sizes[1:]) <= 40  # 1回目は全部、時間切れのあとは40個ずつ


def test_partial_progress_is_saved_when_a_call_fails(lab):
    ui_i18n, translator, tmp = lab
    from gemini_errors import TranslationError
    n = {"i": 0}

    def fake(labels, lang):
        n["i"] += 1
        if n["i"] == 3:
            raise TranslationError("err_overloaded")
        return _tr(labels)
    translator.translate_labels = fake
    with pytest.raises(TranslationError):
        ui_i18n.build_labels("Thai", chunk=40, whole=False)
    saved = json.loads((tmp / "th-th.json").read_text(encoding="utf-8"))
    assert len(saved) == 80                                # 2回成功した分（40個×2）は残っている


def test_run_stops_when_google_is_busy_for_several_languages(lab, monkeypatch):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    from gemini_errors import TranslationError
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    calls = []

    def fake(labels, lang):
        calls.append(lang)
        raise TranslationError("err_overloaded")
    translator.translate_labels = fake
    waits = []
    code = g.run(["--only", "Thai,Dutch,Polish,Czech,Danish"], sleep=lambda s: waits.append(s))
    assert code == 1
    assert set(calls) == {"Thai", "Dutch", "Polish"}       # 3言語続けて失敗したら、4言語目は試さない
    assert max(waits) >= g.RETRY_WAIT_SEC                  # 同じ言語のやり直しの前に、間を空けている


def test_run_retries_a_busy_language_then_succeeds(lab, monkeypatch):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    from gemini_errors import TranslationError
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    n = {"i": 0}

    def fake(labels, lang):
        n["i"] += 1
        if n["i"] == 1:
            raise TranslationError("err_overloaded")
        return _tr(labels)
    translator.translate_labels = fake
    assert g.run(["--only", "Thai"], sleep=lambda s: None) == 0
    assert ui_i18n.has_labels("Thai")


def test_tool_uses_longer_timeout_without_touching_app_defaults():
    import generate_ui_labels  # noqa: F401  # 読み込むだけで、ツール用の待ち時間が環境変数に入る
    assert float(os.environ["GEMINI_TEXT_TIMEOUT"]) >= 60
    src = open(os.path.join(ROOT, "translator.py"), encoding="utf-8").read()
    assert '_env_num("GEMINI_TEXT_TIMEOUT", 25.0)' in src   # アプリ本体の既定（25秒）は変えていない
