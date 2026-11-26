"""v1.7.3: フレーズ集の作成ツール（tools/generate_phrasebook.py）。キーは隠して聞く・呼び出しの上限・間隔・続きから。"""
import json
import os
import sys

import pytest

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))


@pytest.fixture
def pb(monkeypatch, tmp_path):
    import generate_phrasebook as gp
    import translator
    monkeypatch.setattr(gp, "OUT", str(tmp_path))
    monkeypatch.setattr(translator, "RETRY_WAIT", 0)
    monkeypatch.setattr(translator, "_generate", translator._generate)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    return gp, translator, tmp_path


def fake(translator, fail=None, short=False):
    st = {"n": 0}

    def _generate(parts, system=None):
        st["n"] += 1
        if fail:
            fail(st)
        src = json.loads(parts[0].split("\n", 1)[1])
        items = list(src.items())[:-1] if short else list(src.items())
        return json.dumps({k: "T" + v for k, v in items}, ensure_ascii=False)
    translator._generate = _generate
    return st


def test_makes_only_missing_languages_one_call_each_and_paces(pb):
    gp, translator, tmp = pb
    st = fake(translator)
    slept, t = [], [100.0]
    code = gp.run(["--only", "Thai,Dutch", "--no-check"], now=lambda: t[0], sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)))
    assert code == 0 and st["n"] == 2
    assert sorted(os.listdir(tmp)) == ["nl-nl.json", "th-th.json"]
    data = json.load(open(tmp / "th-th.json", encoding="utf-8"))
    assert len(data) == 81 and data["hello"] == "THello"
    assert slept and all(abs(s - 13) < 0.01 for s in slept)            # 2回目の前に13秒待つ（無料枠は1分5回）


def test_max_calls_stops_and_next_run_continues(pb, capsys):
    gp, translator, tmp = pb
    st = fake(translator)
    code = gp.run(["--only", "Thai,Dutch,Greek", "--no-check", "--max-calls", "2"], sleep=lambda s: None)
    out = capsys.readouterr().out
    assert code == 1 and st["n"] == 2 and "呼び出し上限（2回）" in out
    assert sorted(os.listdir(tmp)) == ["nl-nl.json", "th-th.json"]      # 保存済みの分は残る
    code = gp.run(["--only", "Thai,Dutch,Greek", "--no-check"], sleep=lambda s: None)
    assert code == 0 and st["n"] == 3 and len(os.listdir(tmp)) == 3     # 続きは、足りない1言語だけ


def test_incomplete_answer_is_not_saved(pb):
    gp, translator, tmp = pb
    fake(translator, short=True)
    code = gp.run(["--only", "Thai", "--no-check"], sleep=lambda s: None)
    assert code == 1 and os.listdir(tmp) == []


def test_quota_stops_everything(pb, capsys):
    from gemini_errors import TranslationError
    gp, translator, tmp = pb

    def boom(st):
        raise TranslationError("err_quota")
    st = fake(translator, fail=boom)
    code = gp.run(["--only", "Thai,Dutch", "--no-check"], sleep=lambda s: None)
    out = capsys.readouterr().out
    assert code == 1 and "無料枠の上限" in out and "17時" in out and os.listdir(tmp) == []


def test_key_is_asked_hidden_and_never_printed(pb, monkeypatch, capsys):
    gp, translator, tmp = pb
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    st = fake(translator)
    asked = []
    code = gp.run(["--only", "Thai", "--no-check"], sleep=lambda s: None, ask=lambda p: (asked.append(p), " secret-key-9 ")[1])
    out = capsys.readouterr().out
    assert code == 0 and asked == ["APIキー: "] and "secret-key-9" not in out
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert gp.run(["--only", "Dutch"], ask=lambda p: "  ") == 2           # 何も入れなければ、API は呼ばない
    assert st["n"] == 1


def test_bad_arguments_and_check_mode(pb, monkeypatch):
    gp, translator, tmp = pb
    assert gp.run(["--only", "Klingon"]) == 2
    assert gp.run(["--only", "Thai", "--max-calls", "abc"]) == 2
    assert gp.run(["--check", "--only", "Thai"]) == 1                      # 足りない
    fake(translator)
    gp.run(["--only", "Thai", "--no-check"], sleep=lambda s: None)
    assert gp.run(["--check", "--only", "Thai"]) == 0


def test_real_data_state_matches_the_24_missing_languages():
    """リポジトリのいまの状態: ja/en を含む17言語にあり、24言語が足りない"""
    import generate_phrasebook as gp
    missing, _ = gp._targets([])
    names = {l["name"] for l in missing}
    assert len(missing) == 24 and "Dutch" in names and "Swahili" in names and "Thai" not in names
