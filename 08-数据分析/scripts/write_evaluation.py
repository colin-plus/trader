#!/usr/bin/env python3
"""按需评估落库（独立进程执行，规避 DuckDB 同进程只读/读写连接冲突）。

由 FastAPI 通过 subprocess 调用；参数 JSON 从 stdin 传入。
"""
import json
import pathlib
import sys

import duckdb

DB = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"

body = json.loads(sys.stdin.read())
code = body["code"]
margin_level = body["margin_level"]
decision = body.get("decision")
note = body.get("note")

con = duckdb.connect(str(DB))
try:
    # 当前估值快照
    latest = con.execute(
        "SELECT date, pe, pb, dividend_yield FROM margin_daily "
        "WHERE code = ? AND pe IS NOT NULL ORDER BY date DESC LIMIT 1",
        [code],
    ).fetchone()
    price_row = con.execute(
        "SELECT close FROM daily_kline WHERE code = ? ORDER BY date DESC LIMIT 1", [code]
    ).fetchone()
    price = price_row[0] if price_row else None
    pe = pb = dy = pe_pct = pb_pct = None
    if latest:
        pe, pb, dy = latest[1], latest[2], latest[3]
        if pe is not None:
            pe_hist = [r[0] for r in con.execute(
                "SELECT pe FROM margin_daily WHERE code = ? AND pe IS NOT NULL "
                "AND date >= current_date - INTERVAL '5 years' ORDER BY pe",
                [code],
            ).fetchall()]
            if pe_hist:
                pe_pct = round(sum(1 for h in pe_hist if h <= pe) / len(pe_hist) * 100, 1)
        if pb is not None:
            pb_hist = [r[0] for r in con.execute(
                "SELECT pb FROM margin_daily WHERE code = ? AND pb IS NOT NULL "
                "AND date >= current_date - INTERVAL '5 years' ORDER BY pb",
                [code],
            ).fetchall()]
            if pb_hist:
                pb_pct = round(sum(1 for h in pb_hist if h <= pb) / len(pb_hist) * 100, 1)
    max_id = con.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM margin_evaluation").fetchone()[0]
    con.execute(
        "INSERT INTO margin_evaluation (id, code, eval_date, price, pe, pb, dividend_yield, "
        "pe_percentile, pb_percentile, margin_level, decision, note) "
        "VALUES (?, ?, current_date, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [max_id, code, price, pe, pb, dy, pe_pct, pb_pct, margin_level, decision, note],
    )
    print(json.dumps({"id": max_id, "code": code, "margin_level": margin_level}, ensure_ascii=False))
finally:
    con.close()
