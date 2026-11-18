"""V12.11: 画面文言とJSを別ファイルに分けただけで、動きは変わっていないことの確認"""
import glob
import os
import re
import shutil
import subprocess

import pytest

from conftest import ROOT

JS_DIR = os.path.join(ROOT, "static", "js")
MONEY_PARTS = ["money", "money_start", "money_where", "money_view"]
OVERLAY_PARTS = ["overlay", "overlay_zoom", "overlay_save", "overlay_boot"]


def _lines(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return len(f.read().splitlines())


def test_ui_labels_moved_but_same_objects():
    import languages
    import labels_en
    import labels_ja
    assert languages.UI_LABELS["Japanese"] is labels_ja.LABELS
    assert languages.UI_LABELS["English"] is labels_en.LABELS
    assert set(labels_ja.LABELS) == set(labels_en.LABELS)          # キーは日英でそろっている
    assert set(languages.UI_LABELS) == {"Japanese", "English"}
    assert len(labels_ja.LABELS) >= 250
    # From / To は、どの表示言語でも固定（ここは変えていない）
    lab = languages.get_ui_labels("Japanese")
    assert (lab["source_label"], lab["target_label"], lab["target_label_short"]) == ("From", "To", "To")
    # 足りないキーは English で補う
    assert languages.get_ui_labels("French")["title"] == labels_en.LABELS["title"]


def test_languages_py_has_no_label_text_and_is_short():
    assert _lines("languages.py") <= 200
    src = open(os.path.join(ROOT, "languages.py"), encoding="utf-8").read()
    assert "AI万能翻訳アプリ" not in src and "Search languages" not in src
    assert "from labels_ja import" in src and "from labels_en import" in src


def test_js_parts_exist_short_and_loaded_in_order(env):
    for n in MONEY_PARTS + OVERLAY_PARTS:
        p = os.path.join(JS_DIR, n + ".js")
        assert os.path.exists(p), n
        assert _lines("static", "js", n + ".js") <= 200, n
    assert not os.path.exists(os.path.join(JS_DIR, "money_old.js"))
    app, *_ = env
    c = app.test_client()
    tpl = open(os.path.join(ROOT, "templates", "components", "scripts.html"), encoding="utf-8").read()
    order = re.findall(r"js/([a-z_]+)\.js", tpl)
    for group in (MONEY_PARTS, OVERLAY_PARTS):
        idx = [order.index(n) for n in group]
        assert idx == sorted(idx) and idx == list(range(idx[0], idx[0] + 4)), group   # 連続して、この順
    assert order.index("overlay_boot") < order.index("pdf") < order.index("study")
    assert order.index("money_view") < order.index("app")


def test_offline_page_and_sw_include_every_part(env):
    app, *_ = env
    c = app.test_client()
    off = c.get("/offline").get_data(as_text=True)
    sw = c.get("/sw.js").get_data(as_text=True)
    for n in MONEY_PARTS:
        assert f"js/{n}.js" in off, n                      # オフライン画面の通貨タブも動く
    for n in MONEY_PARTS + OVERLAY_PARTS:
        assert f"js/{n}.js" in sw, n                       # 端末に保存される（オフラインで読める）


def test_no_duplicate_top_level_names_across_scripts():
    """読み込む全JSで、最上位の関数・const・let の名前が重複していない（重複するとページ全体が動かなくなる）"""
    tpl = open(os.path.join(ROOT, "templates", "components", "scripts.html"), encoding="utf-8").read()
    seen = {}
    for n in re.findall(r"js/([a-z_]+)\.js", tpl):
        for line in open(os.path.join(JS_DIR, n + ".js"), encoding="utf-8"):
            m = re.match(r"(?:async\s+)?function\s+(\w+)|(?:const|let|var)\s+(\w+)", line)
            if m:
                name = m.group(1) or m.group(2)
                assert name not in seen or name in ("__pendingTab",), (name, seen.get(name), n)
                seen[name] = n


@pytest.mark.skipif(not shutil.which("node"), reason="node がない")
def test_every_js_file_parses():
    for p in sorted(glob.glob(os.path.join(JS_DIR, "*.js"))):
        r = subprocess.run(["node", "--check", p], capture_output=True, text=True)
        assert r.returncode == 0, (p, r.stderr)


def test_version_label(env):
    app, *_ = env
    assert app.config.get("TESTING") is not None
    import app as appmod
    assert appmod.APP_VERSION == "12.11"
