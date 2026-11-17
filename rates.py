"""為替レート（無料API）の取得と、サーバー内での一時保存。Gemini の無料枠・利用制限とは関係なし。

画面（通貨タブ）は /api/rates だけを見る。サーバーは数時間に1回だけ外のAPIへ取りに行き、
その間は保存した値を返す（利用者が何人いても外のAPIへの問い合わせは増えない）。
取得に失敗したときは、前回の値に stale=true を付けて返す。まだ一度も取れていなければ RatesUnavailable。

環境変数（どれも任意）:
  RATES_URL           メインのAPI（既定 https://open.er-api.com/v6/latest/USD ・キー不要・約160通貨・1日1回更新）
  RATES_FALLBACK_URL  予備のAPI（既定 https://api.frankfurter.dev/v1/latest?base=USD ・欧州中央銀行のレート・約30通貨）。空にすると使わない
  RATES_TTL_SEC       何秒ごとに取り直すか（既定 21600 = 6時間）
"""
import math
import os
import threading
import time
from datetime import datetime, timezone

import requests

ATTRIBUTION = "https://www.exchangerate-api.com"   # メインAPIの無料版は、出典の表示が条件
TIMEOUT_SEC = 8
RETRY_AFTER_FAIL_SEC = 120     # 取得に失敗したら、しばらく取りに行かない（待たされる人を増やさない）


class RatesUnavailable(Exception):
    pass


def _http_get(url):
    r = requests.get(url, timeout=TIMEOUT_SEC, headers={"User-Agent": "TOOKIE/1.0 (+rates)"})
    r.raise_for_status()
    return r.json()


def clean_rates(raw, min_count):
    """{"JPY": 154.3, ...} のうち、3文字の通貨コードで、正の有限の数だけを残す。足りなければ None（壊れたデータを使わない）"""
    if not isinstance(raw, dict):
        return None
    out = {}
    for k, v in raw.items():
        if isinstance(k, str) and len(k) == 3 and k.isalpha() and isinstance(v, (int, float)) and not isinstance(v, bool) \
                and math.isfinite(v) and v > 0:
            out[k.upper()] = float(v)
    out["USD"] = 1.0
    return out if len(out) >= min_count else None


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch_primary(url):
    j = _http_get(url)
    if not isinstance(j, dict) or j.get("result") != "success":
        raise ValueError("primary: not success")
    rates = clean_rates(j.get("rates"), 50)
    if not rates:
        raise ValueError("primary: too few rates")
    updated = j.get("time_last_update_unix")
    return {"rates": rates, "updated": _iso(updated) if isinstance(updated, (int, float)) else _iso(time.time()),
            "source": "exchangerate-api.com", "attribution": ATTRIBUTION}


def _fetch_fallback(url):
    j = _http_get(url)
    rates = clean_rates(j.get("rates") if isinstance(j, dict) else None, 10)
    if not rates:
        raise ValueError("fallback: too few rates")
    day = str(j.get("date") or "")
    try:
        updated = _iso(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        updated = _iso(time.time())
    return {"rates": rates, "updated": updated, "source": "frankfurter.dev (ECB)", "attribution": "https://www.frankfurter.dev"}


class RateStore:
    def __init__(self):
        self.lock = threading.Lock()      # 保存した値の読み書き
        self.refresh_lock = threading.Lock()   # 取りに行くのは同時に1つだけ
        self.reset()

    def reset(self):
        with self.lock:
            self.data = None
            self.fetched_at = 0.0
            self.next_try = 0.0

    def _fresh(self, now):
        ttl = int(os.environ.get("RATES_TTL_SEC") or 21600)
        return self.data is not None and now - self.fetched_at < ttl

    def _refresh(self):
        urls = [("primary", os.environ.get("RATES_URL") or "https://open.er-api.com/v6/latest/USD")]
        fb = os.environ.get("RATES_FALLBACK_URL", "https://api.frankfurter.dev/v1/latest?base=USD")
        if fb:
            urls.append(("fallback", fb))
        for kind, url in urls:
            try:
                data = (_fetch_primary if kind == "primary" else _fetch_fallback)(url)
            except Exception as e:     # 通信・形式の失敗は、次の取得先に切り替える
                print(f"[rates] {kind} failed: {type(e).__name__}: {e}", flush=True)
                continue
            with self.lock:
                self.data, self.fetched_at = data, time.time()
            return True
        return False

    def get(self):
        """{"base","rates","updated","fetched","source","attribution","stale"} を返す。1つも取れなければ RatesUnavailable"""
        now = time.time()
        with self.lock:
            if self._fresh(now):
                return self._payload(False)
            have = self.data is not None
            wait = now < self.next_try
        if not wait:                                           # 失敗した直後は、取りに行かず前回の値（なければエラー）を返す
            if self.refresh_lock.acquire(blocking=not have):    # 古い値があるなら、他の人が取りに行っている間は待たずに古い値を返す
                try:
                    with self.lock:
                        if self._fresh(time.time()):
                            return self._payload(False)
                    ok = self._refresh()
                    if not ok:
                        with self.lock:
                            self.next_try = time.time() + RETRY_AFTER_FAIL_SEC
                finally:
                    self.refresh_lock.release()
        with self.lock:
            if self.data is None:
                raise RatesUnavailable()
            return self._payload(not self._fresh(time.time()))

    def _payload(self, stale):
        d = self.data
        return {"base": "USD", "rates": d["rates"], "updated": d["updated"], "fetched": _iso(self.fetched_at),
                "source": d["source"], "attribution": d["attribution"], "stale": stale}


store = RateStore()
