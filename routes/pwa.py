"""ホーム画面に追加（PWA）・オフライン用のルート（favicon / manifest / Service Worker / オフライン画面）"""

import json
import os

from flask import Response, make_response, render_template, url_for, send_from_directory
from helpers import get_langs, get_ui, get_ui_lang
from languages import LANGUAGES, get_lang_code, is_rtl
from phrasebook import available_languages


# 初回に端末へ保存しておく外部ファイル（Tailwind・FontAwesome）。以後は通信できなくても画面が崩れない
CDN_PRECACHE = [
    "https://cdn.tailwindcss.com",
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css",
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-solid-900.woff2",
    "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/webfonts/fa-regular-400.woff2",
]


def register(app):
    # ---- PWA（ホーム画面に追加）・オフライン ----
    @app.route("/favicon.ico")
    def favicon():
        """ブラウザが自動で取りに来る favicon（アイコン画像を返す）"""
        resp = send_from_directory(app.static_folder, "icon-192.png", mimetype="image/png")
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp

    @app.route("/manifest.webmanifest")
    def manifest():
        data = {
            "id": "/", "name": "TOOKIE - AI Universal Translator", "short_name": "TOOKIE",
            "description": "AI translator for text, images, voice and chat",
            "start_url": "/", "scope": "/", "display": "standalone", "orientation": "portrait",
            "background_color": "#020617", "theme_color": "#0f172a",
            "icons": [
                {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
                {"src": "/static/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            ],
        }
        return Response(json.dumps(data, ensure_ascii=False), mimetype="application/manifest+json")

    @app.route("/sw.js")
    def service_worker():
        version = app.config.get("ASSET_V", "dev")
        precache = []
        static_dir = app.static_folder
        for base, _dirs, files in sorted(os.walk(static_dir)):
            for name in sorted(files):
                rel = os.path.relpath(os.path.join(base, name), static_dir).replace(os.sep, "/")
                if rel.startswith(("icon-", "apple-touch")):
                    continue   # アイコンはホーム画面登録時にブラウザが取得する
                if rel.startswith("phrasebook/"):
                    precache.append(url_for("static", filename=rel))
                else:
                    precache.append(url_for("static", filename=rel, v=version))
        body = render_template(
            "sw.js", version=version, precache=precache, cdn=CDN_PRECACHE,
            cdn_hosts=["cdn.tailwindcss.com", "cdnjs.cloudflare.com"],
        )
        resp = Response(body, mimetype="application/javascript")
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["Service-Worker-Allowed"] = "/"
        return resp

    @app.route("/offline")
    def offline():
        """通信できないとき Service Worker が出す画面。履歴・用語集・フレーズ集は端末内のデータで動く"""
        _src, target = get_langs()
        ui_lang = get_ui_lang() or "English"
        resp = make_response(render_template(
            "offline.html", offline_page=True, ui=get_ui(), ui_lang=ui_lang, ui_code=get_lang_code(ui_lang), ui_rtl=is_rtl(ui_lang),
            target_lang=target, phrase_langs=available_languages(),
            lang_list=[{"name": l["name"], "code": l["code"], "native": l["native"]} for l in LANGUAGES],
        ))
        resp.headers["Cache-Control"] = "no-cache"
        return resp
