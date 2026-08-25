#!/usr/bin/env python3
"""导入"我的"数据种子：华亚智能交易记录 + 当前持仓。

数据来源：知识库交易计划文档（交易明细，数字抄券商口径）。
用途：transaction/position 表首批数据，验证模型与 API。
"""
import pathlib
import sys

import duckdb

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"

# 华亚智能（003043）交易明细（含费），数字抄券商
# (id, code, trade_date, direction, price, shares, amount, fee, note)
TRANSACTIONS = [
    (1,  "003043", "2026-08-19", "buy",  73.03, 300, 21909.00, 5.48, "首次建仓"),
    (2,  "003043", "2026-08-20", "sell", 74.23, 200, 14846.00, 12.42, "做T卖出"),
    (3,  "003043", "2026-08-21", "buy",  71.69, 200, 14338.00, 5.00, "低吸"),
    (4,  "003043", "2026-08-21", "buy",  71.20, 200, 14240.00, 5.00, "低吸"),
    (5,  "003043", "2026-08-24", "sell", 73.70, 200, 14740.00, 12.37, "止盈"),
    (6,  "003043", "2026-08-24", "sell", 73.49, 200, 14698.00, 12.35, "止盈"),
    (7,  "003043", "2026-08-24", "buy",  71.70, 200, 14340.00, 5.00, "低吸"),
    (8,  "003043", "2026-08-25", "sell", 74.20, 200, 14840.00, 12.42, "减仓/止盈：300→100股"),
]

# 当前持仓（券商口径）：100 股，摊薄成本 71.745
POSITIONS = [
    ("003043", 100, 71.745),
]


def main():
    con = duckdb.connect(str(DB_PATH))

    # 幂等：清空重导（种子数据，简单处理）
    con.execute("DELETE FROM transaction")
    for t in TRANSACTIONS:
        con.execute(
            "INSERT INTO transaction (id, code, trade_date, direction, price, shares, amount, fee, note) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", t
        )
    print(f"✓ transaction: {len(TRANSACTIONS)} 笔")

    con.execute("DELETE FROM position")
    for p in POSITIONS:
        con.execute("INSERT INTO position (code, shares, cost) VALUES (?, ?, ?)", p)
    print(f"✓ position: {len(POSITIONS)} 条")

    # 验证
    print("\n=== 验证 ===")
    print(con.execute("SELECT id, code, trade_date, direction, price, shares, amount, fee FROM transaction ORDER BY trade_date, id").fetchdf().to_string(index=False))
    print()
    print(con.execute("SELECT code, shares, cost FROM position").fetchdf().to_string(index=False))
    con.close()
    print("\n种子数据导入完成")


if __name__ == "__main__":
    main()
