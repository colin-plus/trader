#!/usr/bin/env python3
"""按需评估落库（独立进程执行，规避 DuckDB 同进程只读/读写连接冲突）。

参数（stdin JSON）：{"code": "601838"}
流程：读当前估值 → 数据校验 → 三把尺子自动算结论 → 落库
失败：stderr 输出原因，exit 1（API 转 400 提示）
"""
import json
import pathlib
import sys

import duckdb

DB = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


body = json.loads(sys.stdin.read())
code = str(body.get("code", "")).strip()
if not code:
    fail("code 必填")

con = duckdb.connect(str(DB))
try:
    # 标的是否存在
    asset = con.execute(
        "SELECT name FROM investable_asset WHERE code = ?", [code]
    ).fetchone()
    if not asset:
        fail(f"标的 {code} 不存在")

    # 最新估值（margin_daily 任意日期，标注数据日期）
    latest = con.execute(
        "SELECT date, pe, pb, dividend_yield FROM margin_daily "
        "WHERE code = ? AND pe IS NOT NULL ORDER BY date DESC LIMIT 1",
        [code],
    ).fetchone()
    if not latest:
        fail(f"{asset[0]}（{code}）无估值数据，请先运行采集（collect_margin）")

    eval_date, pe, pb, dy = latest
    # 数据合理性：PE/PB/股息率至少有一个有效
    if (pe is None or pe <= 0) and (pb is None or pb <= 0) and (dy is None or dy <= 0):
        fail(f"{asset[0]}（{code}）估值数据异常（PE={pe}, PB={pb}, 股息={dy}），无法计算结论")

    # 最新价格
    price_row = con.execute(
        "SELECT close FROM daily_kline WHERE code = ? ORDER BY date DESC LIMIT 1", [code]
    ).fetchone()
    price = price_row[0] if price_row else None

    # 5 年分位（PE/PB）
    pe_pct = pb_pct = None
    if pe is not None and pe > 0:
        pe_hist = [r[0] for r in con.execute(
            "SELECT pe FROM margin_daily WHERE code = ? AND pe IS NOT NULL AND pe > 0 "
            "AND date >= current_date - INTERVAL '5 years' ORDER BY pe",
            [code],
        ).fetchall()]
        if pe_hist:
            pe_pct = round(sum(1 for h in pe_hist if h <= pe) / len(pe_hist) * 100, 1)
    if pb is not None and pb > 0:
        pb_hist = [r[0] for r in con.execute(
            "SELECT pb FROM margin_daily WHERE code = ? AND pb IS NOT NULL AND pb > 0 "
            "AND date >= current_date - INTERVAL '5 years' ORDER BY pb",
            [code],
        ).fetchall()]
        if pb_hist:
            pb_pct = round(sum(1 for h in pb_hist if h <= pb) / len(pb_hist) * 100, 1)

    # 三把尺子（与 eval_margin.py 同规则）：
    # A 股息率≥3% | B 分位≤30% | C PB≤1.5
    lights = 0
    if dy is not None and dy >= 3:
        lights += 1
    if (pe_pct is not None and pe_pct <= 30) or (pb_pct is not None and pb_pct <= 30):
        lights += 1
    if pb is not None and pb <= 1.5:
        lights += 1

    if lights >= 2:
        margin_level = "充足"
    elif lights == 1:
        margin_level = "一般"
    elif pe is not None and pe > 30:
        margin_level = "无边际"
    else:
        margin_level = "不足"

    # 落库（幂等：同日同标的覆盖——先删旧记录，保证每天每标的一条）
    con.execute(
        "DELETE FROM margin_evaluation WHERE code = ? AND eval_date = ?",
        [code, str(eval_date)],
    )
    max_id = con.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM margin_evaluation").fetchone()[0]
    con.execute(
        "INSERT INTO margin_evaluation (id, code, eval_date, price, pe, pb, dividend_yield, "
        "pe_percentile, pb_percentile, margin_level, discount) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
        [max_id, code, str(eval_date), price, pe, pb, dy, pe_pct, pb_pct, margin_level],
    )
    print(json.dumps({"id": max_id, "code": code, "margin_level": margin_level,
                      "eval_date": str(eval_date)}, ensure_ascii=False))
finally:
    con.close()
