#!/usr/bin/env python3
"""数据库 schema 迁移：扁平结构 → 规范化模型。

变更：
- 新增 instrument（标的主数据：股票+ETF）
- 新增 watchlist（关注标的）
- 数据表加复合主键 + code 外键
- 新增 finance（财务：kind + JSON payload）
- 现有数据迁移（daily_kline/fenjia/fund_flow）

策略：重建新表 + INSERT SELECT 迁移（数据量小，秒级）。
"""
import pathlib
import sys

import duckdb

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"

SCHEMA_SQL = """
-- 标的主数据（股票 + ETF）
CREATE TABLE instrument (
  code       VARCHAR PRIMARY KEY,
  name       VARCHAR NOT NULL,
  type       VARCHAR NOT NULL,          -- 'stock' | 'etf'
  exchange   VARCHAR,                   -- 'SH' | 'SZ'
  industry   VARCHAR,
  list_date  DATE,
  created_at TIMESTAMP DEFAULT now()
);

-- 关注标的
CREATE TABLE watchlist (
  code       VARCHAR PRIMARY KEY REFERENCES instrument(code),
  added_at   DATE DEFAULT current_date,
  note       VARCHAR,
  sort_order INTEGER DEFAULT 0,
  active     BOOLEAN DEFAULT TRUE
);

-- 日线
CREATE TABLE daily_kline (
  code   VARCHAR REFERENCES instrument(code),
  date   DATE,
  open   DOUBLE,
  high   DOUBLE,
  low    DOUBLE,
  close  DOUBLE,
  volume DOUBLE,
  PRIMARY KEY (code, date)
);

-- 分价
CREATE TABLE fenjia (
  code  VARCHAR REFERENCES instrument(code),
  date  DATE,
  price DOUBLE,
  vol   INTEGER,
  buy   INTEGER,
  sell  INTEGER,
  PRIMARY KEY (code, date, price)
);

-- 资金流向
CREATE TABLE fund_flow (
  code  VARCHAR REFERENCES instrument(code),
  date  DATE,
  zhuli DOUBLE,
  zdc   DOUBLE,
  dd    DOUBLE,
  zd    DOUBLE,
  xd    DOUBLE,
  pct   DOUBLE,
  close DOUBLE,
  chg   DOUBLE,
  PRIMARY KEY (code, date)
);

-- 财务（kind: 'dividend' 分红 / 'income' 利润表 / 'balance' 资产负债表 ...）
CREATE TABLE finance (
  code        VARCHAR REFERENCES instrument(code),
  report_date DATE,
  kind        VARCHAR,
  payload     JSON,
  PRIMARY KEY (code, report_date, kind)
);

-- 元信息
CREATE TABLE meta (
  key   VARCHAR PRIMARY KEY,
  value VARCHAR
);
"""

# 已知标的信息（后续可通过工具页管理）
INSTRUMENTS = [
    ("603005", "晶方科技", "stock", "SH", "半导体"),
    ("601838", "成都银行", "stock", "SH", "银行"),
    ("003043", "华亚智能", "stock", "SZ", "金属结构件"),
]


def main():
    if not DB_PATH.exists():
        print(f"数据库不存在: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    con = duckdb.connect(str(DB_PATH))

    # 备份旧表（只改名，不删数据）
    for t in ["daily_kline", "fenjia", "fund_flow", "meta"]:
        if con.execute(f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name='{t}_old'").fetchone()[0] == 0:
            try:
                con.execute(f"ALTER TABLE {t} RENAME TO {t}_old")
                print(f"✓ 旧表 {t} → {t}_old")
            except Exception as e:
                print(f"⚠ 重命名 {t} 失败: {e}")

    # 建新 schema
    con.execute(SCHEMA_SQL)
    print("✓ 新 schema 建表完成")

    # 填充 instrument（必须先于数据迁移——外键要求被引用行存在）
    for code, name, typ, exch, ind in INSTRUMENTS:
        con.execute(
            "INSERT INTO instrument (code, name, type, exchange, industry) VALUES (?, ?, ?, ?, ?)",
            [code, name, typ, exch, ind],
        )
    print(f"✓ instrument 填充 {len(INSTRUMENTS)} 条")

    # 迁移数据
    con.execute("INSERT INTO daily_kline SELECT * FROM daily_kline_old")
    con.execute("INSERT INTO fenjia SELECT * FROM fenjia_old")
    con.execute("INSERT INTO fund_flow SELECT * FROM fund_flow_old")
    con.execute("INSERT INTO meta SELECT * FROM meta_old")
    print("✓ 数据迁移完成")

    # 填充 watchlist（默认全部关注）
    con.execute("INSERT INTO watchlist (code, sort_order) SELECT code, row_number() OVER (ORDER BY code) FROM instrument")
    print("✓ watchlist 填充完成")

    # 清理旧表
    for t in ["daily_kline_old", "fenjia_old", "fund_flow_old", "meta_old"]:
        con.execute(f"DROP TABLE {t}")
    print("✓ 旧表已清理")

    # 验证
    for t in ["instrument", "watchlist", "daily_kline", "fenjia", "fund_flow", "finance", "meta"]:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n} 行")

    con.close()
    print("\n迁移完成")


if __name__ == "__main__":
    main()
