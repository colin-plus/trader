#!/usr/bin/env python3
"""安全边际实时采集：腾讯行情接口 → margin_daily / margin_factor。

数据源：qt.gtimg.cn（腾讯实时行情，免代理，字段布局见脚本内注释）。
用途：每日盘后（或盘中）采集关注标的的 PE/PB/股息率/股本，落库 margin_daily；
因子（EPS/BPS）由价格÷PE、价格÷PB 反推，更新 margin_factor。
"""
import pathlib
import sys
import urllib.request

import duckdb

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"

# 关注标的（与 seed_watchlist.py 一致）
CODES = [
    ("003043", "sz"), ("601838", "sh"), ("603005", "sh"),
    ("600900", "sh"), ("600105", "sh"), ("600036", "sh"),
    ("600487", "sh"), ("600919", "sh"), ("000651", "sz"),
]


def fetch_quotes(codes):
    """拉取腾讯行情，返回 {code: {name, price, pe, pb, dy, total_shares, float_shares}}"""
    q = ",".join(f"{pre}{code}" for code, pre in codes)
    url = f"http://qt.gtimg.cn/q={q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=15).read()
    text = raw.decode("gbk", errors="replace")
    result = {}
    for line in text.strip().split(";"):
        line = line.strip()
        if '="' not in line:
            continue
        _, payload = line.split('="', 1)
        f = payload.rstrip('"').split("~")
        code = f[2]
        try:
            result[code] = {
                "name": f[1],
                "price": float(f[3]),
                "pe": float(f[39]) if f[39] else None,      # PE(TTM)
                "pb": float(f[46]) if f[46] else None,      # PB
                "dy": float(f[64]) if f[64] else None,      # 股息率(%)
                "total_shares": int(float(f[72])) if f[72] else None,
                "float_shares": int(float(f[73])) if f[73] else None,
            }
        except (ValueError, IndexError):
            pass
    return result


def main():
    quotes = fetch_quotes(CODES)
    if len(quotes) < len(CODES):
        print(f"警告：仅拉到 {len(quotes)}/{len(CODES)} 只", file=sys.stderr)

    con = duckdb.connect(str(DB_PATH))
    try:
        today = con.execute("SELECT current_date").fetchone()[0]
        for code, pre in CODES:
            q = quotes.get(code)
            if not q:
                print(f"  ✗ {code} 无数据，跳过")
                continue
            price = q["price"]
            # 反推因子：EPS = 价格/PE，BPS = 价格/PB，DPS = 价格×股息率/100
            eps = round(price / q["pe"], 4) if q["pe"] else None
            bps = round(price / q["pb"], 4) if q["pb"] else None
            dps = round(price * q["dy"] / 100, 4) if q["dy"] else None
            # 因子：今日报告期（实时值，标记为当日快照）
            con.execute(
                "DELETE FROM margin_factor WHERE code = ? AND report_date = ?",
                [code, today],
            )
            con.execute(
                "INSERT INTO margin_factor (code, report_date, eps, bps, dps, total_shares, float_shares) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [code, today, eps, bps, dps, q["total_shares"], q["float_shares"]],
            )
            # 日估值快照（同日覆盖，历史保留——数据累积原则）
            con.execute(
                "INSERT INTO margin_daily (code, date, pe, pb, dividend_yield) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (code, date) DO UPDATE SET pe=excluded.pe, pb=excluded.pb, dividend_yield=excluded.dividend_yield",
                [code, today, q["pe"], q["pb"], q["dy"]],
            )
            print(f"  ✓ {code} {q['name']}: 价{price} PE{q['pe']} PB{q['pb']} 股息{q['dy']}%")
        n = con.execute("SELECT COUNT(*) FROM margin_daily WHERE date = ?", [today]).fetchone()[0]
        print(f"\n✓ margin_daily 今日落库 {n} 行；margin_factor 因子已更新")
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
