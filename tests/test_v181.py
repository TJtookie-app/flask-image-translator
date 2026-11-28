"""v1.8.1（V13b）: Android の殻（Capacitor）の設定・起動画面・許可設定ツール・アイコン素材・ツールの安全装置。"""
import json
import os
import sys

import pytest
from PIL import Image

from conftest import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))


def _read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


def test_version_is_181_or_later_in_family():
    from app import APP_VERSION
    assert APP_VERSION.startswith(("1.8.", "1.9.", "1.10."))


def test_capacitor_config_is_the_agreed_one():
    c = json.loads(_read("capacitor.config.json"))
    assert c["appId"] == "app.tookie.translator"
    assert c["appName"] == "TOOKIE"
    assert c["webDir"] == "app-shell" and os.path.isfile(os.path.join(ROOT, "app-shell", "index.html"))
    assert "tookie-translator.onrender.com" in c["server"]["allowNavigation"]
    assert "url" not in c["server"]           # 起動画面を先に出すため、サイトを直接は読み込まない
    assert c["server"]["androidScheme"] == "https"   # 起動確認（/healthz）の許可と、同じ出どころ
    assert c["android"]["allowMixedContent"] is False


def test_package_json_pins_capacitor_8_and_node_22():
    p = json.loads(_read("package.json"))
    assert p["private"] is True and p["engines"]["node"] == ">=22"
    for name in ("@capacitor/core", "@capacitor/android"):
        assert p["dependencies"][name].startswith("^8")
    assert p["devDependencies"]["@capacitor/cli"].startswith("^8")
    assert "@capacitor/assets" in p["devDependencies"]
    for s in ("android:add", "android:patch", "android:assets", "android:sync", "android:open", "android:init"):
        assert s in p["scripts"]


def test_launcher_page_waits_for_the_server_and_has_no_external_loads():
    h = _read("app-shell", "index.html")
    assert 'var TARGET = "https://tookie-translator.onrender.com/"' in h and 'TARGET + "healthz"' in h
    assert "location.replace" in h and "navigator.onLine" in h
    for bad in ("cdn.", "googleapis", "http://", "<script src=", "<link"):
        assert bad not in h
    assert os.path.getsize(os.path.join(ROOT, "app-shell", "logo.png")) > 1000


def test_healthz_is_readable_from_the_app_origin_only(env):
    from app import app
    c = app.test_client()
    r = c.get("/healthz", headers={"Origin": "https://localhost"})
    assert r.data == b"ok" and r.headers["Access-Control-Allow-Origin"] == "https://localhost"
    assert r.headers["Cache-Control"] == "no-store"
    r = c.get("/healthz", headers={"Origin": "https://evil.example"})
    assert r.data == b"ok" and "Access-Control-Allow-Origin" not in r.headers
    assert "Access-Control-Allow-Origin" not in c.get("/healthz").headers


def test_android_files_are_not_in_the_docker_image_or_served():
    di = _read(".dockerignore")
    for name in ("android", "app-shell", "assets", "capacitor.config.json", "package.json"):
        assert name in di.split()
    assert "package-lock.json" not in _read(".gitignore").split()
    from app import app
    c = app.test_client()
    assert c.get("/static/../app-shell/index.html").status_code == 404
    assert c.get("/capacitor.config.json").status_code == 404


def test_asset_sources_have_the_sizes_capacitor_assets_needs():
    sizes = {"icon-only.png": 1024, "icon-foreground.png": 1024, "icon-background.png": 1024, "splash.png": 2732, "splash-dark.png": 2732}
    for name, n in sizes.items():
        assert Image.open(os.path.join(ROOT, "assets", name)).size == (n, n), name


MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application android:label="TOOKIE"></application>

    <uses-permission android:name="android.permission.INTERNET" />
</manifest>
"""


def test_patch_manifest_adds_permissions_once():
    import android_patch as ap
    out = ap.patch_manifest(MANIFEST)
    for p in ap.PERMISSIONS:
        assert out.count(f'android:name="{p}"') == 1
    for f in ap.FEATURES:
        assert f'<uses-feature android:name="{f}" android:required="false" />' in out
    assert out.rstrip().endswith("</manifest>")
    assert ap.patch_manifest(out) == out                      # 2回目は何も変えない
    assert ap.missing(out) == ([], [])


def test_patch_tool_run_modes(tmp_path, monkeypatch, capsys):
    import android_patch as ap
    man = tmp_path / "AndroidManifest.xml"
    var = tmp_path / "variables.gradle"
    monkeypatch.setattr(ap, "MANIFEST", str(man)); monkeypatch.setattr(ap, "VARIABLES", str(var))
    assert ap.run([]) == 2 and "npm run android:add" in capsys.readouterr().out     # android/ がまだ
    man.write_text(MANIFEST, encoding="utf-8"); var.write_text("ext {\n  targetSdkVersion = 36\n}\n", encoding="utf-8")
    assert ap.run(["--check"]) == 1 and man.read_text(encoding="utf-8") == MANIFEST   # 確認だけでは書き換えない
    assert ap.run([]) == 0 and ap.missing(man.read_text(encoding="utf-8")) == ([], [])
    assert ap.run(["--check"]) == 0
    var.write_text("ext {\n  targetSdkVersion = 34\n}\n", encoding="utf-8")
    assert ap.run(["--check"]) == 1 and "36" in capsys.readouterr().out


def test_label_and_phrasebook_tools_stop_without_a_lite_model(monkeypatch, capsys, tmp_path):
    import generate_phrasebook as gp
    import generate_ui_labels as gl
    monkeypatch.setattr(gp, "OUT", str(tmp_path))
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    asked = []
    assert gp.run(["--only", "Thai"], ask=lambda p: asked.append(p) or "k") == 2
    out = capsys.readouterr().out
    assert "GEMINI_MODEL" in out and "gemini-3.1-flash-lite" in out and "--prod-model" in out and not asked
    monkeypatch.setenv("GEMINI_MODEL", "gemini-4-hydrogen")          # 本番のモデルでも止まる
    assert gp.run(["--only", "Thai"]) == 2
    assert gl.run(["--only", "Thai", "--force"]) == 2
    assert gl.model_guard(["--prod-model"]) is True                    # わかっていて使うときだけ
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
    assert gl.model_guard([]) is True
    # --check は API を使わないので、指定がなくても動く
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert gp.run(["--check", "--only", "Thai"]) in (0, 1)

