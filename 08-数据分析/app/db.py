"""duckdb 连接与查询封装。

读写分离（单写者模型）：
- 后端（本模块）只读连接 —— 查询/展示
- 写操作由采集脚本（scripts/）独占执行
- 避免后端与采集脚本争写锁
"""
import pathlib

import duckdb

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"

_conn = None


def get_conn():
    """单例只读连接"""
    global _conn
    if _conn is None:
        _conn = duckdb.connect(str(DB_PATH), read_only=True)
    return _conn


def query_df(sql, params=None):
    """执行查询返回 pandas DataFrame"""
    con = get_conn()
    if params:
        return con.execute(sql, params).fetchdf()
    return con.execute(sql).fetchdf()


def query_all(sql, params=None):
    """执行查询返回 dict 列表（date 字段转为 YYYY-MM-DD 字符串，NaT/NaN → None）"""
    import pandas as pd

    df = query_df(sql, params)
    if not df.empty:
        for col in df.columns:
            if "date" in col.lower() or col in ("added_at",):
                df[col] = df[col].where(pd.notna(df[col]), None).astype("string")
                df[col] = df[col].map(lambda v: str(v)[:10] if v is not None and str(v) != "<NA>" else None)
    # 纯 Python 层清洗：None/NaN/pd.NA → None
    # （pandas 的 map/apply/where 对 str/object dtype 列的 None 填充均不可靠，dict 层清洗最稳）
    recs = df.to_dict(orient="records")
    for r in recs:
        for k, v in r.items():
            if v is None or v is pd.NA or (isinstance(v, float) and pd.isna(v)):
                r[k] = None
    return recs
