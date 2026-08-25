#!/usr/bin/env python3
"""表重命名迁移：instrument → investable_asset，fenjia → price_distribution。

命名依据（金融领域建模）：
- investable_asset：股票+ETF 的顶层抽象（可投资资产），标准金融术语
- price_distribution：分价（每日每价格档成交量分布）

DuckDB 的 RENAME 会因外键依赖失败（daily_kline/fund_flow/finance/watchlist
都引用 instrument），采用全量重建模式：
1. 导出所有表数据（临时 CSV）
2. 重建全部表（新表名）
3. 回填数据
4. 校验
"""
import pathlib
import sys

import duckdb

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"
TMP_DIR = pathlib.Path("/tmp/trader_rename_export")


def export_table(con, table):
    """导出表到临时 parquet（保留类型信息，比 CSV 稳）"""
    out = TMP_DIR / f"{table}.parquet"
    con.execute(f"COPY (SELECT * FROM {table}) TO '{out}' (FORMAT PARQUET)")
    return out


def main():
    TMP_DIR.mkdir(exist_ok=True)
    con = duckdb.connect(str(DB_PATH))

    # 1. 导出所有现有数据
    tables = ["instrument", "watchlist", "daily_kline", "fenjia", "fund_flow", "finance", "meta"]
    for t in tables:
        if con.execute(f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name='{t}'").fetchone()[0] > 0:
            export_table(con, t)
            print(f"✓ 导出 {t}")

    # 2. 删除全部旧表（先删依赖方，后删被依赖方）
    con.execute("DROP TABLE IF EXISTS watchlist")
    con.execute("DROP TABLE IF EXISTS daily_kline")
    con.execute("DROP TABLE IF EXISTS fund_flow")
    con.execute("DROP TABLE IF EXISTS finance")
    con.execute("DROP TABLE IF EXISTS fenjia")
    con.execute("DROP TABLE IF EXISTS instrument")
    con.execute("DROP TABLE IF EXISTS meta")
    print("✓ 旧表已删除")

    # 3. 重建新 schema
    con.execute("""
    CREATE TABLE investable_asset (
      code       VARCHAR PRIMARY KEY,
      name       VARCHAR NOT NULL,
      type       VARCHAR NOT NULL,          -- 'stock' | 'etf'
      exchange   VARCHAR,
      industry   VARCHAR,
      list_date  DATE,
      created_at TIMESTAMP DEFAULT now()
    );
    CREATE TABLE watchlist (
      code       VARCHAR PRIMARY KEY REFERENCES investable_asset(code),
      added_at   DATE DEFAULT current_date,
      note       VARCHAR,
      sort_order INTEGER DEFAULT 0,
      active     BOOLEAN DEFAULT TRUE
    );
    CREATE TABLE daily_kline (
      code   VARCHAR REFERENCES investable_asset(code),
      date   DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
      PRIMARY KEY (code, date)
    );
    CREATE TABLE price_distribution (
      code  VARCHAR REFERENCES investable_asset(code),
      date  DATE, price DOUBLE, vol INTEGER, buy INTEGER, sell INTEGER,
      PRIMARY KEY (code, date, price)
    );
    CREATE TABLE fund_flow (
      code  VARCHAR REFERENCES investable_asset(code),
      date  DATE, zhuli DOUBLE, zdc DOUBLE, dd DOUBLE, zd DOUBLE, xd DOUBLE,
      pct DOUBLE, close DOUBLE, chg DOUBLE,
      PRIMARY KEY (code, date)
    );
    CREATE TABLE finance (
      code        VARCHAR REFERENCES investable_asset(code),
      report_date DATE, kind VARCHAR, payload JSON,
      PRIMARY KEY (code, report_date, kind)
    );
    CREATE TABLE meta (
      key VARCHAR PRIMARY KEY, value VARCHAR
    );
    """)
    print("✓ 新 schema 建表完成")

    # 4. 回填数据
    con.execute("INSERT INTO investable_asset SELECT * FROM read_parquet(?)", [str(TMP_DIR / "instrument.parquet")])
    con.execute("INSERT INTO watchlist SELECT * FROM read_parquet(?)", [str(TMP_DIR / "watchlist.parquet")])
    con.execute("INSERT INTO daily_kline SELECT * FROM read_parquet(?)", [str(TMP_DIR / "daily_kline.parquet")])
    con.execute("INSERT INTO price_distribution SELECT * FROM read_parquet(?)", [str(TMP_DIR / "fenjia.parquet")])
    con.execute("INSERT INTO fund_flow SELECT * FROM read_parquet(?)", [str(TMP_DIR / "fund_flow.parquet")])
    con.execute("INSERT INTO finance SELECT * FROM read_parquet(?)", [str(TMP_DIR / "finance.parquet")])
    con.execute("INSERT INTO meta SELECT * FROM read_parquet(?)", [str(TMP_DIR / "meta.parquet")])
    print("✓ 数据回填完成")

    # 5. 校验
    for t in ["investable_asset", "watchlist", "daily_kline", "price_distribution", "fund_flow", "finance", "meta"]:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n} 行")
    con.close()
    print("\n重命名完成")


if __name__ == "__main__":
    main()
