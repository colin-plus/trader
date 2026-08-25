"""API 路由：行情 / 分价 / 资金流 / 财务。"""
from fastapi import APIRouter, HTTPException, Query

from app import db

router = APIRouter(prefix="/api")


@router.get("/stocks")
def list_stocks():
    """关注的股票列表"""
    return [{"code": c, "name": n} for c, n in db.STOCKS.items()]


@router.get("/kline/{code}")
def kline(code: str, days: int = Query(120, ge=10, le=1000)):
    """日线行情（前复权）"""
    if code not in db.STOCKS:
        raise HTTPException(404, f"未跟踪的股票代码: {code}")
    rows = db.query_all(
        "SELECT date, open, high, low, close, volume FROM daily_kline "
        "WHERE code = ? ORDER BY date DESC LIMIT ?",
        [code, days],
    )
    rows.reverse()
    if not rows:
        raise HTTPException(404, f"{code} 无日线数据")
    return {"code": code, "name": db.STOCKS[code], "rows": rows}


@router.get("/fenjia/{code}")
def fenjia(code: str, days: int = Query(5, ge=1, le=30)):
    """分价成交量（近 N 个交易日，含主动买/卖）"""
    if code not in db.STOCKS:
        raise HTTPException(404, f"未跟踪的股票代码: {code}")
    rows = db.query_all(
        "SELECT date, price, vol, buy, sell FROM fenjia "
        "WHERE code = ? AND date >= (SELECT MAX(date) - INTERVAL (? - 1) DAY FROM fenjia WHERE code = ?) "
        "ORDER BY date, price",
        [code, days, code],
    )
    if not rows:
        raise HTTPException(404, f"{code} 无分价数据")
    return {"code": code, "name": db.STOCKS[code], "rows": rows}


@router.get("/fundflow/{code}")
def fundflow(code: str, days: int = Query(20, ge=5, le=120)):
    """资金流向（主力/超大单/大单/中单/小单，单位：亿）"""
    if code not in db.STOCKS:
        raise HTTPException(404, f"未跟踪的股票代码: {code}")
    rows = db.query_all(
        "SELECT date, zhuli, zdc, dd, zd, xd, pct, close, chg FROM fund_flow "
        "WHERE code = ? ORDER BY date DESC LIMIT ?",
        [code, days],
    )
    rows.reverse()
    if not rows:
        raise HTTPException(404, f"{code} 无资金流数据")
    return {"code": code, "name": db.STOCKS[code], "rows": rows}


@router.get("/meta")
def meta():
    """数据库元信息"""
    rows = db.query_all("SELECT key, value FROM meta")
    return {"meta": rows}
