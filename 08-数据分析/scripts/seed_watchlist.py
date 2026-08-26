#!/usr/bin/env python3
"""关注列表种子：维护 watchlist（幂等，可反复运行）。

新增关注 = 在此列表加一行再运行本脚本。
"""
import pathlib
import sys

import duckdb

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"

# 关注列表（code, 排序, 备注）——sort_order 从 1 递增
WATCHLIST = [
    ("003043", 1, "华亚智能：持仓，波段做T"),
    ("601838", 2, "成都银行：持仓，做T底仓"),
    ("603005", 3, "晶方科技：已清仓，跟踪"),
    ("600900", 4, "长江电力：高股息观察"),
    ("600105", 5, "永鼎股份：跟踪"),
    ("600036", 6, "招商银行：高股息观察"),
    ("600487", 7, "亨通光电：跟踪"),
    ("600919", 8, "江苏银行：高股息观察"),
    ("000651", 9, "格力电器：高股息观察"),
]


def main():
    con = duckdb.connect(str(DB_PATH))
    try:
        for code, so, note in WATCHLIST:
            con.execute(
                "INSERT INTO watchlist (code, added_at, note, sort_order, active) "
                "VALUES (?, current_date, ?, ?, TRUE) "
                "ON CONFLICT (code) DO UPDATE SET "
                "note=excluded.note, sort_order=excluded.sort_order, active=TRUE",
                [code, note, so],
            )
            print(f"  ✓ {code} {note}")
        rows = con.execute("SELECT COUNT(*) FROM watchlist WHERE active").fetchone()[0]
        print(f"\n✓ watchlist: {rows} 只关注")
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
