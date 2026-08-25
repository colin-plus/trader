#!/usr/bin/env python3
"""表重命名迁移：instrument → target，fenjia → price_distribution。

DuckDB 不允许 RENAME 被外键依赖的表，采用重建方式：
1. 备份原表（RENAME 到 _old）
2. 建新表（新名字）
3. 迁移数据
4. 重建 watchlist（其外键引用 target）
5. 清理旧表
"""
import pathlib
import sys

import duckdb

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"


def main():
    con = duckdb.connect(str(DB_PATH))

    # 0. 先删 watchlist（其外键引用 instrument，会阻止 RENAME）
    con.execute("DROP TABLE IF EXISTS watchlist")
    print("✓ watchlist 暂删（将重建）")

    # 1. 旧表改名（备份）
    for old, new in [("instrument", "instrument_old"), ("fenjia", "fenjia_old")]:
        if con.execute(f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name='{old}'").fetchone()[0] > 0:
            con.execute(f"ALTER TABLE {old} RENAME TO {new}")
            print(f"✓ {old} → {new}")

    # 2. 建新表
    con.execute("""
    CREATE TABLE target (
      code       VARCHAR PRIMARY KEY,
      name       VARCHAR NOT NULL,
      type       VARCHAR NOT NULL,          -- 'stock' | 'etf'
      exchange   VARCHAR,
      industry   VARCHAR,
      list_date  DATE,
      created_at TIMESTAMP DEFAULT now()
    );
    """)
    con.execute("""
    CREATE TABLE price_distribution (
      code  VARCHAR REFERENCES target(code),
      date  DATE,
      price DOUBLE,
      vol   INTEGER,
      buy   INTEGER,
      sell  INTEGER,
      PRIMARY KEY (code, date, price)
    );
    """)
    print("✓ target / price_distribution 建表完成")

    # 4. 迁移数据
    con.execute("INSERT INTO target SELECT * FROM instrument_old")
    con.execute("INSERT INTO price_distribution SELECT * FROM fenjia_old")
    print("✓ 数据迁移完成")

    # 5. 重建 watchlist（引用 target）
    con.execute("""
    CREATE TABLE watchlist (
      code       VARCHAR PRIMARY KEY REFERENCES target(code),
      added_at   DATE DEFAULT current_date,
      note       VARCHAR,
      sort_order INTEGER DEFAULT 0,
      active     BOOLEAN DEFAULT TRUE
    );
    """)
    con.execute("INSERT INTO watchlist (code, sort_order) SELECT code, row_number() OVER (ORDER BY code) FROM target")
    print("✓ watchlist 重建完成")

    # 6. 清理旧表
    for t in ["instrument_old", "fenjia_old"]:
        con.execute(f"DROP TABLE {t}")
    print("✓ 旧表清理完成")

    # 7. 验证
    for t in ["target", "watchlist", "daily_kline", "price_distribution", "fund_flow", "finance", "meta"]:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n} 行")
    con.close()
    print("\n重命名完成")


if __name__ == "__main__":
    main()
