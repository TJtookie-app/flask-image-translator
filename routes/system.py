"""そのほか（全データ削除・プライバシー・利用状況・残り回数・為替レート・ヘルスチェック）"""

import os

from flask import abort, jsonify, make_response, render_template, request, session
from helpers import client_ip, get_ui, get_ui_lang
from limits import limiter, stats
from languages import get_lang_code, is_rtl
import rates

# アプリ（Capacitor）の画面の出どころ。この3つだけ、起動確認の応答を読めるようにする
APP_ORIGINS = {"https://localhost", "http://localhost", "capacitor://localhost"}


def register(app):
    @app.route("/api/clear-session", methods=["POST"])
    def api_clear_session():
        """「全データ削除」用。サーバー側に残る設定（Cookie）を消す"""
        session.clear()
        return jsonify(ok=True)

    @app.route("/privacy")
    def privacy():
        return render_template("privacy.html", ui=get_ui(), ui_code=get_lang_code(get_ui_lang() or "English"),
                               ui_rtl=is_rtl(get_ui_lang() or "English"))

    @app.route("/api/stats")
    def api_stats():
        """ADMIN_TOKEN を設定したときだけ有効。?token=... または X-Admin-Token ヘッダ"""
        token = os.environ.get("ADMIN_TOKEN")
        given = request.headers.get("X-Admin-Token") or request.args.get("token")
        if not token or given != token:
            abort(404)
        data = stats.snapshot()
        if request.args.get("ip"):   # 利用制限が見ているIPの確認用（TRUSTED_PROXY_HOPS を決めるときに使う）
            return jsonify(seen_ip=client_ip(), x_forwarded_for=request.headers.get("X-Forwarded-For", ""),
                           remote_addr=request.remote_addr)
        return jsonify(data)

    @app.route("/api/quota")
    def quota():
        """サイト全体の「今日の残り回数」（画面の小さな表示用）。利用回数には数えない"""
        resp = jsonify(limiter.quota())
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route("/api/rates")
    def api_rates():
        """通貨タブ用の為替レート（USD基準）。サーバー内に数時間保存した値を返す。Gemini の利用回数には数えない"""
        try:
            data = rates.store.get()
        except rates.RatesUnavailable:
            resp = jsonify({"error": get_ui()["err_rates"]})
            resp.status_code = 503
        else:
            resp = jsonify(data)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.route("/healthz")
    def healthz():
        """生きているかの確認。Android アプリの起動画面（別のオリジン）からも、応答の中身まで読めるようにする"""
        resp = make_response("ok")
        origin = request.headers.get("Origin", "")
        if origin in APP_ORIGINS:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
        resp.headers["Cache-Control"] = "no-store"
        return resp
