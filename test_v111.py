"""V11.1: 上限超過で予備モデルへ切替・待ち時間・サイト全体の1分上限・枠切れ表示・IP判定・ヘッダ・アイコン・依存の範囲"""
import json
import os
import time

import pytest
from PIL import Image

from conftest import start

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OK = '{"detected_language":"English","source_text":"hi","translation":"やあ"}'


class ApiError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def scripted(monkeypatch, translator, outcomes):
    """_generate を差し替え、呼ばれるたびに outcomes を順に返す（例外ならそれを投げる）。使ったモデル名も記録"""
    models = []
    it = iter(outcomes)

    def fake(parts, system=None):
        models.append(translator._model())
        out = next(it)
        if isinstance(out, Exception):
            raise out
        return out
    monkeypatch.setattr(translator, "_generate", fake)
    return models


def no_sleep(monkeypatch, translator):
    def boom(_):
        raise AssertionError("待たずに切り替えるはず")
    monkeypatch.setattr(translator.time, "sleep", boom)


# ---------------- 上限超過(429)で予備モデルへ ----------------

def test_quota_switches_to_fallback_immediately(env):
    _, tr, _, mp = env
    mp.setattr(tr, "MODEL", "primary"); mp.setattr(tr, "FALLBACK_MODEL", "backup"); mp.setattr(tr, "RETRY_WAIT", 1.0)
    no_sleep(mp, tr)
    models = scripted(mp, tr, [ApiError(429, "RESOURCE_EXHAUSTED quota"), OK])
    assert tr._call(["hi"])  == OK
    assert models == ["primary", "backup"]


def test_quota_without_fallback_fails_once(env):
    _, tr, _, mp = env
    mp.setattr(tr, "MODEL", "primary"); mp.setattr(tr, "FALLBACK_MODEL", "")
    models = scripted(mp, tr, [ApiError(429, "RESOURCE_EXHAUSTED"), OK])
    with pytest.raises(tr.TranslationError) as e:
        tr._call(["hi"])
    assert e.value.key == "err_quota" and models == ["primary"]


def test_quota_on_both_models_reports_quota(env):
    _, tr, _, mp = env
    mp.setattr(tr, "MODEL", "primary"); mp.setattr(tr, "FALLBACK_MODEL", "backup")
    models = scripted(mp, tr, [ApiError(429, "quota"), ApiError(429, "quota")])
    with pytest.raises(tr.TranslationError) as e:
        tr._call(["hi"])
    assert e.value.key == "err_quota" and models == ["primary", "backup"]


def test_timeout_still_switches_and_overload_too(env):
    _, tr, _, mp = env
    mp.setattr(tr, "MODEL", "primary"); mp.setattr(tr, "FALLBACK_MODEL", "backup")
    for code, msg in ((504, "DEADLINE_EXCEEDED"), (503, "UNAVAILABLE")):
        models = scripted(mp, tr, [ApiError(code, msg), OK])
        assert tr._call(["hi"]) == OK and models == ["primary", "backup"]


def test_api_key_error_does_not_switch(env):
    _, tr, _, mp = env
    mp.setattr(tr, "MODEL", "primary"); mp.setattr(tr, "FALLBACK_MODEL", "backup")
    models = scripted(mp, tr, [ApiError(403, "API key not valid"), OK])
    with pytest.raises(tr.TranslationError) as e:
        tr._call(["hi"])
    assert e.value.key == "err_api_key" and models == ["primary"]


def test_text_waits_less_than_images():
    import translator
    assert translator._timeout_for(["hello"]) == translator.TEXT_TIMEOUT_SEC
    assert translator._timeout_for([("img", "image/png"), "prompt"]) == translator.TIMEOUT_SEC
    assert translator.TEXT_TIMEOUT_SEC * translator.ATTEMPTS <= 60   # 2回試しても1分以内


# ---------------- サイト全体の1分上限 ----------------

def test_site_per_minute_limit(env):
    _, _, _, mp = env
    from limits import limiter
    mp.setenv("SITE_RATE_PER_MIN", "2")
    assert limiter.check("1.1.1.1") is None
    assert limiter.check("2.2.2.2") is None          # 別のIPでも合計で数える
    assert limiter.check("3.3.3.3") == "err_busy"
    # 1分たてば使える
    real = time.time()
    mp.setattr(time, "time", lambda: real + 61)
    assert limiter.check("3.3.3.3") is None


def test_site_per_minute_can_be_disabled(env):
    _, _, _, mp = env
    from limits import limiter
    mp.setenv("SITE_RATE_PER_MIN", "0")
    assert all(limiter.check("1.1.1.1") is None for _ in range(10))


def test_busy_blocked_request_is_not_counted(env):
    _, _, _, mp = env
    from limits import limiter
    mp.setenv("SITE_RATE_PER_MIN", "1")
    assert limiter.check("1.1.1.1") is None
    assert limiter.check("1.1.1.1") == "err_busy"
    assert limiter.site_day == 1 and limiter.per_ip_day["1.1.1.1"] == 1


def test_busy_error_through_api(env):
    app, _, _, mp = env
    mp.setenv("SITE_RATE_PER_MIN", "1")
    c = app.test_client(); start(c)
    body = {"text": "hi", "source": "English", "target": "Japanese"}
    assert c.post("/api/translate-text", json=body).status_code == 200
    r = c.post("/api/translate-text", json=body)
    assert r.status_code == 429 and r.get_json()["key"] == "err_busy"
    assert "1分" in r.get_json()["error"]


def test_daily_message_explains_free_plan():
    from languages import UI_LABELS
    ja, en = UI_LABELS["Japanese"], UI_LABELS["English"]
    assert "今日の翻訳の枠は終わりました" in ja["err_daily"] and "戻ります" in ja["err_daily"]
    assert "Today" in en["err_daily"] and "resets" in en["err_daily"]
    assert "err_busy" in ja and "err_busy" in en


# ---------------- IP の判定 ----------------

def ip_of(app, xff=None, remote="9.9.9.9"):
    from helpers import client_ip
    headers = {"X-Forwarded-For": xff} if xff is not None else {}
    with app.test_request_context("/", headers=headers, environ_base={"REMOTE_ADDR": remote}):
        return client_ip()


def test_client_ip_default_uses_first_valid_value(env):
    app, *_ = env
    assert ip_of(app, "1.2.3.4, 10.0.0.1") == "1.2.3.4"
    assert ip_of(app) == "9.9.9.9"


def test_client_ip_ignores_garbage(env):
    app, *_ = env
    assert ip_of(app, "999.1.1.1, 1.2.3.4") == "9.9.9.9"
    assert ip_of(app, "<script>") == "9.9.9.9"
    assert ip_of(app, "") == "9.9.9.9"


def test_client_ip_trusted_hops(env):
    app, _, _, mp = env
    mp.setenv("TRUSTED_PROXY_HOPS", "1")
    assert ip_of(app, "6.6.6.6, 1.2.3.4") == "1.2.3.4"        # 偽装した先頭ではなく、プロキシが付けた末尾を使う
    mp.setenv("TRUSTED_PROXY_HOPS", "2")
    assert ip_of(app, "6.6.6.6, 1.2.3.4, 10.0.0.1") == "1.2.3.4"
    mp.setenv("TRUSTED_PROXY_HOPS", "5")                      # 段数が足りないときは先頭
    assert ip_of(app, "1.2.3.4") == "1.2.3.4"
    mp.setenv("TRUSTED_PROXY_HOPS", "abc")
    assert ip_of(app, "1.2.3.4, 5.5.5.5") == "1.2.3.4"


def test_admin_can_see_ip_seen_by_the_app(env):
    app, _, _, mp = env
    mp.setenv("ADMIN_TOKEN", "t0k")
    c = app.test_client()
    r = c.get("/api/stats?token=t0k&ip=1", headers={"X-Forwarded-For": "1.2.3.4, 10.0.0.1"})
    d = r.get_json()
    assert d["seen_ip"] == "1.2.3.4" and d["x_forwarded_for"] == "1.2.3.4, 10.0.0.1" and "remote_addr" in d
    assert c.get("/api/stats?token=wrong&ip=1").status_code == 404
    assert isinstance(c.get("/api/stats?token=t0k").get_json(), dict)


# ---------------- セキュリティヘッダ ----------------

@pytest.mark.parametrize("path", ["/", "/healthz", "/manifest.webmanifest", "/privacy"])
def test_security_headers(env, path):
    app, *_ = env
    c = app.test_client()
    h = c.get(path).headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "SAMEORIGIN"
    assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=(self)" in h["Permissions-Policy"] and "microphone=(self)" in h["Permissions-Policy"]
    assert h["Strict-Transport-Security"].startswith("max-age=")


def test_headers_do_not_break_caching_or_sw(env):
    app, *_ = env
    c = app.test_client()
    r = c.get("/sw.js")
    assert r.headers["Cache-Control"] == "no-cache" and r.headers["Service-Worker-Allowed"] == "/"
    assert c.get("/favicon.ico").headers["Cache-Control"].startswith("public")


# ---------------- アイコン ----------------

@pytest.mark.parametrize("name,size", [("icon-512.png", 512), ("icon-192.png", 192),
                                       ("apple-touch-icon.png", 180), ("icon-maskable-512.png", 512)])
def test_icon_files(name, size):
    im = Image.open(os.path.join(ROOT, "static", name))
    assert im.size == (size, size) and im.mode in ("RGB", "RGBA")


def test_maskable_icon_keeps_artwork_inside_safe_zone():
    im = Image.open(os.path.join(ROOT, "static", "icon-maskable-512.png")).convert("RGB")
    # 端の10%は真っ黒（端末の形で切り取られても絵が欠けない）
    m = int(512 * 0.10)
    for box in ((0, 0, 512, m), (0, 512 - m, 512, 512), (0, 0, m, 512), (512 - m, 0, 512, 512)):
        assert max(im.crop(box).getextrema()[i][1] for i in range(3)) <= 40, box
    full = Image.open(os.path.join(ROOT, "static", "icon-512.png")).convert("RGB")
    assert im.tobytes() != full.tobytes()


def test_manifest_lists_all_icons(env):
    app, *_ = env
    icons = app.test_client().get("/manifest.webmanifest").get_json()["icons"]
    assert {(i["sizes"], i["purpose"]) for i in icons} == {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")}
    for i in icons:
        assert os.path.exists(os.path.join(ROOT, i["src"].lstrip("/")))


def test_asset_version_changes_with_icon(env):
    """アイコンを替えると版番号が変わり、古いキャッシュを使わない"""
    import app as appmod
    before = appmod._asset_version()
    p = os.path.join(ROOT, "static", "icon-192.png")
    orig = open(p, "rb").read()
    try:
        open(p, "ab").write(b"\0")
        assert appmod._asset_version() != before
    finally:
        open(p, "wb").write(orig)
    assert appmod._asset_version() == before


# ---------------- 依存 ----------------

def test_requirements_have_upper_bounds():
    lines = [l.strip() for l in open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8")
             if l.strip() and not l.startswith("#")]
    names = {l.split(">")[0].split("=")[0].split("<")[0] for l in lines}
    assert names == {"Flask", "gunicorn", "requests", "google-genai", "pillow", "pydantic", "pypdf"}
    for l in lines:
        if not l.startswith("google-genai"):
            assert "<" in l, l
