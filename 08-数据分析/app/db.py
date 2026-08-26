"""duckdb 连接与查询封装。

单写者模型（事务级单写）：
- 后端连接用只读模式（查询/展示）——实测只读连接不阻塞其他进程写
- 写操作（采集脚本、评估落库）走独立进程——与只读后端共存无锁冲突
- 线程模型：duckdb 连接不可跨线程共享，threading.local 每线程一个连接

注意：不要用可写连接常驻——可写连接持有单写者锁，
会阻塞其他进程写（含采集脚本），实测报 Conflicting lock。
"""
import pathlib
import threading

import duckdb
import pandas as pd

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"

_local = threading.local()


def get_conn():
    """当前线程的只读连接（每线程一个，线程安全）"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = duckdb.connect(str(DB_PATH), read_only=True)
        _local.conn = conn
    return conn


def query_df(sql, params=None):
    """执行查询返回 pandas DataFrame"""
    con = get_conn()
    if params:
        df = con.execute(sql, params).fetchdf()
    else:
        df = con.execute(sql).fetchdf()
    return df if df is not None else pd.DataFrame()


def query_all(sql, params=None):
    """执行查询返回 dict 列表（date 字段转为 YYYY-MM-DD 字符串，NaT/NaN → None）"""
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
