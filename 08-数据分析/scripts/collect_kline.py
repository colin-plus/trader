#!/usr/bin/env python3
"""日线行情批量采集：腾讯 fqkline → daily_kline（9 只关注标的，近 5 年）。

数据源：web.ifzq.gtimg.cn/appstock/app/fqkline/get（前复权，稳定）。
幂等：同日覆盖（ON CONFLICT DO UPDATE），历史保留。
"""
import json
import pathlib
import sys
import urllib.request

import duckdb

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"

CODES = [
    ("003043", "sz"), ("601838", "sh"), ("603005", "sh"),
    ("600900", "sh"), ("600105", "sh"), ("600036", "sh"),
    ("600487", "sh"), ("600919", "sh"), ("000651", "sz"),
]


def fetch_kline(pre, code, n=1300):
    """拉前复权日线，返回 [(date, open, close, high, low, volume), ...]"""
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={pre}{code},day,,,{n},qfq"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=20).read()
    d = json.loads(raw)
    data = d["data"][f"{pre}{code}"]
    rows = []
    for key in ("qfqday", "day"):
        if key in data:
            for r in data[key]:
                # [date, open, close, high, low, volume]
                rows.append((r[0], float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
            break
    return rows


def main():
    con = duckdb.connect(str(DB_PATH))
    try:
        total = 0
        for code, pre in CODES:
            rows = fetch_kline(pre, code)
            if not rows:
                print(f"  ✗ {code} 无数据")
                continue
            # 幂等：upsert
            con.executemany(
                "INSERT INTO daily_kline (code, date, open, high, low, close, volume) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (code, date) DO UPDATE SET "
                "open=excluded.open, high=excluded.high, low=excluded.low, "
                "close=excluded.close, volume=excluded.volume",
                [(code, r[0], r[1], r[3], r[4], r[2], r[5]) for r in rows],
            )
            total += len(rows)
            print(f"  ✓ {code}: {len(rows)} 行（{rows[0][0]} ~ {rows[-1][0]}）")
        print(f"\n✓ daily_kline 批量写入 {total} 行")
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
