"""翻訳まわりのエラー（TranslationError）と、Gemini の例外・応答をエラーの種類に分ける処理"""


class TranslationError(Exception):
    """key は languages.UI_LABELS のエラーラベル名"""

    def __init__(self, key):
        super().__init__(key)
        self.key = key


def _block_reason(resp):
    """安全フィルタ等でブロックされていれば理由を返す（なければ None）"""
    fb = getattr(resp, "prompt_feedback", None)
    reason = getattr(fb, "block_reason", None) if fb else None
    if reason:
        return str(reason)
    for c in getattr(resp, "candidates", None) or []:
        fr = str(getattr(c, "finish_reason", "") or "")
        if any(w in fr.upper() for w in ("SAFETY", "PROHIBITED", "BLOCKLIST", "SPII", "RECITATION")):
            return fr
    return None


def classify_exception(e):
    """例外を UI のエラーラベル名に分類する"""
    name = type(e).__name__.lower()
    msg = str(e).lower()
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    if not isinstance(code, int):
        code = None
    if "timeout" in name or "timed out" in msg or "deadline" in msg or code == 504:
        return "err_timeout"
    if code == 429 or "resource_exhausted" in msg or "quota" in msg:
        return "err_quota"
    if "api key" in msg or "api_key" in msg or code in (401, 403) or "permission_denied" in msg:
        return "err_api_key"
    if code in (500, 502, 503) or "unavailable" in msg or "overloaded" in msg:
        return "err_overloaded"
    if "connect" in name or "connection" in name or isinstance(e, (ConnectionError, OSError)) or "network" in msg:
        return "err_connection"
    return "err_failed"
