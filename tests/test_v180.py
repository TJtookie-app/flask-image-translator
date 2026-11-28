"""v1.8.0（V13a）: 外部の読み込み（Tailwind・FontAwesome の CDN）をなくし、同梱にした。"""
import os
import re

from conftest import ROOT, start

import sys

sys.path.insert(0, os.path.join(ROOT, "tools"))


def _read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def _scan(dirs, exts):
    for d in dirs:
        for base, _dirs, files in os.walk(os.path.join(ROOT, d)):
            if os.sep + "vendor" in base:
                continue
            for n in files:
                if n.endswith(exts):
                    yield os.path.join(base, n)


def test_version():
    import app as appmod
    assert appmod.APP_VERSION.startswith(("1.8.", "1.9.", "1.10."))


def test_no_cdn_left_anywhere_in_the_app():
    banned = ("cdn.tailwindcss.com", "cdnjs.cloudflare.com", "unpkg.com", "fonts.googleapis.com", "fonts.gstatic.com", "code.jquery.com")
    for path in _scan(["templates", "static", "routes"], (".html", ".js", ".css", ".py")):
        text = open(path, encoding="utf-8").read()
        for b in banned:
            assert b not in text, (path, b)
        if "cdn.jsdelivr.net" in text:   # v1.9.0: オフライン翻訳のエンジンだけは、ダウンロードのボタンを押したときに jsdelivr から取る（試作）
            assert path.replace(os.sep, "/").endswith(("static/js/offline_mt_worker.js", "templates/sw.js")), path
    assert "CDN_PRECACHE" not in _read("routes", "pwa.py") and "CDN_HOSTS" not in _read("templates", "sw.js")


def test_every_page_links_the_bundled_css_and_tailwind_comes_last(env):
    app, *_ = env
    c = app.test_client(); start(c, "Japanese")
    for path in ("/", "/start", "/privacy", "/select-language?type=source", "/offline"):
        html = c.get(path).get_data(as_text=True)
        head = html[:html.index("</head>")]
        assert "/static/vendor/tailwind.css?v=" in head, path
        assert "<script src=\"https://" not in head, path
        # Tailwind は head の最後（これまで CDN が styleを足していた場所）。自前の CSS より後ろ
        for mine in ("style.css", "theme.css", "look.css"):
            if mine in head:
                assert head.index(mine) < head.index("vendor/tailwind.css"), (path, mine)
        if path != "/privacy":
            assert "vendor/fontawesome/css/all.min.css?v=" in head, path


def test_vendor_files_are_served_with_the_right_types(env):
    app, *_ = env
    c = app.test_client()
    for url, kind in (("/static/vendor/tailwind.css", "text/css"), ("/static/vendor/fontawesome/css/all.min.css", "text/css"),
                      ("/static/vendor/fontawesome/webfonts/fa-solid-900.woff2", "font/woff2"),
                      ("/static/vendor/fontawesome/webfonts/fa-regular-400.woff2", "font/woff2"),
                      ("/static/vendor/fontawesome/LICENSE.txt", "text/plain")):
        r = c.get(url)
        assert r.status_code == 200 and kind in r.headers["Content-Type"], (url, r.headers.get("Content-Type"))


def test_tailwind_css_is_real_and_not_stale():
    css = _read("static", "vendor", "tailwind.css")
    assert len(css) > 15000 and css.startswith("/* Tailwind CSS v3")
    for needle in (".bg-slate-900", ".hover\\:bg-slate-700", ".space-y-3", ".max-w-xl", ".text-\\[11px\\]", ".rounded-3xl", ".from-indigo-600", ".md\\:p-7"):
        assert needle in css, needle
    import build_css                                # tools/build_css.py
    assert not build_css.stale(), "クラス名が変わりました。python tools/build_css.py を実行して、static/vendor/ の CSS を作り直してください。"
    assert os.path.exists(os.path.join(ROOT, "tools", "vendor", "tailwind-play-cdn.js"))


def test_every_icon_used_exists_in_the_bundled_font_awesome():
    css = _read("static", "vendor", "fontawesome", "css", "all.min.css")
    defined = set(re.findall(r"\.(fa-[a-z0-9-]+)", css))
    used, regular = set(), set()
    for path in _scan(["templates", "static", "routes"], (".html", ".js", ".py")):
        text = open(path, encoding="utf-8").read()
        for m in re.finditer(r"\bfa-(solid|regular|brands)\s+(fa-[a-z0-9]+(?:-[a-z0-9]+)*)", text):
            used.add(m.group(2))
            if m.group(1) == "regular":
                regular.add(m.group(2))
            assert m.group(1) != "brands", path               # ブランド用フォントは同梱していない
    assert used and used <= defined, sorted(used - defined)
    assert regular <= {"fa-star", "fa-bookmark"}, regular      # 同梱の線画フォントで確かめたのは、この2つだけ。増やしたら、確かめる
    assert "--fa-width: auto" in css                            # アイコンの幅は、これまでと同じ（自動）


def test_service_worker_precaches_the_bundled_files_and_drops_the_old_runtime_cache(env):
    app, *_ = env
    from app import ASSET_V
    js = app.test_client().get("/sw.js").get_data(as_text=True)
    pre = js.split("const PRECACHE")[1].split("self.addEventListener")[0]
    assert f"/static/vendor/tailwind.css?v={ASSET_V}" in pre and f"/static/vendor/fontawesome/css/all.min.css?v={ASSET_V}" in pre
    assert '"/static/vendor/fontawesome/webfonts/fa-solid-900.woff2"' in pre      # CSS の中から（?v= なしで）呼ばれるので、付けずに保存する
    assert "const keep = [CACHE, MODE_CACHE, OMT_CACHE, 'transformers-cache']" in js and "tookie-runtime-v1" not in js.replace("tookie-runtime-v1）は", "")


def test_build_css_check_command_works():
    import subprocess
    import sys
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_css.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
