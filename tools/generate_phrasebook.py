"""手書きデータが無い言語のフレーズ集（旅行の定型文81個）を Gemini で作るツール。1言語＝API 1回。

  python tools/generate_phrasebook.py                      足りない言語だけを作る（途中で止まっても、次は続きから）
  python tools/generate_phrasebook.py --check              API を使わず、どの言語にフレーズ集があるか確認（足りなければ終了コード 1）
  python tools/generate_phrasebook.py --only Thai,Dutch    言語を指定（英語名。カンマ区切り）
  python tools/generate_phrasebook.py --force --only Thai  指定した言語を作り直す（--only なしの --force は、足りない言語だけ）
  python tools/generate_phrasebook.py --max-calls 10       1回の実行で使う API の呼び出しの上限（既定 15。失敗も数える）
  python tools/generate_phrasebook.py --no-check           最初の「混雑チェック」を省く

APIキー・無料枠・混雑チェックの考え方は、tools/generate_ui_labels.py と同じです（キーは実行すると隠し入力で聞かれ、ファイルには保存しません。
環境変数 GEMINI_API_KEY に入れてある場合は聞かれません。無料枠は「モデルごとに 1分5回・1日20回」程度なので、1回ごとに約13秒待ちます）。
作った JSON は static/phrasebook/ に1言語ずつ保存されます（コミットして使ってください）。
機械翻訳なので、ネイティブの方に確認してもらうと安心です（JSON を直接直して構いません）。"""
import getpass
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate_ui_labels as g  # noqa: E402  環境変数の既定値（長めの待ち時間）と、止まり方の部品を共有する

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from languages import LANGUAGES  # noqa: E402
from phrasebook_data import CATEGORIES  # noqa: E402

OUT = os.path.join(ROOT, "static", "phrasebook")
TRIES = 2
STOP_AFTER_BUSY = 2
SYSTEM = ("You are a professional translator for a travel phrasebook. Respond ONLY with a JSON object that has "
          "exactly the same keys as the input, with every value translated naturally and politely, the way a "
          "native speaker would say it to a stranger.")


def _path(lang):
    return os.path.join(OUT, lang["code"].lower() + ".json")


def _targets(only):
    """作る言語（ja・en は index.json にあるので対象外のまま。ファイルが無い言語だけ）"""
    langs = [l for l in LANGUAGES if not os.path.exists(_path(l))]
    if not only:
        return langs, []
    lower = {l["name"].lower(): l for l in LANGUAGES}
    picked, unknown = [], []
    for w in only:
        l = lower.get(w.strip().lower())
        (picked if l else unknown).append(l or w)
    return picked, unknown


def make(lang):
    """1言語ぶんを API 1回で作って保存する。足りない・形が違うときは例外（保存しない）"""
    import translator
    src = {p[0]: p[2] for c in CATEGORIES for p in c[3]}
    prompt = (f"Translate every value of this JSON object from English into {lang['name']}. Keep the keys. "
              "Keep each phrase short and natural.\n" + json.dumps(src, ensure_ascii=False))
    data = translator._loads_object(translator._call([prompt], system=SYSTEM)) or {}
    out = {k: str(data[k]).strip() for k in src if isinstance(data.get(k), str) and str(data[k]).strip()}
    if len(out) != len(src):
        raise RuntimeError(f"incomplete: {len(out)}/{len(src)}")
    os.makedirs(OUT, exist_ok=True)
    with open(_path(lang), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")


def check(langs):
    have = [l for l in langs if os.path.exists(_path(l))]
    for l in langs:
        g._say(f"{'OK  ' if l in have else 'なし'}  {l['name']}")
    g._say(f"\n{len(have)} / {len(langs)} 言語にフレーズ集があります。")
    return 0 if len(have) == len(langs) else 1


def _ask_key(ask):
    if os.environ.get("GEMINI_API_KEY", "").strip():
        return True
    if ask is None and sys.stdin.isatty():
        ask = getpass.getpass
    key = ""
    if ask:
        g._say("APIキーを貼り付けて Enter を押してください（貼り付けても画面には何も表示されません。それで正しい動作です）。")
        try:
            key = (ask("APIキー: ") or "").strip()
        except (EOFError, KeyboardInterrupt):
            key = ""
    if not key:
        g._say("APIキーが入力されませんでした。もう一度実行して、聞かれたらキーを貼り付けてください。")
        return False
    os.environ["GEMINI_API_KEY"] = key   # このツールの実行中だけ。ファイルには保存しない
    return True


def run(argv, now=time.time, sleep=time.sleep, ask=None):
    only = []
    if "--only" in argv:
        i = argv.index("--only")
        only = [w for w in (argv[i + 1] if i + 1 < len(argv) else "").split(",") if w.strip()]
    max_calls = g.MAX_CALLS
    if "--max-calls" in argv:
        i = argv.index("--max-calls")
        try:
            max_calls = max(1, int(argv[i + 1]))
        except (IndexError, ValueError):
            g._say("--max-calls には回数を数字で指定してください（例: --max-calls 10）")
            return 2
    force = "--force" in argv
    todo, unknown = _targets(only)
    if unknown:
        g._say("見つからない言語: " + ", ".join(unknown) + "（英語名で。例: Thai, Dutch）")
        return 2
    if "--check" in argv:
        return check(todo if only else list(LANGUAGES))
    if not force:
        todo = [l for l in todo if not os.path.exists(_path(l))]
    if not todo:
        g._say("作る言語はありません（すべて揃っています）。")
        return 0
    if not _ask_key(ask):
        return 2

    import translator
    real = translator._generate
    last, calls = [0.0], [0]

    def counted(parts, system=None):
        if calls[0] >= max_calls:
            raise g._OutOfBudget()
        wait = g.PACE_SEC - (now() - last[0])
        if wait > 0:
            sleep(wait)
        last[0] = now()
        calls[0] += 1
        return real(parts, system=system)

    translator._generate = counted
    made, kind, key = [], "", ""
    try:
        if "--no-check" not in argv:
            g._say("Google が空いているか、短い依頼を1回だけ試します ...")
            kind, key = g._probe()
            g._say("  混雑チェック: " + ("失敗（" + key + "）" if kind else "OK。フレーズ集づくりを始めます。"))
        busy = 0
        for lang in ([] if kind else todo):
            g._say(f"make   {lang['name']} ...")
            done = False
            for attempt in range(TRIES):
                try:
                    make(lang)
                    done = True
                    break
                except Exception as e:
                    key = getattr(e, "key", "") or type(e).__name__
                    if g._kind_of(key) in ("quota", "key", "budget"):
                        kind = g._kind_of(key)
                        break
                    g._say(f"  うまくいきませんでした（{key}）")
                    if attempt + 1 < TRIES:
                        sleep(g.RETRY_WAIT_SEC * (attempt + 1))
            if kind:
                break
            if not done:
                busy += 1
                g._say("  この言語は今回あきらめて、次へ進みます")
                if busy >= STOP_AFTER_BUSY:
                    kind = "busy"
                    break
                continue
            busy = 0
            made.append(lang["name"])
            g._say("  保存しました")
    finally:
        translator._generate = real

    g._say(f"\nAPI の呼び出し: {calls[0]}回（上限 {max_calls}回）")
    g._say("今回できた言語: " + (", ".join(made) if made else "なし"))
    code = check(todo)
    if kind:
        why, then = g._stop_text(kind, key, max_calls)
        g._say(f"\n{why}{then}")
        return code
    if code:
        g._say("\n足りない言語があります。もう一度同じコマンドを実行してください（続きから作ります）。")
    else:
        g._say("\nすべての言語が揃いました。static/phrasebook/ の変更を git add -A → commit → push してください。")
    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sys.exit(run(sys.argv[1:]))
