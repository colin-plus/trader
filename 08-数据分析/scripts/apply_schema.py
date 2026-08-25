#!/usr/bin/env python3
"""应用数据模型（与 docs/schema.md 权威文档同步）。

工程化取舍（个人项目、数据量小、schema 变更低频）：
- 不做"差异检测+局部重建"（依赖链复杂、易错）
- 全量重建：导出全部数据(parquet) → 删旧表 → 建规范表 → 回填
- 幂等：运行 N 次结果一致；数据无损

用法：.venv/bin/python scripts/apply_schema.py
"""
import pathlib
import shutil
import sys
import tempfile

import duckdb

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"

# ==================== 规范 schema（与 docs/schema.md 同步） ====================
# fk: 外键目标表（code 列 → investable_asset(code)）；None 表示无外键
SCHEMA = {
    "investable_asset": {
        "comment": "标的主数据（股票+ETF 统一抽象，全库锚点）",
        "fk": None,
        "columns": [
            ("code", "VARCHAR NOT NULL", "标的代码（6位）"),
            ("name", "VARCHAR NOT NULL", "标的名称"),
            ("type", "VARCHAR NOT NULL", "类型：stock=股票 / etf=ETF"),
            ("exchange", "VARCHAR", "交易所：SH / SZ"),
            ("industry", "VARCHAR", "行业（仅股票）"),
            ("list_date", "DATE", "上市日期"),
            ("created_at", "TIMESTAMP DEFAULT now()", "记录创建时间"),
        ],
        "pk": ["code"],
        "checks": ["type IN ('stock','etf')"],
    },
    "watchlist": {
        "comment": "关注标的（软移除用 active，保留关注痕迹）",
        "fk": "investable_asset",
        "columns": [
            ("code", "VARCHAR NOT NULL", "标的代码"),
            ("added_at", "DATE DEFAULT current_date NOT NULL", "加入关注日期"),
            ("note", "VARCHAR", "关注备注"),
            ("sort_order", "INTEGER DEFAULT 0 NOT NULL", "列表排序（升序）"),
            ("active", "BOOLEAN DEFAULT TRUE NOT NULL", "是否启用"),
        ],
        "pk": ["code"],
        "checks": [],
    },
    "daily_kline": {
        "comment": "日线行情（前复权），K线页数据源",
        "fk": "investable_asset",
        "columns": [
            ("code", "VARCHAR NOT NULL", "标的代码"),
            ("date", "DATE NOT NULL", "交易日"),
            ("open", "DOUBLE NOT NULL", "开盘价"),
            ("high", "DOUBLE NOT NULL", "最高价"),
            ("low", "DOUBLE NOT NULL", "最低价"),
            ("close", "DOUBLE NOT NULL", "收盘价（前复权）"),
            ("volume", "INTEGER NOT NULL", "成交量（手）"),
        ],
        "pk": ["code", "date"],
        "checks": [],
    },
    "volume_profile": {
        "comment": "分价分布（每日每价格档成交量，Volume Profile）",
        "fk": "investable_asset",
        "columns": [
            ("code", "VARCHAR NOT NULL", "标的代码"),
            ("date", "DATE NOT NULL", "交易日"),
            ("price", "DOUBLE NOT NULL", "价格档位"),
            ("vol", "INTEGER NOT NULL", "该价位成交量（手）"),
            ("buy", "INTEGER NOT NULL", "主动买量（手）"),
            ("sell", "INTEGER NOT NULL", "主动卖量（手）"),
        ],
        "pk": ["code", "date", "price"],
        "checks": [],
    },
    "fund_flow": {
        "comment": "资金流向（单位：亿元，字段名沿用东财数据源缩写）",
        "fk": "investable_asset",
        "columns": [
            ("code", "VARCHAR NOT NULL", "标的代码"),
            ("date", "DATE NOT NULL", "交易日"),
            ("zhuli", "DOUBLE NOT NULL", "主力净流入（亿）"),
            ("zdc", "DOUBLE NOT NULL", "超大单净流入（亿）"),
            ("dd", "DOUBLE NOT NULL", "大单净流入（亿）"),
            ("zd", "DOUBLE NOT NULL", "中单净流入（亿）"),
            ("xd", "DOUBLE NOT NULL", "小单净流入（亿）"),
            ("pct", "DOUBLE NOT NULL", "涨跌幅（%）"),
            ("close", "DOUBLE NOT NULL", "收盘价"),
            ("chg", "DOUBLE", "主力净流入占比（%）"),
        ],
        "pk": ["code", "date"],
        "checks": [],
    },
    "finance": {
        "comment": "财务数据（kind 分类 + JSON payload，新指标加 kind 不改表）",
        "fk": "investable_asset",
        "columns": [
            ("code", "VARCHAR NOT NULL", "标的代码"),
            ("report_date", "DATE NOT NULL", "报告期（除权日/财报截止日）"),
            ("kind", "VARCHAR NOT NULL", "类型：dividend/income/balance"),
            ("payload", "JSON NOT NULL", "该 kind 的具体字段（见 docs/schema.md）"),
        ],
        "pk": ["code", "report_date", "kind"],
        "checks": ["kind IN ('dividend','income','balance')"],
    },
    "meta": {
        "comment": "库级元信息（键值）",
        "fk": None,
        "columns": [
            ("key", "VARCHAR NOT NULL", "配置键（如 kline_updated_at）"),
            ("value", "VARCHAR", "配置值"),
        ],
        "pk": ["key"],
        "checks": [],
    },
}

# 建表顺序（被依赖方在前）
TABLE_ORDER = [
    "investable_asset",
    "watchlist",
    "daily_kline",
    "volume_profile",
    "fund_flow",
    "finance",
    "meta",
]


def build_ddl(name, spec):
    """由 spec 生成 CREATE TABLE DDL（含列级 CHECK、外键）"""
    lines = [f"CREATE TABLE {name} ("]
    for col, typ, _ in spec["columns"]:
        lines.append(f"  {col} {typ},")
    lines.append(f"  PRIMARY KEY ({', '.join(spec['pk'])}),")
    for chk in spec["checks"]:
        lines.append(f"  CHECK ({chk}),")
    if spec["fk"]:
        lines.append(f"  FOREIGN KEY (code) REFERENCES {spec['fk']}(code)")
    # 去掉最后的逗号（若 FK 是最后一行）
    ddl = "\n".join(lines).rstrip(",") + "\n)"
    return ddl


def main():
    if not DB_PATH.exists():
        print(f"数据库不存在: {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    src_con = duckdb.connect(str(DB_PATH), read_only=True)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="schema_backup_"))
    new_db = DB_PATH.parent / "trader.duckdb.new"
    try:
        # 1. 导出全部现有数据（从旧库只读导出，不影响任何依赖）
        existing = [
            t for t in TABLE_ORDER
            if src_con.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name=?", [t]
            ).fetchone()[0] > 0
        ]
        for t in existing:
            n = src_con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            if n > 0:
                src_con.execute(f"COPY (SELECT * FROM {t}) TO '{tmp / t}.parquet' (FORMAT PARQUET)")
                print(f"✓ 导出 {t}: {n} 行")
            else:
                print(f"· {t}: 空表，跳过导出")
        src_con.close()

        # 2. 建全新库文件（blue-green 替换，规避 DuckDB 目录残留依赖问题）
        if new_db.exists():
            new_db.unlink()
        con = duckdb.connect(str(new_db))
        for t in TABLE_ORDER:
            spec = SCHEMA[t]
            con.execute(build_ddl(t, spec))
            for col, _, comment in spec["columns"]:
                con.execute(f"COMMENT ON COLUMN {t}.{col} IS '{comment}'")
            con.execute(f"COMMENT ON TABLE {t} IS '{spec['comment']}'")
        print("✓ 规范表建表完成（含 COMMENT/NOT NULL/CHECK/FK）")

        # 3. 回填数据
        for t in TABLE_ORDER:
            parquet = tmp / f"{t}.parquet"
            if parquet.exists():
                spec = SCHEMA[t]
                cols = ", ".join(c[0] for c in spec["columns"])
                con.execute(f"INSERT INTO {t} ({cols}) SELECT {cols} FROM read_parquet('{parquet}')")
        print("✓ 数据回填完成")
        con.close()

        # 4. 原子替换旧库
        backup = DB_PATH.parent / "trader.duckdb.bak"
        if backup.exists():
            backup.unlink()
        DB_PATH.rename(backup)      # 旧库 → .bak（保留一份回退）
        new_db.rename(DB_PATH)      # 新库 → 正式路径
        print(f"✓ 已替换（旧库备份: {backup.name}）")

        # 5. 校验新库
        con = duckdb.connect(str(DB_PATH), read_only=True)
        print("\n=== 校验 ===")
        for t in TABLE_ORDER:
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t}: {n} 行")
        con.close()
    finally:
        try:
            src_con.close()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)
    print("\napply_schema 完成")


if __name__ == "__main__":
    main()
