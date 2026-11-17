"""ルート（URL ごとの処理）。種類ごとにファイルを分けてある。URL・関数名（endpoint）は分ける前と同じ。

- pages.py         画面（トップ・言語選択・言語の切り替え）と、フォームの翻訳
- api_translate.py 翻訳まわりの API（文字・PDF・別の言い方・解説）
- pwa.py           ホーム画面に追加（PWA）・オフライン
- system.py        全データ削除・プライバシー・利用状況・残り回数・為替レート・ヘルスチェック
"""
from . import api_translate, pages, pwa, system


def register_routes(app):
    pages.register(app)
    api_translate.register(app)
    pwa.register(app)
    system.register(app)
