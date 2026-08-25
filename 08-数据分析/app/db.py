"""duckdb 连接与查询封装。"""
import pathlib

import duckdb

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"

STOCKS = {
    "603005": "晶方科技",
    "601838": "成都银行",
    "003043": "华亚智能",
}

_conn = None


def get_conn():
    """单例连接（duckdb 默认单写者，读多场景一个连接够用）"""
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
    """执行查询返回 dict 列表（date 字段转为 YYYY-MM-DD 字符串）"""
    df = query_df(sql, params)
    if not df.empty and "date" in df.columns:
        df["date"] = df["date"].astype(str)
    return df.to_dict(orient="records")
