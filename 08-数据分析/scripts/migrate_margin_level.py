#!/usr/bin/env python3
"""一次性迁移：margin_evaluation '无' → '无边际'（含约束更新）。

流程：导出转换 → DROP 旧表 → apply_schema 重建（新 CHECK）→ 回填。
"""
import pathlib
import subprocess
import sys

import duckdb

ROOT = pathlib.Path(__file__).parent.parent
DB = ROOT / "data" / "trader.duckdb"

# 1. 导出并转换
con = duckdb.connect(str(DB))
rows = con.execute(
    "SELECT id, code, eval_date, price, pe, pb, dividend_yield, pe_percentile, pb_percentile, "
    "CASE WHEN margin_level='无' THEN '无边际' ELSE margin_level END, discount, decision, note "
    "FROM margin_evaluation"
).fetchall()
print(f"导出 {len(rows)} 条（'无'已转换'无边际'）")

# 2. 删旧表（旧 CHECK 会拒绝新值，必须先删）
con.execute("DROP TABLE margin_evaluation")
print("旧表已删")
con.close()

# 3. apply_schema 重建（新 CHECK 约束）
r = subprocess.run([sys.executable, "scripts/apply_schema.py"], cwd=ROOT, capture_output=True, text=True)
print(r.stdout[-300:] if r.returncode == 0 else f"apply_schema 失败: {r.stderr[-500:]}")

# 4. 回填转换后数据
con = duckdb.connect(str(DB))
for row in rows:
    con.execute(
        "INSERT INTO margin_evaluation (id, code, eval_date, price, pe, pb, dividend_yield, "
        "pe_percentile, pb_percentile, margin_level, discount, decision, note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        list(row),
    )
n = con.execute("SELECT COUNT(*) FROM margin_evaluation").fetchone()[0]
print(f"回填完成：{n} 条")
for r in con.execute("SELECT margin_level, COUNT(*) FROM margin_evaluation GROUP BY margin_level ORDER BY margin_level").fetchall():
    print(f"  {r[0]}: {r[1]}")
con.close()
print("迁移完成")
