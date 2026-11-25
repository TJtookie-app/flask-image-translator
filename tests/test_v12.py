"""V12: 翻訳が遅いときの案内・今日の残り回数・「1日」の区切り・スマホの見た目（文字色・大きさ・押しやすさ）"""
import os
import re
from datetime import datetime, timezone

import pytest

from conftest import start

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


def all_front_files():
    out = []
    for base in ("templates", os.path.join("templates", "components"), os.path.join("static", "js")):
        d = os.path.join(ROOT, base)
        out += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith((".html", ".js"))]
    return out


# ---------------- 今日の残り回数 ----------------

def test_quota_endpoint_shows_remaining_for_small_limits(env):
    app, _, _, mp = env
    mp.setenv("SITE_DAILY_LIMIT", "16")
    c = app.test_client(); start(c)
    q = c.get("/api/quota").get_json()
    assert q == {"limit": 16, "used": 0, "remaining": 16, "show": True}
    body = {"text": "hi", "source": "English", "target": "Japanese"}
    for _ in range(2):
        assert c.post("/api/translate-text", json=body).status_code == 200
    q = c.get("/api/quota").get_json()
    assert q["used"] == 2 and q["remaining"] == 14


def test_quota_hidden_when_limit_is_large(env):
    app, _, _, mp = env
    c = app.test_client()
    q = c.get("/api/quota").get_json()
    assert q["limit"] == 3000 and q["show"] is False
    mp.setenv("QUOTA_SHOW_BELOW", "5000")
    assert c.get("/api/quota").get_json()["show"] is True


def test_quota_check_does_not_use_up_quota(env):
    app, _, _, mp = env
    from limits import limiter
    mp.setenv("SITE_DAILY_LIMIT", "10")
    c = app.test_client()
    for _ in range(40):
        c.get("/api/quota")
    assert limiter.site_day == 0
    r = c.get("/api/quota")
    assert r.headers["Cache-Control"] == "no-store"


def test_quota_reaches_zero_and_never_negative(env):
    app, _, _, mp = env
    mp.setenv("SITE_DAILY_LIMIT", "2")
    c = app.test_client(); start(c)
    body = {"text": "hi", "source": "English", "target": "Japanese"}
    for _ in range(4):
        c.post("/api/translate-text", json=body)
    q = c.get("/api/quota").get_json()
    assert q["remaining"] == 0 and q["used"] == 2


# ---------------- 「1日」の区切り（Gemini の無料枠に合わせる） ----------------

def test_limit_day_follows_pacific_time(monkeypatch):
    import limits
    monkeypatch.delenv("LIMIT_DAY_TZ", raising=False)
    d = lambda y, m, dd, h, mi: limits._limit_day(datetime(y, m, dd, h, mi, tzinfo=timezone.utc))
    assert d(2026, 11, 16, 7, 59) == "2026-11-15" and d(2026, 11, 16, 8, 0) == "2026-11-16"   # 冬: UTC 8:00（日本時間 17:00）
    assert d(2026, 7, 16, 6, 59) == "2026-07-15" and d(2026, 7, 16, 7, 0) == "2026-07-16"      # 夏: UTC 7:00（日本時間 16:00）


def test_limit_day_timezone_can_be_changed_and_has_fallback(monkeypatch):
    import limits
    monkeypatch.setenv("LIMIT_DAY_TZ", "Asia/Tokyo")
    assert limits._limit_day(datetime(2026, 11, 16, 14, 59, tzinfo=timezone.utc)) == "2026-11-16"
    assert limits._limit_day(datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc)) == "2026-11-17"
    monkeypatch.setenv("LIMIT_DAY_TZ", "No/Such_Zone")          # 読み込めないときは UTC-8
    assert limits._limit_day(datetime(2026, 11, 16, 7, 59, tzinfo=timezone.utc)) == "2026-11-15"
    assert limits._limit_day(datetime(2026, 11, 16, 8, 0, tzinfo=timezone.utc)) == "2026-11-16"


def test_counters_reset_when_the_day_changes(env):
    _, _, _, mp = env
    import limits
    mp.setenv("SITE_DAILY_LIMIT", "2")
    mp.setattr(limits, "_limit_day", lambda now=None: "D1")
    limits.limiter.reset()
    assert limits.limiter.check("1.1.1.1") is None and limits.limiter.check("1.1.1.1") is None
    assert limits.limiter.check("1.1.1.1") == "err_daily"
    assert limits.limiter.quota()["remaining"] == 0
    mp.setattr(limits, "_limit_day", lambda now=None: "D2")
    assert limits.limiter.quota()["remaining"] == 2
    assert limits.limiter.check("1.1.1.1") is None


# ---------------- 画面の部品 ----------------

def test_labels_exist_in_ja_and_en():
    from languages import UI_LABELS
    for lang in ("Japanese", "English"):
        ui = UI_LABELS[lang]
        for k in ("wait_slow", "wait_slower", "quota_left_n", "quota_none"):
            assert ui[k], (lang, k)
        assert "{n}" in ui["quota_left_n"]
    assert "1分" in UI_LABELS["Japanese"]["wait_slow"] and "minute" in UI_LABELS["English"]["wait_slow"]


def test_page_has_quota_note_and_loads_status_js_before_app_js(env):
    app, *_ = env
    c = app.test_client(); start(c)
    html = c.get("/").get_data(as_text=True)
    assert 'id="quota-note"' in html and 'role="status"' in html
    assert html.index("js/status.js") < html.index("js/app.js")
    assert html.index("js/backup.js") < html.index("js/status.js")        # fmt() を使うため
    assert "js/status.js" in c.get("/sw.js").get_data(as_text=True)        # オフライン用に端末へ保存される


def test_status_js_wires_wait_notice_and_quota():
    js = read("static", "js", "status.js")
    for fn in ("startWaitNotice", "stopWaitNotice", "resetSubmitButtons", "refreshQuota"):
        assert f"function {fn}" in js or f"async function {fn}" in js, fn
    assert "WAIT_SLOW_MS = 6000" in js and "WAIT_SLOWER_MS = 25000" in js
    assert "e.persisted" in js and "/api/quota" in js
    app_js = read("static", "js", "app.js")
    assert "startWaitNotice(form)" in app_js and "dataset.label" in app_js
    assert "refreshQuota" in read("static", "js", "chat.js")


# ---------------- スマホの見た目 ----------------

def test_no_low_contrast_text_colors():
    """暗い背景で読みにくい文字色（slate-500/600）と、薄い入力案内文字を使わない。例外は飾りのカメラアイコンだけ"""
    bad = []
    for f in all_front_files():
        for n, line in enumerate(open(f, encoding="utf-8"), 1):
            for m in re.finditer(r"(?<![\w-])(text-slate-[56]00|placeholder-slate-[56]00)", line):
                if "fa-camera" in line and "text-3xl" in line:
                    continue
                bad.append(f"{os.path.relpath(f, ROOT)}:{n}:{m.group(1)}")
    assert not bad, bad


def test_text_colors_meet_contrast_on_dark_backgrounds():
    def lum(h):
        h = h.lstrip("#")
        r, g, b = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

    def ratio(a, b):
        hi, lo = sorted([lum(a), lum(b)], reverse=True)
        return (hi + 0.05) / (lo + 0.05)
    slate400, slate950, slate800, slate900 = "#94a3b8", "#020617", "#1e293b", "#0f172a"
    for bg in (slate950, slate900, slate800):
        assert ratio(slate400, bg) >= 4.5
    # 新しい案内の色も 4.5 以上
    assert ratio("#fde68a", "#2b1a12") >= 4.5 and ratio("#fcd34d", slate900) >= 4.5 and ratio("#fca5a5", slate900) >= 4.5
    assert ratio("#cbd5e1", slate900) >= 4.5


def test_light_theme_placeholder_override_exists():
    css = read("static", "style.css")
    assert 'html[data-theme=light] [class*="placeholder-slate-400"]::placeholder' in css
    for sel in (".wait-note", ".quota-note.low", ".quota-note.none"):
        assert f"html[data-theme=light] {sel}" in css, sel


def test_tiny_text_is_gone_and_font_size_setting_still_applies():
    css = read("static", "style.css")
    for f in all_front_files():
        assert "text-[10px]" not in open(f, encoding="utf-8").read(), f
    assert "text-\\[10px\\]" not in css
    assert "html[data-fs] .text-\\[11px\\]" in css and "html[data-fs=xl] .text-\\[11px\\]" in css


def test_header_buttons_are_big_enough_to_tap():
    header = read("templates", "components", "header.html")
    # ロゴの画像（押すボタンではない）以外に、36px以下の指定がない
    stripped = re.sub(r'<img[^>]*>', '', header, flags=re.S)
    assert not re.search(r'(?<![\w-])(w|h)-(8|9|10)(?![\w.])', stripped)
    assert header.count("h-11") >= 2 and header.count("w-11") >= 1     # 言語ボタンと、入れ替えボタン（v1.1 で歯車を撤去）
    assert "w-11 h-11" in read("templates", "select_language.html")
    assert "w-11 h-11" in read("templates", "components", "history_tab.html")


def test_tap_delay_css():
    assert "touch-action: manipulation" in read("static", "style.css")
