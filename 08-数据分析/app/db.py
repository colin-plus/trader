"""duckdb 连接与查询封装。

单写者模型（DuckDB 无 WAL，文件级锁）：
- DuckDB 1.5.5 无 WAL：查询过的只读连接持有读快照会锁文件，阻塞其他进程写
- 故后端不缓存连接：每次查询临时开/关只读连接（锁短暂存在）
- 写操作（采集脚本、评估落库）走独立进程——后端查询间隙可写入
- 线程安全：连接不跨线程共享（每次新建）

注意：不要缓存连接（threading.local 也不行）——任何查询过的常驻连接
都会永久锁文件，导致评估/采集写进程报 Conflicting lock。
"""
import pathlib

import duckdb
import pandas as pd

DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"


def get_conn(read_only=True):
    """临时连接（用完必须 close 释放锁）。查询/写都短暂持有。"""
    return duckdb.connect(str(DB_PATH), read_only=read_only)


def query_all(sql, params=None):
    """执行查询并返回 dict 列表（连接用完即关，释放文件锁）

    用 duckdb 原生 fetchall + 列名映射（不用 pandas：其 NaN 转 JSON 会崩）。
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        cur = con.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        con.close()


def query_df(sql, params=None):
    """执行查询并返回 DataFrame（连接用完即关）"""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return con.execute(sql, params or []).fetchdf()
    finally:
        con.close()
