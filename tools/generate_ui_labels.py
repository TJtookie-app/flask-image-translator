"""画面の文言（日本語・英語以外の全言語）を作る・確認するツール。

  python tools/generate_ui_labels.py            足りない文言だけを Gemini で翻訳して ui_labels/ に保存（途中で止まっても、次は続きから）
  python tools/generate_ui_labels.py --check    API を使わず、全言語が揃っているか確認（揃っていなければ終了コード 1）
  python tools/generate_ui_labels.py --only Thai,Dutch    言語を指定（英語名。カンマ区切り）
  python tools/generate_ui_labels.py --force --only Thai  指定した言語を作り直す（--only なしの --force は全言語）
  python tools/generate_ui_labels.py --max-calls 10       1回の実行で使う API の呼び出しの上限（既定 15。失敗した呼び出しも数える）
  python tools/generate_ui_labels.py --no-check           最初の「混雑チェック」を省く（既定では、本番の前に短い依頼を1回だけ試す）

軽いモデル: 実行前に、軽いモデルの指定（GEMINI_MODEL に "lite" を含む名前）を確認します。ターミナルを開き直すと指定が消え、公開サイトと同じモデルで動いてサイトの枠を使い切るため、
  指定がなければキーを聞く前に止まり、設定のしかたを表示します（わかっていて使うときだけ --prod-model）。
APIキー: 実行すると「APIキーを貼り付けて Enter」と聞かれます。貼り付けても画面には何も出ません（それで正しい）。
  キーは、このツールが動いている間だけ使い、ファイルには保存しません。環境変数 GEMINI_API_KEY に入れてある場合は、聞かれません。
混雑チェック: 本番の前に、ごく短い依頼を1回だけ試します。Google が混んでいれば、そこで止まります（使う呼び出しは1〜2回だけ。終了コード 3）。
無料枠は「プロジェクトごと・モデルごとに 1分5回・1日20回」程度です。1回ごとに約13秒待ち、1日の上限か、この実行の上限（--max-calls）に達したら、保存済みの分を残して止まります。
**同じプロジェクトのキーは、公開中のサイトと同じ枠を使います。** 文言づくりには、別のプロジェクトで作ったキーを使うと、サイトの枠を減らしません。
1日の上限に達したときは、日本時間の夕方（17時ごろ）に戻ります。別のプロジェクトのキーなら、すぐ続けられます（続きから作ります）。
"""
import getpass
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 文言は文字数が多く、アプリ本体の待ち時間（25秒）では足りない。このツールの中だけ長くする（本体の設定は変えない）
os.environ.setdefault("GEMINI_TEXT_TIMEOUT", "150")
os.environ.setdefault("GEMINI_ATTEMPTS", "2")

import ui_i18n  # noqa: E402
from gemini_errors import TranslationError  # noqa: E402
from languages import LANGUAGES, UI_LABELS  # noqa: E402

PACE_SEC = float(os.environ.get("LABEL_PACE_SEC", "13"))   # API の呼び出しの間隔（無料枠は1分5回）
MAX_CALLS = int(os.environ.get("LABEL_MAX_CALLS", "15"))   # 1回の実行で使う API 呼び出しの上限（失敗も数える。無料枠は1日20回）
RETRY_WAIT_SEC = float(os.environ.get("LABEL_RETRY_WAIT_SEC", "30"))   # 混雑・時間切れのとき、同じ言語をやり直すまでの待ち（回数をかけて長くなる）
TRIES = 2             # 1言語あたりの挑戦回数（混んでいるときに、呼び出しを使い切らないよう少なめ）
STOP_AFTER_BUSY = 2   # 続けてこれだけの言語が混雑・時間切れで失敗したら、Google側が混んでいるとみて止まる
BUSY_KEYS = {"err_timeout", "err_overloaded", "err_connection"}
PROBE = {"ping": "Hello"}   # 混雑チェック用の、ごく短い依頼

BUSY_HINT = "Google 側が混んでいます。1〜2時間あけて、もう一度同じコマンドを実行してください（日本時間の夜〜朝は混みやすい傾向があります。昼〜夕方のほうが通りやすいです）。"


def model_guard(argv):
    """軽いモデルが指定されていないとき（ターミナルを開き直すと設定が消える）は、サイトと同じモデルを使って
    サイトの無料枠を使い切らないよう、キーを聞く前に止める。わかっていて使うときだけ --prod-model。"""
    model = os.environ.get("GEMINI_MODEL", "").strip()
    if "--prod-model" in argv or "lite" in model.lower():
        return True
    _say("止めました。軽いモデルの指定が見つかりません（ターミナルを開き直すと消えます）。")
    _say("このまま動かすと、公開サイトと同じモデルを使い、サイトの1日の枠を使い切るおそれがあります。")
    _say("次の2行を実行してから、もう一度同じコマンドを実行してください。")
    _say('  $env:GEMINI_MODEL = "gemini-3.1-flash-lite"')
    _say('  $env:GEMINI_FALLBACK_MODEL = "gemini-3.5-flash-lite"')
    _say("（サイトと同じモデルで動かしてよいときだけ、--prod-model を付けます）")
    return False


class _OutOfBudget(TranslationError):
    """この実行の呼び出し上限に達した（Gemini のエラーではない）"""

    def __init__(self):
        super().__init__("err_budget")


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


def check(names, brief=False):
    """揃っているか表示する。全部揃っていれば 0、足りなければ 1。brief=True なら一覧は出さず、数だけ"""
    rows = [(n, ) + tuple(r[1:]) for n in names for r in ui_i18n.audit() if r[0] == n]
    short = [r for r in rows if r[2]]
    if not brief:
        for n, have, miss in rows:
            _say(f"{'OK  ' if not miss else 'あと'+str(miss).rjust(3)+'個'}  {n}  ({have}個あり)")
        _say("")
    _say(f"{len(rows) - len(short)} / {len(rows)} 言語が揃っています。" + ("" if not short else f"（足りない言語: {len(short)}）"))
    return 0 if not short else 1


def _kind_of(key):
    """エラーの種類を、止まり方の種類に分ける"""
    if key == "err_quota":
        return "quota"
    if key == "err_budget":
        return "budget"
    if key in ("err_api_key", "err_no_key"):
        return "key"
    if key in BUSY_KEYS:
        return "busy"
    return "other"


def _probe():
    """本番の前に、ごく短い依頼を1回だけ試す。空いていれば ("", "")、止めるなら (止まり方の種類, エラー名)"""
    import translator
    try:
        translator.translate_labels(dict(PROBE), "English")
        return "", ""
    except Exception as e:
        key = getattr(e, "key", "") or type(e).__name__
        kind = _kind_of(key)
        return ("" if kind == "other" else kind), key   # 混雑・枠・キーの問題だけ止める。形式の不一致などは、本番で扱う


def _stop_text(kind, key, max_calls):
    """止まった理由（1行）と、次にすること"""
    if kind == "quota":
        return ("今日の無料枠の上限に達しました。",
                "日本時間の夕方（17時ごろ）に枠が戻ります。別のプロジェクトで作ったキーなら、すぐ続けられます。保存済みの分は残っています。")
    if kind == "budget":
        return (f"この実行の呼び出し上限（{max_calls}回）まで使いました。",
                "無料枠が残っていれば、同じコマンドをすぐ実行できます（続きから作ります）。1日の上限（1モデル20回ほど）に近いときは、夕方（17時ごろ）以降か、別のプロジェクトのキーで。保存済みの分は残っています。")
    if kind == "key":
        return ("APIキーが使えません（未設定・間違い・無効・削除済み）。",
                "キーを確かめて、もう一度実行してください。")
    if kind == "busy":
        return ("Google 側が混んでいて、失敗が続いています。", BUSY_HINT + "保存済みの分は残っています。")
    return (f"予期しないエラーで止まりました（{key}）。", "この表示を、そのまま送ってください。保存済みの分は残っています。")


def run(argv, now=time.time, sleep=time.sleep, ask=None):
    force = "--force" in argv
    only = []
    if "--only" in argv:
        i = argv.index("--only")
        only = [w for w in (argv[i + 1] if i + 1 < len(argv) else "").split(",") if w.strip()]
    max_calls = MAX_CALLS
    if "--max-calls" in argv:
        i = argv.index("--max-calls")
        try:
            max_calls = max(1, int(argv[i + 1]))
        except (IndexError, ValueError):
            _say("--max-calls には回数を数字で指定してください（例: --max-calls 10）")
            return 2
    names, unknown = _targets(only)
    if unknown:
        _say("見つからない言語: " + ", ".join(unknown) + "（英語名で。例: Thai, Dutch）")
        return 2
    if "--check" in argv:
        return check(names)
    if not force and not any(ui_i18n._missing(n) for n in names):
        _say("作る言語はありません（すべて揃っています）。")
        return check(names, brief=True)
    if not model_guard(argv):
        return 2
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        if ask is None and sys.stdin.isatty():
            ask = getpass.getpass
        key = ""
        if ask:
            _say("APIキーを貼り付けて Enter を押してください（貼り付けても画面には何も表示されません。それで正しい動作です）。")
            try:
                key = (ask("APIキー: ") or "").strip()
            except (EOFError, KeyboardInterrupt):
                key = ""
        if not key:
            _say("APIキーが入力されませんでした。もう一度実行して、聞かれたらキーを貼り付けてください。")
            return 2
        os.environ["GEMINI_API_KEY"] = key   # このツールの実行中だけ。ファイルには保存しない

    import translator
    real = translator._generate   # 本当の API 呼び出し1回。アプリ本体の再挑戦・予備モデルへの切り替えも、ここを通る
    last = [0.0]
    calls = [0]

    def counted(parts, system=None):
        if calls[0] >= max_calls:
            raise _OutOfBudget()
        wait = PACE_SEC - (now() - last[0])
        if wait > 0:
            sleep(wait)
        last[0] = now()
        calls[0] += 1
        return real(parts, system=system)

    translator._generate = counted
    made_names = []
    kind = key = ""
    try:
        if "--no-check" not in argv:
            _say("Google が空いているか、短い依頼を1回だけ試します ...")
            kind, key = _probe()
            if kind:
                _say("  混雑チェック: 失敗（" + key + "）")
            else:
                _say("  混雑チェック: OK。文言づくりを始めます。")
        busy_in_a_row = 0
        for name in ([] if kind else names):
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
                    if _kind_of(key) in ("quota", "key", "budget"):
                        kind = _kind_of(key)
                        break
                    _say(f"  うまくいきませんでした（{key}）" + ("。小分けにしてやり直します" if key == "err_timeout" else ""))
                    small = small or key == "err_timeout"
                    if attempt + 1 < TRIES:
                        sleep(RETRY_WAIT_SEC * (attempt + 1))
            if kind:
                break
            if not done:
                busy_in_a_row += 1
                _say("  この言語は今回あきらめて、次へ進みます")
                if busy_in_a_row >= STOP_AFTER_BUSY:
                    kind = "busy"
                    break
                continue
            busy_in_a_row = 0
            made_names.append(name)
            _say(f"  +{got}個を保存" + (f"（まだ {left}個足りません。もう一度実行すると続きから作ります）" if left else "（揃いました）"))

    finally:
        translator._generate = real

    _say(f"\nAPI の呼び出し: {calls[0]}回（上限 {max_calls}回）")
    _say("今回できた言語: " + (", ".join(made_names) if made_names else "なし"))
    probe_stopped = bool(kind) and not made_names and calls[0] <= 2 and "--no-check" not in argv
    code = check(names, brief=probe_stopped)
    if kind:
        why, then = _stop_text(kind, key, max_calls)
        _say(f"\n{why}{then}")
        return 3 if probe_stopped and kind == "busy" else code
    if code:
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
