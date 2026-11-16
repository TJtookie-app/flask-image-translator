"""利用制限（1分・1日・サイト全体の1分と1日）と簡易統計。すべてメモリ上（ワーカー1つ前提）。
再起動やデプロイで数え直しになるため、Google 側の上限（無料枠）より少し低めに設定しておく。

環境変数:
  RATE_PER_MIN        IPごとの1分あたり上限（既定 20）
  DAILY_LIMIT_PER_IP  IPごとの1日あたり上限（既定 300）
  SITE_RATE_PER_MIN   サイト全体の1分あたり上限（既定 4。無料枠は1モデル1分5回。0で無効）
  SITE_DAILY_LIMIT    サイト全体の1日あたり上限（既定 3000。APIの無料枠・費用を守る）
  LIMIT_DAY_TZ        「1日」の区切りに使うタイムゾーン（既定 America/Los_Angeles。Gemini の無料枠は太平洋時間の0時に戻るため、合わせている）
  QUOTA_SHOW_BELOW    サイト全体の1日上限がこの値以下のときだけ、画面に「今日の残り回数」を出す（既定 500）
"""
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import os
import threading
import time


def _num(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _limit_day(now=None):
    """利用制限の「1日」の区切り。Google の無料枠（太平洋時間の0時にリセット）に合わせる。
    タイムゾーンが読み込めないときは、太平洋標準時（UTC-8）で代用する"""
    now = now or datetime.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        zone = ZoneInfo(os.environ.get("LIMIT_DAY_TZ") or "America/Los_Angeles")
    except Exception:
        zone = timezone(timedelta(hours=-8))
    return now.astimezone(zone).strftime("%Y-%m-%d")


class Limiter:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        with self.lock:
            self.hits = defaultdict(deque)   # ip -> 直近1分のタイムスタンプ
            self.day = _limit_day()
            self.per_ip_day = defaultdict(int)
            self.site_day = 0
            self.site_hits = deque()         # サイト全体の直近1分のタイムスタンプ

    def _roll(self):
        """日が変わっていたら、1日分の数え直しをする（lock を持った状態で呼ぶ）"""
        today = _limit_day()
        if today != self.day:
            self.day, self.per_ip_day, self.site_day = today, defaultdict(int), 0
            self.hits = defaultdict(deque)
            self.site_hits = deque()

    def quota(self):
        """画面に出す「今日の残り回数」。サイト全体の1日上限に対する残り"""
        limit = _num("SITE_DAILY_LIMIT", 3000)
        with self.lock:
            self._roll()
            used = self.site_day
        return {"limit": limit, "used": used, "remaining": max(0, limit - used),
                "show": limit <= _num("QUOTA_SHOW_BELOW", 500)}

    def check(self, ip):
        """OKなら None。制限に当たったらエラーラベル名（err_rate / err_daily）を返し、OKなら1回分を消費する"""
        per_min, per_ip, site = (_num("RATE_PER_MIN", 20), _num("DAILY_LIMIT_PER_IP", 300),
                                 _num("SITE_DAILY_LIMIT", 3000))
        site_min = _num("SITE_RATE_PER_MIN", 4)
        now = time.time()
        with self.lock:
            self._roll()
            if self.site_day >= site or self.per_ip_day[ip] >= per_ip:
                return "err_daily"
            q = self.hits[ip]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= per_min:
                return "err_rate"
            sq = self.site_hits
            while sq and now - sq[0] > 60:
                sq.popleft()
            if site_min > 0 and len(sq) >= site_min:
                return "err_busy"
            sq.append(now)
            q.append(now)
            self.per_ip_day[ip] += 1
            self.site_day += 1
            return None


class Stats:
    """日別の件数（成功・エラー種別）。再起動で消える。ログにも出すので Render のログで追える"""
    KEEP_DAYS = 14

    def __init__(self):
        self.lock = threading.Lock()
        self.days = {}

    def reset(self):
        with self.lock:
            self.days = {}

    def record(self, kind, key="ok"):
        day = _today()
        with self.lock:
            d = self.days.setdefault(day, defaultdict(int))
            d["total"] += 1
            d[f"{kind}:{key}"] += 1
            for old in sorted(self.days)[:-self.KEEP_DAYS]:
                del self.days[old]
        if key != "ok":
            print(f"[stats] {kind} error: {key}", flush=True)

    def snapshot(self):
        with self.lock:
            return {day: dict(v) for day, v in sorted(self.days.items())}


limiter = Limiter()
stats = Stats()


def start_keepalive():
    """KEEP_ALIVE_URL が設定されていれば、10分ごとに自分の /healthz を叩いて Render の無料枠のスリープを防ぐ。
    ※外部の監視サービス（UptimeRobot等）で /healthz を5分おきに叩く方が確実"""
    url = os.environ.get("KEEP_ALIVE_URL")
    if not url:
        return

    def loop():
        import urllib.request
        while True:
            time.sleep(600)
            try:
                urllib.request.urlopen(url, timeout=15).read()
            except Exception as e:
                print(f"[keepalive] {e}", flush=True)

    threading.Thread(target=loop, daemon=True).start()
