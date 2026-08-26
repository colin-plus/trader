#!/usr/bin/env python3
"""安全边际数据填充：margin_factor + margin_daily + margin_macro 种子数据。

数据源：腾讯/东财公开接口（因子取财报数据）。
种子阶段：为持仓/关注标的填充；后续接入 cron 日更。
"""
import pathlib
import sys

import duckdb

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"

# (code, report_date, eps, bps, dps, total_shares, float_shares)
# 因子为近似值（腾讯接口每股指标），正式采集待接入东财 F10
FACTORS = [
    # 成都银行：2025 年报（近似：EPS 2.11 / BPS 17.9 / DPS 0.63 / 总股本 39.7亿）
    ("601838", "2025-12-31", 2.11, 17.90, 0.63, 3970000000, 3970000000),
    # 华亚智能：2025 年报（近似）
    ("003043", "2025-12-31", 1.85, 12.40, 0.30, 80000000, 80000000),
    # 晶方科技：2025 年报（近似）
    ("603005", "2025-12-31", 0.95, 9.80, 0.20, 650000000, 650000000),
]

# 宏观：10 年期国债收益率（近值 %）
MACRO = [
    ("2026-08-26", 1.72),
]


def main():
    con = duckdb.connect(str(DB_PATH))
    try:
        # 1. margin_factor（幂等：先删后插）
        for code, rd, eps, bps, dps, ts, fs in FACTORS:
            con.execute("DELETE FROM margin_factor WHERE code = ? AND report_date = ?", [code, rd])
            con.execute(
                "INSERT INTO margin_factor (code, report_date, eps, bps, dps, total_shares, float_shares) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [code, rd, eps, bps, dps, ts, fs],
            )
        n_factor = con.execute("SELECT COUNT(*) FROM margin_factor").fetchone()[0]
        print(f"✓ margin_factor: {n_factor} 行")

        # 2. margin_daily：用 daily_kline 历史 × 最新因子回算 PE/PB/股息率
        for code, rd, eps, bps, dps, ts, fs in FACTORS:
            con.execute("DELETE FROM margin_daily WHERE code = ?", [code])
            con.execute(
                """
                INSERT INTO margin_daily (code, date, pe, pb, dividend_yield)
                SELECT k.code, k.date,
                       CASE WHEN ? > 0 THEN ROUND(k.close / ?, 2) ELSE NULL END,
                       CASE WHEN ? > 0 THEN ROUND(k.close / ?, 2) ELSE NULL END,
                       CASE WHEN ? > 0 AND k.close > 0 THEN ROUND(? / k.close * 100, 2) ELSE NULL END
                FROM daily_kline k
                WHERE k.code = ? AND k.date >= '2021-01-01'
                """,
                [eps, eps, bps, bps, dps, dps, code],
            )
            n = con.execute("SELECT COUNT(*) FROM margin_daily WHERE code = ?", [code]).fetchone()[0]
            print(f"  margin_daily {code}: {n} 行")

        # 3. margin_macro
        for d, y in MACRO:
            con.execute("INSERT INTO margin_macro VALUES (?, ?) ON CONFLICT DO NOTHING", [d, y])
        print(f"✓ margin_macro: {con.execute('SELECT COUNT(*) FROM margin_macro').fetchone()[0]} 行")
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
