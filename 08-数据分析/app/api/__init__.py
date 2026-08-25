"""API 路由：行情 / 分价 / 资金流 / 财务 / 标的 / 我的。"""
from fastapi import APIRouter, HTTPException, Query

from app import db, performance

router = APIRouter(prefix="/api")


@router.get("/stocks")
def list_stocks():
    """关注的股票列表（含类型，前端按类型裁剪功能）"""
    rows = db.query_all(
        "SELECT i.code, i.name, i.type FROM investable_asset i "
        "JOIN watchlist w ON i.code = w.code WHERE w.active ORDER BY w.sort_order"
    )
    return rows


@router.get("/assets")
def list_assets():
    """全部标的（含未关注的）"""
    return db.query_all("SELECT code, name, type, exchange, industry, list_date FROM investable_asset ORDER BY code")


@router.get("/watchlist")
def get_watchlist():
    """关注列表明细"""
    return db.query_all(
        "SELECT w.code, i.name, i.type, w.added_at, w.note, w.sort_order "
        "FROM watchlist w JOIN investable_asset i ON i.code = w.code WHERE w.active ORDER BY w.sort_order"
    )


@router.get("/kline/{code}")
def kline(code: str, days: int = Query(120, ge=10, le=1000)):
    """日线行情（前复权）"""
    if code not in _valid_codes():
        raise HTTPException(404, f"未跟踪的股票代码: {code}")
    rows = db.query_all(
        "SELECT date, open, high, low, close, volume FROM daily_kline "
        "WHERE code = ? ORDER BY date DESC LIMIT ?",
        [code, days],
    )
    rows.reverse()
    if not rows:
        raise HTTPException(404, f"{code} 无日线数据")
    return {"code": code, "name": _asset_name(code), "rows": rows}


@router.get("/volume-profile/{code}")
def volume_profile(code: str, days: int = Query(5, ge=1, le=30)):
    """分价成交量（近 N 个交易日，含主动买/卖）"""
    if code not in _valid_codes():
        raise HTTPException(404, f"未跟踪的股票代码: {code}")
    rows = db.query_all(
        "SELECT date, price, vol, buy, sell FROM volume_profile "
        "WHERE code = ? AND date >= (SELECT MAX(date) - INTERVAL (? - 1) DAY FROM volume_profile WHERE code = ?) "
        "ORDER BY date, price",
        [code, days, code],
    )
    if not rows:
        raise HTTPException(404, f"{code} 无分价数据")
    return {"code": code, "name": _asset_name(code), "rows": rows}


@router.get("/capital-flow/{code}")
def capital_flow(code: str, days: int = Query(20, ge=5, le=120)):
    """资金流向（日）（主力/超大单/大单/中单/小单，单位：亿）"""
    if code not in _valid_codes():
        raise HTTPException(404, f"未跟踪的股票代码: {code}")
    rows = db.query_all(
        "SELECT date, zhuli, zdc, dd, zd, xd, pct, close, chg FROM daily_capital_flow "
        "WHERE code = ? ORDER BY date DESC LIMIT ?",
        [code, days],
    )
    rows.reverse()
    if not rows:
        raise HTTPException(404, f"{code} 无资金流数据")
    return {"code": code, "name": _asset_name(code), "rows": rows}


@router.get("/finance/{code}")
def finance(code: str, kind: str = Query("dividend", pattern="^(dividend|snapshot|income|balance)$")):
    """财务数据（默认分红；kind: dividend/snapshot/income/balance）"""
    if code not in _valid_codes():
        raise HTTPException(404, f"未跟踪的股票代码: {code}")
    rows = db.query_all(
        "SELECT report_date, kind, payload FROM finance WHERE code = ? AND kind = ? ORDER BY report_date DESC",
        [code, kind],
    )
    return {"code": code, "name": _asset_name(code), "kind": kind, "rows": rows}


@router.get("/positions")
def positions():
    """持仓列表（含市价/浮盈，join performance 计算）"""
    rows = db.query_all(
        "SELECT p.code, i.name, p.shares, p.cost, p.updated_at "
        "FROM position p JOIN investable_asset i ON i.code = p.code ORDER BY p.updated_at DESC"
    )
    result = []
    for r in rows:
        ap = performance.asset_performance(r["code"])
        r.update({
            "market_value": ap["position"]["market_value"],
            "unrealized": ap["position"]["unrealized"],
            "unrealized_pct": ap["position"]["unrealized_pct"],
            "latest_close": ap["latest_close"],
        })
        result.append(r)
    return result


@router.get("/transactions")
def transactions(code: str | None = Query(None)):
    """交易记录（可按标的过滤）"""
    if code:
        if code not in _valid_codes():
            raise HTTPException(404, f"未跟踪的股票代码: {code}")
        rows = db.query_all(
            "SELECT t.id, t.code, i.name, t.trade_date, t.direction, t.price, t.shares, t.amount, t.fee, t.note "
            "FROM transaction t JOIN investable_asset i ON i.code = t.code "
            "WHERE t.code = ? ORDER BY t.trade_date, t.id", [code]
        )
    else:
        rows = db.query_all(
            "SELECT t.id, t.code, i.name, t.trade_date, t.direction, t.price, t.shares, t.amount, t.fee, t.note "
            "FROM transaction t JOIN investable_asset i ON i.code = t.code ORDER BY t.trade_date, t.id"
        )
    return rows


@router.get("/performance/summary")
def perf_summary():
    """全账户收益统计汇总（须在 /performance/{code} 之前定义）"""
    return performance.summary()


@router.get("/performance/{code}")
def perf(code: str):
    """单标的收益统计（Performance 概念：实时计算，不建表）"""
    if code not in _valid_codes():
        raise HTTPException(404, f"未跟踪的股票代码: {code}")
    return performance.asset_performance(code)


@router.get("/meta")
def meta():
    """数据库元信息"""
    rows = db.query_all("SELECT key, value FROM meta")
    return {"meta": rows}


def _valid_codes() -> set:
    rows = db.query_all("SELECT code FROM investable_asset")
    return {r["code"] for r in rows}


def _asset_name(code: str) -> str:
    rows = db.query_all("SELECT name FROM investable_asset WHERE code = ?", [code])
    return rows[0]["name"] if rows else code
