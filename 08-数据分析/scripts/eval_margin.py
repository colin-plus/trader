#!/usr/bin/env python3
"""安全边际批量评估落库：9 只关注标的 → margin_evaluation（今日一次评估一条）。

判定规则（对应《安全边际评估框架》三把尺子）：
- 尺子A 股息率：≥ 3% 亮（基准 10 年国债 1.7% × 1.5 ≈ 2.5%，取 3% 严格线）
- 尺子B 分位：PE/PB 5年分位 ≤ 30% 亮
- 尺子C PB：≤ 1.5 亮（银行股放宽）
结论：两把以上亮 = 充足；一把亮 = 一般；股息/分位均差 = 不足；高PE高PB = 无
"""
import pathlib
import sys

import duckdb

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"

# 尺子阈值
DY_OK = 3.0          # 股息率 ≥ 3%
PCT_OK = 30.0        # 分位 ≤ 30%
PB_OK = 1.5          # PB ≤ 1.5

CODES = ["600900", "600036", "600919", "000651", "600105", "600487", "003043", "601838", "603005"]


def evaluate(code: str, latest: dict, pct: dict, price: float) -> dict:
    pe, pb, dy = latest["pe"], latest["pb"], latest["dividend_yield"]
    pe_pct, pb_pct = pct["pe"], pct["pb"]
    # 三把尺子（分位不足数据时按不亮处理）
    a = dy is not None and dy >= DY_OK
    b = (pe_pct is not None and pe_pct <= PCT_OK) or (pb_pct is not None and pb_pct <= PCT_OK)
    c = pb is not None and pb <= PB_OK
    lights = sum([a, b, c])
    if lights >= 2:
        level = "充足"
    elif lights == 1:
        level = "一般"
    elif pe is not None and pe > 30:
        level = "无"
    else:
        level = "不足"
    return {
        "price": price,
        "pe": pe, "pb": pb, "dy": dy,
        "pe_pct": pe_pct, "pb_pct": pb_pct,
        "level": level, "lights": lights,
        "detail": f"股息率{'✓' if a else '✗'}({dy}%) 分位{'✓' if b else '✗'}(PE{pe_pct}%/PB{pb_pct}%) PB{'✓' if c else '✗'}({pb})",
    }


def main():
    con = duckdb.connect(str(DB_PATH))
    try:
        today = con.execute("SELECT current_date").fetchone()[0]
        results = []
        for code in CODES:
            latest = con.execute(
                "SELECT date, pe, pb, dividend_yield FROM margin_daily "
                "WHERE code = ? ORDER BY date DESC LIMIT 1", [code]
            ).fetchone()
            if not latest:
                print(f"  ✗ {code} 无 margin_daily，跳过")
                continue
            # 5 年分位（SQL 算百分位）
            pct = con.execute(
                "SELECT "
                "ROUND((SELECT COUNT(*) FROM margin_daily WHERE code=? AND pe IS NOT NULL AND pe <= ?) * 100.0 / "
                "(SELECT COUNT(*) FROM margin_daily WHERE code=? AND pe IS NOT NULL), 1) AS pe_pct, "
                "ROUND((SELECT COUNT(*) FROM margin_daily WHERE code=? AND pb IS NOT NULL AND pb <= ?) * 100.0 / "
                "(SELECT COUNT(*) FROM margin_daily WHERE code=? AND pb IS NOT NULL), 1) AS pb_pct",
                [code, latest[1], code, code, latest[2], code]
            ).fetchone()
            # 最新价格（daily_kline 最新收盘）
            price_row = con.execute(
                "SELECT close FROM daily_kline WHERE code=? ORDER BY date DESC LIMIT 1", [code]
            ).fetchone()
            price = price_row[0] if price_row else latest[0]
            r = evaluate(code, {"pe": latest[1], "pb": latest[2], "dividend_yield": latest[3]},
                         {"pe": pct[0], "pb": pct[1]}, price)
            r["code"] = code
            # 落库（幂等：同日同标的覆盖；id 手动分配）
            con.execute(
                "DELETE FROM margin_evaluation WHERE code=? AND eval_date=? AND note LIKE '批量评估%'",
                [code, today],
            )
            max_id = con.execute("SELECT COALESCE(MAX(id), 0) FROM margin_evaluation").fetchone()[0]
            con.execute(
                "INSERT INTO margin_evaluation (id, code, eval_date, price, pe, pb, dividend_yield, "
                "pe_percentile, pb_percentile, margin_level, discount, decision, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [max_id + 1, code, today, r["price"], r["pe"], r["pb"], r["dy"], r["pe_pct"], r["pb_pct"],
                 r["level"], None, None, f"批量评估：{r['detail']}"],
            )
            results.append(r)
            print(f"  ✓ {code}: {r['level']}（{r['detail']}）")

        n = con.execute("SELECT COUNT(*) FROM margin_evaluation WHERE eval_date=?", [today]).fetchone()[0]
        print(f"\n✓ margin_evaluation 今日落库 {n} 条")
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
