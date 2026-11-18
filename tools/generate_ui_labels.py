"""画面の文言（日本語・英語以外の全言語）を作る・確認するツール。

  python tools/generate_ui_labels.py            足りない文言だけを Gemini で翻訳して ui_labels/ に保存（途中で止まっても、次は続きから）
  python tools/generate_ui_labels.py --check    API を使わず、全言語が揃っているか確認（揃っていなければ終了コード 1）
  python tools/generate_ui_labels.py --only Thai,Dutch    言語を指定（英語名。カンマ区切り）
  python tools/generate_ui_labels.py --force --only Thai  指定した言語を作り直す（--only なしの --force は全言語）

APIキーは、実行する端末の環境変数 GEMINI_API_KEY に入れてから実行します（コードやチャットには書かない）。
  PowerShell:  $env:GEMINI_API_KEY = "（自分のキー）"
無料枠は「1分5回・1日20回」程度なので、1回ごとに約13秒待ち、1日の上限に達したら保存済みの分を残して止まります。
その場合は、日本時間の夕方（17時ごろ）に上限が戻るので、もう一度同じコマンドを実行してください（続きから作ります）。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 文言は文字数が多く、アプリ本体の待ち時間（25秒）では足りない。このツールの中だけ長くする（本体の設定は変えない）
os.environ.setdefault("GEMINI_TEXT_TIMEOUT", "150")
os.environ.setdefault("GEMINI_ATTEMPTS", "2")

import ui_i18n  # noqa: E402
from languages import LANGUAGES, UI_LABELS  # noqa: E402

PACE_SEC = float(os.environ.get("LABEL_PACE_SEC", "13"))   # API の呼び出しの間隔（無料枠は1分5回）
RETRY_WAIT_SEC = float(os.environ.get("LABEL_RETRY_WAIT_SEC", "30"))   # 混雑・時間切れのとき、同じ言語をやり直すまでの待ち（回数をかけて長くなる）
TRIES = 3             # 1言語あたりの挑戦回数
STOP_AFTER_BUSY = 3   # 続けてこれだけの言語が混雑・時間切れで失敗したら、Google側が混んでいるとみて止まる
BUSY_KEYS = {"err_timeout", "err_overloaded", "err_connection"}


def _say(text=""):
    print(text, flush=True)


def _targets(only):
    names = [l["name"] for l in LANGUAGES if l["name"] not in UI_LABELS]
    if not only:
        return names, []
    lower = {n.lower(): n for n in names}
    picked, unknown = [], []
    for w in only:
        n = lower.get(w.strip().lower())
        (picked if n else unknown).append(n or w)
    return picked, unknown


def check(names):
    """揃っているか表示する。全部揃っていれば 0、足りなければ 1"""
    rows = [(n, ) + tuple(r[1:]) for n in names for r in ui_i18n.audit() if r[0] == n]
    short = [r for r in rows if r[2]]
    for n, have, miss in rows:
        _say(f"{'OK  ' if not miss else 'あと'+str(miss).rjust(3)+'個'}  {n}  ({have}個あり)")
    _say(f"\n{len(rows) - len(short)} / {len(rows)} 言語が揃っています。" + ("" if not short else f"（足りない言語: {len(short)}）"))
    return 0 if not short else 1


def run(argv, now=time.time, sleep=time.sleep):
    force = "--force" in argv
    only = []
    if "--only" in argv:
        i = argv.index("--only")
        only = [w for w in (argv[i + 1] if i + 1 < len(argv) else "").split(",") if w.strip()]
    names, unknown = _targets(only)
    if unknown:
        _say("見つからない言語: " + ", ".join(unknown) + "（英語名で。例: Thai, Dutch）")
        return 2
    if "--check" in argv:
        return check(names)
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        _say("環境変数 GEMINI_API_KEY が空です。PowerShell なら次のように設定してから、もう一度実行してください（キーはここに貼らないでください）。")
        _say('  $env:GEMINI_API_KEY = "（自分のキー）"')
        return 2

    import translator
    real = translator.translate_labels
    last = [0.0]

    def paced(labels, lang):
        wait = PACE_SEC - (now() - last[0])
        if wait > 0:
            sleep(wait)
        last[0] = now()
        return real(labels, lang)

    translator.translate_labels = paced   # ui_i18n.build_labels はここを呼ぶ
    made = 0
    busy_in_a_row = 0
    stopped = ""
    for name in names:
        if force:
            ui_i18n._mem.pop(name, None)
            try:
                os.remove(ui_i18n._path(name))
            except OSError:
                pass
        if not ui_i18n._missing(name):
            _say(f"skip   {name}（揃っています）")
            continue
        _say(f"make   {name} ...")
        done = False
        small = False   # 時間切れになったら、次は小分けにして頼む
        for attempt in range(TRIES):
            try:
                got, left = ui_i18n.build_labels(name, chunk=40, whole=not small)
                done = True
                break
            except Exception as e:
                key = getattr(e, "key", "") or type(e).__name__
                if key in ("err_quota", "err_api_key"):
                    stopped = ("今日の無料枠の上限に達しました。" if key == "err_quota"
                               else "APIキーが使えません（未設定・間違い・無効・削除済み）。")
                    break
                _say(f"  うまくいきませんでした（{key}）" + ("。小分けにしてやり直します" if key == "err_timeout" else ""))
                small = small or key == "err_timeout"
                if attempt + 1 < TRIES:
                    sleep(RETRY_WAIT_SEC * (attempt + 1))
        if stopped:
            break
        if not done:
            busy_in_a_row += 1
            _say("  この言語は今回あきらめて、次へ進みます")
            if busy_in_a_row >= STOP_AFTER_BUSY:
                stopped = "Google 側が混んでいて、続けて失敗しています。"
                break
            continue
        busy_in_a_row = 0
        made += got
        _say(f"  +{got}個を保存" + (f"（まだ {left}個足りません。もう一度実行すると続きから作ります）" if left else "（揃いました）"))

    _say("")
    code = check(names)
    if stopped:
        _say(f"\n{stopped}保存済みの分は残っています。" + ("日本時間の夕方（17時ごろ）以降" if "上限" in stopped else "しばらく（30分〜数時間）置いてから") + "、もう一度同じコマンドを実行してください（続きから作ります）。")
    elif code:
        _say("\n足りない言語があります。もう一度同じコマンドを実行してください（続きから作ります）。")
    else:
        _say("\nすべての言語が揃いました。ui_labels/ の変更を git add -A → commit → push してください。")
    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(run(sys.argv[1:]))
