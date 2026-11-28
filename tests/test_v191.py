"""v1.9.1: オフライン画面（/offline）に、ダウンロード済みモデルで訳すテキスト翻訳タブ。"""
import os
import re

from conftest import ROOT, start

LABELS = ["ot_hint", "ot_dir_auto", "ot_ph", "ot_run", "ot_need", "ot_open", "ot_err"]


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def test_version():
    import app as appmod
    assert tuple(int(x) for x in appmod.APP_VERSION.split(".")) >= (1, 9, 1)


def test_labels_ja_en_and_fallback():
    import labels_en
    import labels_ja
    for k in LABELS:
        assert labels_ja.LABELS[k].strip() and labels_en.LABELS[k].strip(), k
    from ui_i18n import get_ui_labels
    assert get_ui_labels("Thai")["ot_run"] == labels_en.LABELS["ot_run"]


def test_offline_page_has_the_tab_above_the_history_and_normal_page_does_not(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    off = c.get("/offline").get_data(as_text=True)
    assert off.index('id="omt-tab"') < off.index('id="page-title"')
    for needle in ('id="omt-tab-in"', 'id="omt-tab-run"', 'data-dir="auto"', 'data-dir="ja-en"', 'data-dir="en-ja"', 'id="omt-tab-need"', 'id="omt-tab-open"', 'id="omt-tab-copy"'):
        assert needle in off, needle
    assert 'id="omt-tab"' not in c.get("/").get_data(as_text=True)


def test_script_order_tab_after_ui_before_pwa():
    order = re.findall(r"js/([a-z_0-9]+)\.js", _read("templates", "offline.html"))
    assert order.index("offline_mt") < order.index("offline_mt_ui") < order.index("offline_mt_tab") < order.index("pwa")


def test_tab_js_is_short_safe_and_uses_the_agreed_pieces():
    js = _read("static", "js", "offline_mt_tab.js")
    assert len(js.splitlines()) <= 200
    assert "innerHTML" not in js
    for needle in ("OfflineMT.isDownloaded", "OfflineText.translate", "addHistory", "omt-changed", "setHistFilter('settings')"):
        assert needle in js, needle
    assert "omt-changed" in _read("static", "js", "offline_mt_ui.js")


def test_service_worker_precaches_the_new_script(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    assert "/static/js/offline_mt_tab.js" in c.get("/sw.js").get_data(as_text=True)
