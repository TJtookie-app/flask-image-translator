"""通貨一覧用の同梱データを作る（国→通貨、タイムゾーン→国）。
  使い方: pip install babel  →  python tools/build_money_data.py
  出力:   static/money/countries.json  {"JP": ["JPY"], "PA": ["USD", "PAB"], ...}   現在使われている法定通貨（主なものが先頭）
          static/money/zones.json      {"Asia/Tokyo": "JP", ...}                      端末のタイムゾーンから国を決めるための表
  元データ: 通貨は Unicode CLDR（Babel 経由）、タイムゾーンは IANA（OS の zone.tab / tzdata.zi）。年に数回、国の通貨が変わったときだけ作り直す。"""
import datetime
import json
import os
import sys

from babel.core import get_global

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "money")
TODAY = (datetime.date.today().year, datetime.date.today().month, datetime.date.today().day)
ZONEINFO = "/usr/share/zoneinfo"

# CLDR が複数の通貨を返す国、または旅行者が実際に使う通貨が違う国（先頭が主な通貨）
OVERRIDES = {
    "BT": ["BTN", "INR"], "HT": ["HTG", "USD"], "LS": ["LSL", "ZAR"], "NA": ["NAD", "ZAR"],
    "PA": ["USD", "PAB"], "PS": ["ILS", "JOD"], "ZW": ["USD", "ZWG"],
    "KH": ["KHR", "USD"],   # カンボジアは米ドルも広く使われる
    "BG": ["EUR"],          # ブルガリアは 2026年1月にユーロへ移行（CLDR のデータが古い分を補う）
}
SKIP = {"AQ", "BU", "CP", "CS", "DD", "SU", "TP", "YD", "YU", "ZR", "ZZ", "XK_"}   # 南極・消えた国・特殊コード


def build_countries():
    out = {}
    for cc, rows in get_global("territory_currencies").items():
        if cc in SKIP or len(cc) != 2:
            continue
        cur = [c for (c, f, t, tender) in rows if tender and (f is None or f <= TODAY) and (t is None or t >= TODAY)]
        cur = OVERRIDES.get(cc) or cur
        if cur:
            out[cc] = cur
    return dict(sorted(out.items()))


def build_zones(countries):
    zones = {}
    with open(os.path.join(ZONEINFO, "zone.tab"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            cc, _coord, zone, *_ = line.rstrip("\n").split("\t")
            if cc in countries:
                zones[zone] = cc
    # 古い名前（Asia/Calcutta など）も、新しい名前と同じ国にする（tzdata.zi の「L 新 旧」行）
    with open(os.path.join(ZONEINFO, "tzdata.zi"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("L "):
                _, target, alias = line.split()[:3]
                if target in zones and alias not in zones:
                    zones[alias] = zones[target]
    return dict(sorted(zones.items()))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    countries = build_countries()
    zones = build_zones(countries)
    for name, data in (("countries.json", countries), ("zones.json", zones)):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        print(name, len(data), "entries", os.path.getsize(os.path.join(OUT, name)), "bytes")
    missing = sorted(set(countries) - set(zones.values()))
    print("国はあるがタイムゾーンがない（GPS・手動でだけ判定）:", missing)
