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
    """文言の保存先を一時フォルダにし、API の呼び出し（translator._generate）を偽物に差し替える"""
    import translator
    import ui_i18n
    monkeypatch.setattr(ui_i18n, "LABEL_DIR", str(tmp_path))
    monkeypatch.setattr(translator, "RETRY_WAIT", 0)
    monkeypatch.setattr(translator, "_generate", translator._generate)   # 終わったら元に戻す
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    ui_i18n._mem.clear()
    yield ui_i18n, translator, tmp_path
    ui_i18n._mem.clear()


def fake_api(translator, behavior=None, trim=None):
    """偽の Gemini。依頼された文言に "T" を付けて返す。
    behavior(state, labels) で失敗を起こせる。trim(state) が数を返すと、その個数だけ返す（出力が途中で切れた想定）"""
    state = {"n": 0, "sizes": []}

    def _generate(parts, system=None):
        state["n"] += 1
        labels = json.loads(parts[0].split("\n", 1)[1])      # translate_labels の依頼文は「説明\n{JSON}」
        state["sizes"].append(len(labels))
        if behavior:
            behavior(state, labels)
        items = list(labels.items())
        keep = trim(state) if trim else None
        if keep is not None:
            items = items[:keep]
        return json.dumps({k: "T" + v for k, v in items}, ensure_ascii=False)
    translator._generate = _generate
    return state


def failing(key, when=lambda state: True):
    from gemini_errors import TranslationError

    def raise_it(state, labels):
        if when(state):
            raise TranslationError(key)
    return raise_it


def need_keys():
    from languages import FIXED_LABELS, UI_LABELS
    return [k for k in UI_LABELS["English"] if k not in FIXED_LABELS]


def test_clean_drops_broken_placeholders_and_empty(lab):
    ui_i18n, *_ = lab
    src = {"a": "Hello {h}", "b": "Plain", "c": "Go {g} {c}"}
    out = ui_i18n._clean({"a": "Hola", "b": "  ", "c": "Ir {c} {g}", "zz": "x"}, src)
    assert out == {"c": "Ir {c} {g}"}                     # {h} が消えた a・空の b・知らないキー zz は使わない（順序違いは可）


def test_build_labels_one_call_then_fill_gaps_in_chunks(lab):
    ui_i18n, translator, tmp = lab
    need = need_keys()
    st = fake_api(translator, trim=lambda s: len(need) // 2 if s["n"] == 1 else None)   # 1回目は半分だけ返る
    got, left = ui_i18n.build_labels("Thai")
    assert st["sizes"][0] == len(need) and got == len(need) and left == 0
    assert sum(st["sizes"][1:]) == len(need) - len(need) // 2   # 2回目以降は、欠けた分だけ頼んでいる
    assert ui_i18n.has_labels("Thai") and (tmp / "th-th.json").exists()


def test_partial_progress_is_saved_when_a_call_fails(lab):
    ui_i18n, translator, tmp = lab
    from gemini_errors import TranslationError
    fake_api(translator, failing("err_failed", lambda s: s["n"] == 3))
    with pytest.raises(TranslationError):
        ui_i18n.build_labels("Thai", chunk=40, whole=False)
    saved = json.loads((tmp / "th-th.json").read_text(encoding="utf-8"))
    assert len(saved) == 80                                # 2回成功した分（40個×2）は残っている


def test_run_check_without_api_and_missing_key(lab, monkeypatch, capsys):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    assert g.run(["--check", "--only", "Thai"]) == 1       # 足りない → 1
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert g.run(["--only", "Thai"]) == 2                  # キーがない（聞けない環境）→ API は呼ばない
    assert g.run(["--only", "Thai"], ask=lambda prompt: "  ") == 2        # 聞かれて何も入れなかった → API は呼ばない
    assert g.run(["--only", "Klingon"]) == 2               # 知らない言語名
    assert g.run(["--only", "Thai", "--max-calls", "abc"]) == 2
    out = capsys.readouterr().out
    assert "APIキーが入力されませんでした" in out and "Klingon" in out and "sk-" not in out


def test_run_asks_for_the_key_when_missing_and_does_not_print_it(lab, monkeypatch, capsys):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    st = fake_api(translator)
    asked = []
    code = g.run(["--only", "Thai", "--no-check"], sleep=lambda s: None, ask=lambda prompt: (asked.append(prompt), "  secret-key-123  ")[1])
    out = capsys.readouterr().out
    assert code == 0 and len(asked) == 1 and st["n"] == 1
    assert "secret-key-123" not in out                     # 入れたキーは、画面（ログ）に出さない
    assert os.environ["GEMINI_API_KEY"] == "secret-key-123"
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_run_generates_and_paces_every_real_call(lab):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    st = fake_api(translator)
    stub = translator._generate
    slept = []
    t = [100.0]
    code = g.run(["--only", "Thai,Dutch", "--no-check"], now=lambda: t[0], sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)))
    assert code == 0
    assert (tmp / "th-th.json").exists() and (tmp / "nl-nl.json").exists()
    assert st["n"] == 2 and len(slept) == 1 and slept[0] <= g.PACE_SEC + 0.01   # 2回目の呼び出しの前に待っている
    assert translator._generate is stub                                          # 終わったら差し替えを元に戻す
    assert g.run(["--check", "--only", "Thai,Dutch"]) == 0
    assert g.run(["--only", "Thai,Dutch"], sleep=lambda s: None) == 0   # 揃っていれば、混雑チェックもしない
    assert st["n"] == 2                                                          # 揃っていれば何も呼ばない


def test_run_stops_safely_when_daily_quota_is_used(lab):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    fake_api(translator, failing("err_quota", lambda s: s["n"] > 1))
    code = g.run(["--only", "Thai,Dutch,Polish", "--no-check"], sleep=lambda s: None)
    assert code == 1
    assert (tmp / "th-th.json").exists()                   # 作れた分は残る
    assert not (tmp / "nl-nl.json").exists() and not (tmp / "pl-pl.json").exists()


def test_run_stops_at_call_budget_and_counts_failed_calls(lab, capsys):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    st = fake_api(translator, failing("err_overloaded"))
    code = g.run(["--only", "Thai,Dutch", "--max-calls", "4", "--no-check"], sleep=lambda s: None)
    assert code == 1
    assert st["n"] == 4                                    # 失敗した呼び出しも数えて、上限で止まる（それ以上は呼ばない）
    out = capsys.readouterr().out
    assert "呼び出し上限（4回）" in out and "API の呼び出し: 4回" in out


def test_timeout_falls_back_to_small_chunks(lab):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    need = need_keys()
    from gemini_errors import TranslationError

    def big_times_out(state, labels):
        if len(labels) > 40:
            raise TranslationError("err_timeout")
    st = fake_api(translator, big_times_out)
    assert g.run(["--only", "Thai", "--max-calls", "30", "--no-check"], sleep=lambda s: None) == 0
    assert ui_i18n.has_labels("Thai")
    assert st["sizes"][0] == len(need) and max(st["sizes"][-3:]) <= 40   # 全部を頼んで時間切れ→40個ずつ


def test_run_stops_when_google_is_busy_for_several_languages(lab):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    st = fake_api(translator, failing("err_overloaded"))
    waits = []
    code = g.run(["--only", "Thai,Dutch,Polish,Czech,Danish", "--max-calls", "100", "--no-check"], sleep=lambda s: waits.append(s))
    assert code == 1
    assert st["n"] <= g.STOP_AFTER_BUSY * g.TRIES * 2      # 続けて失敗した言語が上限に達したら打ち切り（次の言語は試さない）
    assert max(waits) >= g.RETRY_WAIT_SEC                  # 同じ言語のやり直しの前に、間を空けている


def test_run_retries_a_busy_language_then_succeeds(lab):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    fake_api(translator, failing("err_overloaded", lambda s: s["n"] <= 2))   # 最初の2回（予備モデルへの切り替え含む）は失敗
    assert g.run(["--only", "Thai", "--no-check"], sleep=lambda s: None) == 0
    assert ui_i18n.has_labels("Thai")


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


def test_tool_uses_longer_timeout_without_touching_app_defaults():
    import generate_ui_labels  # noqa: F401  # 読み込むだけで、ツール用の待ち時間が環境変数に入る
    assert float(os.environ["GEMINI_TEXT_TIMEOUT"]) >= 60
    src = open(os.path.join(ROOT, "translator.py"), encoding="utf-8").read()
    assert '_env_num("GEMINI_TEXT_TIMEOUT", 25.0)' in src   # アプリ本体の既定（25秒）は変えていない


def test_preflight_stops_at_once_when_google_is_busy(lab, capsys):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    st = fake_api(translator, failing("err_overloaded"))
    waits = []
    code = g.run(["--only", "Thai,Dutch"], sleep=lambda s: waits.append(s))
    out = capsys.readouterr().out
    assert code == 3 and st["n"] <= 2                      # 混んでいれば、本番に入らず 1〜2 回の呼び出しだけで止まる
    assert not (tmp / "th-th.json").exists() and max(waits or [0]) < g.RETRY_WAIT_SEC
    assert "混雑チェック: 失敗" in out and "Google 側が混んでいます" in out and "make   Thai" not in out
    assert "OK  " not in out                                # 長い一覧は出さない（数だけ）


def test_preflight_ok_then_proceeds_and_is_counted(lab, capsys):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    st = fake_api(translator)
    assert g.run(["--only", "Thai"], sleep=lambda s: None) == 0
    out = capsys.readouterr().out
    assert st["n"] == 2 and st["sizes"][0] == len(g.PROBE)   # 試しの1回 + 本番1回
    assert "混雑チェック: OK" in out and ui_i18n.has_labels("Thai")
    st["n"] = 0
    assert g.run(["--only", "Thai"], sleep=lambda s: None) == 0
    assert st["n"] == 0                                       # 何も足りなければ、試しの呼び出しもしない
    ui_i18n._mem.clear()
    for f in tmp.glob("*.json"):
        f.unlink()
    assert g.run(["--only", "Thai", "--max-calls", "1"], sleep=lambda s: None) == 1
    out = capsys.readouterr().out
    assert st["n"] == 1 and "呼び出し上限（1回）" in out     # 試しの1回も上限に数える


def test_preflight_quota_message_and_no_check_flag(lab, capsys):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    st = fake_api(translator, failing("err_quota"))
    assert g.run(["--only", "Thai"], sleep=lambda s: None) == 1
    out = capsys.readouterr().out
    assert st["n"] == 1 and "無料枠の上限" in out and "17時" in out
    st["n"] = 0
    g.run(["--only", "Thai", "--no-check"], sleep=lambda s: None)
    assert st["n"] == 1 and "混雑チェック" not in capsys.readouterr().out


def test_budget_stop_message_does_not_blame_the_daily_limit(lab, capsys):
    ui_i18n, translator, tmp = lab
    import generate_ui_labels as g
    fake_api(translator)
    g.run(["--only", "Thai,Dutch", "--max-calls", "2"], sleep=lambda s: None)
    out = capsys.readouterr().out
    assert "呼び出し上限（2回）" in out and "同じコマンドをすぐ実行できます" in out
    assert "今日の無料枠の上限に達しました" not in out


def test_version_is_1_x():
    import app as appmod
    assert appmod.APP_VERSION.startswith("1.")


def test_requirements_pin_google_genai_below_next_major():
    reqs = open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8").read()
    assert re.search(r"^google-genai>=3\.6,<4\s*$", reqs, re.M)
