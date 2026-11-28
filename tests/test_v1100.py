"""v1.10.0: 翻訳メモリー、圏外の自動切り替え（通常の「テキスト」）、オフライン翻訳モデルの自動ダウンロード。"""
import os
import re

from conftest import ROOT, start

LABELS = ["omt_auto", "omt_auto_note", "tm_use", "tm_note", "tm_count", "tm_clear", "tm_confirm_clear",
          "lo_via_memory", "lo_via_similar", "lo_via_mixed", "lo_via_model", "lo_msg_nopair", "lo_msg_nomodel", "lo_msg_unsupported", "lo_msg_failed"]


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def test_version():
    import app as appmod
    assert tuple(int(x) for x in appmod.APP_VERSION.split(".")) >= (1, 10, 0)


def test_labels_ja_en_and_fallback():
    import labels_en
    import labels_ja
    for k in LABELS:
        assert labels_ja.LABELS[k].strip() and labels_en.LABELS[k].strip(), k
    assert "{n}" in labels_ja.LABELS["tm_count"] and "{n}" in labels_en.LABELS["tm_count"]
    assert "{s}" in labels_ja.LABELS["lo_via_similar"] and "{s}" in labels_en.LABELS["lo_via_similar"]
    from ui_i18n import get_ui_labels
    assert get_ui_labels("Thai")["tm_use"] == labels_en.LABELS["tm_use"]


def test_js_parts_short_and_free_of_innerhtml():
    for n in ("tm", "tm_ui", "offline_text", "offline_mt_tab", "offline_mt_ui"):
        js = _read("static", "js", n + ".js")
        assert len(js.splitlines()) <= 200, n
        assert "innerHTML" not in js, n


def test_script_order_in_both_pages():
    main = re.findall(r"js/([a-z_0-9]+)\.js", _read("templates", "components", "scripts.html"))
    off = re.findall(r"js/([a-z_0-9]+)\.js", _read("templates", "offline.html"))
    for order in (main, off):
        assert order.index("settings") < order.index("tm") < order.index("history")                    # tm は settings の後（loadSettings を使う）
        assert order.index("offline_mt_ui") < order.index("tm_ui") < order.index("offline_text") < order.index("pwa")
        assert order.index("offline_mt") + 1 == order.index("offline_mt_ui")
    assert off.index("offline_text") < off.index("offline_mt_tab") < off.index("pwa")


def test_memory_is_filled_from_online_results_and_corrections_only():
    s = _read("static", "js", "storage.js")
    assert "!entry.offline && ['text', 'voice', 'conversation']" in s and "tmAdd(entry.src, entry.out, entry.tgt, false)" in s
    assert "tmAdd(src, out, toLang, true)" in s
    for js in ("offline_text", "offline_mt_tab"):
        assert "offline: true" in _read("static", "js", js + ".js")      # 端末内で訳した文は、メモリーに入れない


def test_main_page_has_the_local_result_card_and_settings_switches(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    html = c.get("/").get_data(as_text=True)
    for needle in ('id="local-result"', 'id="local-msg"', 'id="local-out"', 'data-local="speak"', 'data-local="copy"',
                   'id="set-tm"', 'id="set-auto-model"', 'id="tm-count"', 'id="tm-clear"', "js/tm.js?v=", "js/offline_text.js?v="):
        assert needle in html, needle
    assert html.index('id="set-tm"') > html.index('id="omt-card"')
    off = c.get("/offline").get_data(as_text=True)
    assert 'id="set-tm"' in off and 'id="local-result"' not in off and "js/tm.js?v=" in off


def test_settings_defaults_memory_on_auto_download_off():
    js = _read("static", "js", "settings.js")
    assert "tm: true" in js and "autoModel: false" in js


def test_auto_download_rules_in_the_ui_script():
    js = _read("static", "js", "offline_mt_ui.js")
    for needle in ("loadSettings().autoModel", "navigator.onLine === false", "c.type === 'cellular'", "saveData", "sessionStorage", "omt-auto-on"):
        assert needle in js, needle


def test_service_worker_precaches_the_new_scripts(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    sw = c.get("/sw.js").get_data(as_text=True)
    for n in ("tm", "tm_ui", "offline_text"):
        assert f"/static/js/{n}.js" in sw, n
