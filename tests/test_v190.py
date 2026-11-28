"""v1.9.0: オフライン翻訳（試作）。日本語⇄英語を、端末の中（ブラウザ）で訳す。"""
import os
import re
import shutil
import subprocess

import pytest

from conftest import ROOT, start


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


NEW_LABELS = ["omt_group", "omt_intro", "omt_ja_en", "omt_en_ja", "omt_state_none", "omt_state_ready", "omt_state_loading", "omt_btn_get",
              "omt_btn_del", "omt_confirm_del", "omt_test_ph", "omt_run_ja_en", "omt_run_en_ja", "omt_running", "omt_unsupported",
              "omt_diag", "omt_diag_copy", "omt_copied", "omt_net", "omt_err"]


def test_version():
    import app as appmod
    assert appmod.APP_VERSION.startswith(("1.9.", "1.10.", "1.11.", "1.12."))


def test_labels_in_ja_and_en_and_other_languages_fall_back_to_english():
    import labels_en
    import labels_ja
    for k in NEW_LABELS:
        assert labels_ja.LABELS[k].strip() and labels_en.LABELS[k].strip(), k
    assert "MB" in labels_ja.LABELS["omt_intro"] and "MB" in labels_en.LABELS["omt_intro"]
    from ui_i18n import get_ui_labels
    assert get_ui_labels("Thai")["omt_group"] == labels_en.LABELS["omt_group"]      # まだ訳していない言語は、English で出る


def test_js_parts_short_and_loaded_before_pwa_in_both_pages():
    for n in ("offline_mt", "offline_mt_ui", "offline_mt_worker"):
        assert len(_read("static", "js", n + ".js").splitlines()) <= 200, n
    for tpl in (("templates", "components", "scripts.html"), ("templates", "offline.html")):
        order = re.findall(r"js/([a-z_0-9]+)\.js", _read(*tpl))
        assert order.index("offline_mt") + 1 == order.index("offline_mt_ui") < order.index("pwa"), tpl


def test_worker_pins_the_engine_and_uses_the_agreed_models():
    w = _read("static", "js", "offline_mt_worker.js")
    assert "transformers@3.5.2" in w                          # 版を固定（勝手に新しい版に変わらない）
    assert "'Xenova/opus-mt-ja-en'" in w and "'Xenova/opus-mt-en-jap'" in w
    assert "dtype: 'q8'" in w and "device: 'wasm'" in w       # 量子化版（約100MB）、iPhone でも動く WASM
    assert "allowRemoteModels = !offline" in w                # 圏外のときは、通信を試みない
    assert "type: 'module'" in _read("static", "js", "offline_mt.js")
    assert "encoder_model_quantized.onnx" in _read("static", "js", "offline_mt.js")
    assert "storage.persist" in _read("static", "js", "offline_mt.js")


def test_ui_never_uses_innerhtml_and_shows_text_only():
    for n in ("offline_mt", "offline_mt_ui", "offline_mt_worker"):
        assert "innerHTML" not in _read("static", "js", n + ".js"), n


def test_settings_has_the_card_after_translate_before_display(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    assert html.index('id="set-pron"') < html.index('id="omt-card"') < html.index('id="set-contrast"')
    for needle in ("オフライン翻訳（試作）", 'data-pair="ja-en"', 'data-pair="en-ja"', 'data-omt-run="ja-en"', 'id="omt-diag"', 'id="omt-copy"', "約100MB"):
        assert needle in html, needle
    assert html.count('class="omt-row ') == 17      # v1.11.2: 17方向。v1.11.0: 日本語⇄英語、中国語⇄英語、韓国語→英語
    off = c.get("/offline").get_data(as_text=True)
    assert 'id="omt-card"' in off and "js/offline_mt.js?v=" in off


def test_service_worker_keeps_the_engine_and_models_across_versions_and_caches_only_the_engine(env):
    app, *_ = env
    js = app.test_client().get("/sw.js").get_data(as_text=True)
    assert "const keep = [CACHE, MODE_CACHE, OMT_CACHE, 'transformers-cache']" in js
    assert "OMT_HOST = 'cdn.jsdelivr.net'" in js and "'/npm/@huggingface/transformers@'" in js and "'/npm/onnxruntime-web@'" in js
    assert "engineCache(req)" in js
    # 重いファイル（エンジン・モデル）は、ページを開いただけでは取らない（ボタンを押したときだけ）
    assert not any("onnx" in u or "wasm" in u for u in re.findall(r'"(/static/[^"]+)"', js.split("const PRECACHE")[1].split("self.addEventListener")[0]))


def test_cdn_is_only_in_the_worker_service_worker_and_the_notice_text():
    hits = []
    for base, _d, files in os.walk(ROOT):
        if any(x in base for x in (".git", "node_modules", "__pycache__", os.sep + "tests", os.sep + "android")):
            continue
        for n in files:
            if n.endswith((".js", ".html", ".css", ".py", ".json")):
                p = os.path.join(base, n)
                if "cdn.jsdelivr.net" in open(p, encoding="utf-8", errors="ignore").read():
                    hits.append(os.path.relpath(p, ROOT).replace(os.sep, "/"))
    assert sorted(hits) == ["labels_en.py", "labels_ja.py", "static/js/offline_mt_worker.js", "static/js/offline_ocr.js", "templates/sw.js"]   # 手書きの2つは、利用者に知らせる文章だけ


@pytest.mark.skipif(shutil.which("node") is None, reason="node がない")
def test_sentence_splitter_keeps_decimals_and_endings():
    js = _read("static", "js", "offline_mt_worker.js")
    fn = re.search(r"function pieces\(line\) \{.*?\n\}", js, re.S).group(0)
    code = fn + """
    const t = (s) => JSON.stringify(pieces(s).map(x => x.trim()));
    console.log(t('こんにちは。元気ですか？はい！'));
    console.log(t('Hello world. I paid 3.14 dollars! ok'));
    console.log(t('no end'));"""
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout.splitlines()
    assert out[0] == '["こんにちは。","元気ですか？","はい！"]'
    assert out[1] == '["Hello world.","I paid 3.14 dollars!","ok"]'
    assert out[2] == '["no end"]'


def test_docker_image_does_not_get_tooling_and_gitignore_ok():
    assert "node_modules" in _read(".dockerignore") and "node_modules/" in _read(".gitignore")
