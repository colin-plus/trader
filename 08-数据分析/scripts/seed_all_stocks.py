#!/usr/bin/env python3
"""全市场股票导入：market.duckdb → trader.duckdb（investable_asset）。

数据源：/Users/zhanglubing/Github/market/data/market.duckdb（DBX 数据浏览器的 DuckDB 库）
  - stock 表：全市场股票基础信息（code/name/industry_code/list_date/is_active）
  - industry 表：3 级行业分类（code/name/level/parent_code）
目标：trader.duckdb 的 investable_asset（全库锚点表）

映射规则：
  - code      ← stock.code
  - name      ← stock.name（去除空格，如 '五 粮 液' → '五粮液'）
  - type      ← 'stock'（本库仅沪深股票，无 ETF）
  - exchange  ← 6xx=SH / 0xx|3xx=SZ（按代码前缀推导）
  - industry  ← 一级行业名（industry_code 沿父链追溯至 level=1；无映射留 NULL）
  - list_date ← stock.list_date

幂等：INSERT OR REPLACE（以 code 为主键），可重复运行；重复运行等价于全量同步。
"""
import pathlib
import sys

import duckdb

MARKET_DB = pathlib.Path("/Users/zhanglubing/Github/market/data/market.duckdb")
TRADER_DB = pathlib.Path(__file__).resolve().parent.parent / "data" / "trader.duckdb"


def load_industry_map(con):
    """industry 表 → {叶子code: 一级行业名}。"""
    rows = con.execute("SELECT code, name, level, parent_code FROM industry").fetchall()
    by_code = {r[0]: {"name": r[1], "level": r[2], "parent": r[3]} for r in rows}
    out = {}
    for code, node in by_code.items():
        cur = node
        # 沿父链向上追溯 level=1（行业是树，最多 3 层）
        while cur["level"] > 1 and cur["parent"] and cur["parent"] in by_code:
            cur = by_code[cur["parent"]]
        if cur["level"] == 1:
            out[code] = cur["name"]
    return out


def derive_exchange(code):
    if code.startswith("6"):
        return "SH"
    return "SZ"  # 本库仅沪深：0xx/3xx


def main():
    if not MARKET_DB.exists():
        print(f"✗ 数据源不存在: {MARKET_DB}")
        sys.exit(1)

    src = duckdb.connect(str(MARKET_DB), read_only=True)
    dst = duckdb.connect(str(TRADER_DB))

    print(f"数据源: {MARKET_DB}")
    ind_map = load_industry_map(src)
    print(f"行业映射: {len(ind_map)} 个行业码 → 一级行业名")

    # 全市场股票（全部 is_active）
    stocks = src.execute(
        "SELECT code, name, industry_code, list_date FROM stock WHERE is_active"
    ).fetchall()
    print(f"读取股票: {len(stocks)} 只")

    # 构建写入行
    rows = []
    mapped_industry = 0
    for code, name, ind_code, list_date in stocks:
        clean_name = (name or "").replace(" ", "").strip()
        industry = ind_map.get(ind_code) if ind_code else None
        if industry:
            mapped_industry += 1
        rows.append((code, clean_name, "stock", derive_exchange(code), industry, list_date))

    # 幂等写入（blue-green 不必要：investable_asset 无外键依赖方约束问题，
    # 直接 INSERT OR REPLACE 即可，code 主键天然防重）
    dst.execute("BEGIN")
    dst.executemany(
        """
        INSERT OR REPLACE INTO investable_asset (code, name, type, exchange, industry, list_date)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    dst.execute("COMMIT")

    n = dst.execute("SELECT COUNT(*) FROM investable_asset").fetchone()[0]
    n_etf = dst.execute(
        "SELECT COUNT(*) FROM investable_asset WHERE type='etf'"
    ).fetchone()[0]
    n_ind = dst.execute(
        "SELECT COUNT(*) FROM investable_asset WHERE industry IS NOT NULL"
    ).fetchone()[0]

    print(f"✔ 写入完成: investable_asset 共 {n} 行（股票 {n - n_etf} / ETF {n_etf}）")
    print(f"✔ 行业覆盖: {n_ind}/{n}（{n_ind / max(n, 1) * 100:.1f}%）")
    print(f"✔ 行业映射来源: {mapped_industry}/{len(stocks)} 只股票有行业码")

    # 样例抽查
    print("\n抽查 5 条:")
    for r in dst.execute(
        "SELECT code, name, type, exchange, industry, list_date FROM investable_asset WHERE type='stock' ORDER BY code LIMIT 5"
    ).fetchall():
        print(" ", r)

    src.close()
    dst.close()


if __name__ == "__main__":
    main()
