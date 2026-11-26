"""Tailwind の CSS を作って static/vendor/tailwind.css に保存する（V13: 外部の読み込み＝CDN をなくすため）。

これまで画面は、開くたびに Tailwind の CDN（cdn.tailwindcss.com）から CSS を作っていました。アプリ（Android）や圏外でも画面が崩れないよう、
同じエンジン（tools/vendor/tailwind-play-cdn.js ＝ Tailwind v3 の CDN 版）をブラウザ（Chromium）で一度だけ動かし、できた CSS をそのまま保存します。
見た目はこれまでと同じです。

  python tools/build_css.py            CSS と、元になった文字の一覧のハッシュ（static/vendor/tailwind.manifest.json）を作り直す
  python tools/build_css.py --check    作り直しが要るか確かめる（API もブラウザも使わない。要るなら終了コード 1）

クラス名を足したり変えたりしたら、このツールを実行してください（忘れると、tests/test_v180.py が教えてくれます）。
必要なもの: Python の playwright（Chromium）。"""
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CDN_JS = os.path.join(ROOT, "tools", "vendor", "tailwind-play-cdn.js")
OUT = os.path.join(ROOT, "static", "vendor", "tailwind.css")
MANIFEST = os.path.join(ROOT, "static", "vendor", "tailwind.manifest.json")
SKIP_DIRS = {".git", "__pycache__", "tests", "tools", "ui_labels", "phrasebook", "vendor", "money", "node_modules", "android", "app-shell", "assets"}
TOKEN = re.compile(r"[A-Za-z0-9_\-:/.\[\]%#!&>()=,'\"*]+")
SINGLE = {  # ハイフンのない1語のクラス
    "flex", "grid", "block", "inline", "hidden", "relative", "absolute", "fixed", "sticky", "static", "truncate", "italic", "underline", "uppercase",
    "lowercase", "capitalize", "border", "rounded", "shadow", "ring", "blur", "grow", "shrink", "transition", "transform", "resize", "outline",
    "container", "visible", "invisible", "collapse", "contents", "table", "isolate", "antialiased", "underline", "overline", "filter",
}


def _clean(t):
    """前後の記号（引用符・>・, など）を落とす。括弧は、対になっていない分だけ落とす（w-[calc(1rem)] は残す）"""
    t = t.lstrip("\"'(<=")
    while t:
        if t[-1] in "\"'>,;":
            t = t[:-1]
        elif t[-1] == ")" and t.count(")") > t.count("("):
            t = t[:-1]
        elif t[-1] == "]" and t.count("]") > t.count("["):
            t = t[:-1]
        else:
            break
    return t


def _pieces(raw):
    """1つの文字から、クラス名の候補を取り出す（class="a b" の a や、'bg-x' のような引用符つきも拾う）"""
    out = {_clean(raw)}
    if "[" not in raw:
        out.update(_clean(x) for x in re.split(r"[\"'=>]", raw))
    return out


def candidates():
    """画面・JS・Python の中の、クラス名らしい文字（ハイフン・コロン・[ を含むもの、または1語のクラス）"""
    found = set()
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if not name.endswith((".html", ".js", ".py")):
                continue
            with open(os.path.join(base, name), encoding="utf-8") as f:
                for m in TOKEN.finditer(f.read()):
                    for t in _pieces(m.group(0)):
                        if t and (("-" in t or ":" in t or "[" in t) or t in SINGLE):
                            found.add(t)
    return sorted(found)


def digest(tokens):
    return hashlib.sha256("\n".join(tokens).encode("utf-8")).hexdigest()


def stale():
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            return json.load(f).get("sha256") != digest(candidates())
    except (OSError, ValueError):
        return True


def build():
    from playwright.sync_api import sync_playwright
    import tempfile
    tokens = candidates()
    with tempfile.TemporaryDirectory() as tmp:
        with open(CDN_JS, encoding="utf-8") as f, open(os.path.join(tmp, "cdn.js"), "w", encoding="utf-8") as g:
            g.write(f.read())
        # 全部の文字を、1つずつのクラスとして画面に置く（CDN 版が、使えるものだけ CSS にする）
        body = "".join('<i class="%s"></i>' % t.replace("&", "&amp;").replace('"', "&quot;") for t in tokens)
        with open(os.path.join(tmp, "page.html"), "w", encoding="utf-8") as f:
            f.write('<!doctype html><html><head><script src="cdn.js"></script></head><body>%s</body></html>' % body)
        with sync_playwright() as p:
            br = p.chromium.launch()
            pg = br.new_page()
            pg.goto("file://" + os.path.join(tmp, "page.html"))
            last, same = -1, 0
            for _ in range(60):          # 出力が増えなくなるまで待つ
                pg.wait_for_timeout(250)
                n = pg.evaluate("[...document.querySelectorAll('style')].reduce((a, s) => a + s.textContent.length, 0)")
                same = same + 1 if n == last else 0
                last = n
                if same >= 4 and n > 0:
                    break
            css = pg.evaluate("[...document.querySelectorAll('style')].map(s => s.textContent).join('\\n')")
            br.close()
    if len(css) < int(os.environ.get("CSS_MIN", "20000")):
        raise SystemExit("CSS が小さすぎます（%d文字）。CDN 版のエンジンが動かなかった可能性があります。" % len(css))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("/* Tailwind CSS v3（CDN 版のエンジンで作成）。直接は編集しない。tools/build_css.py で作り直す */\n" + css + "\n")
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump({"sha256": digest(tokens), "tokens": len(tokens), "css_bytes": len(css.encode("utf-8"))}, f, indent=1)
        f.write("\n")
    print("wrote %s (%d bytes, %d candidate tokens)" % (OUT, len(css.encode("utf-8")), len(tokens)))


if __name__ == "__main__":
    if "--check" in sys.argv:
        if stale():
            print("CSS が古いか、まだ作っていません。python tools/build_css.py を実行してください。")
            sys.exit(1)
        print("CSS は最新です。")
    else:
        build()
