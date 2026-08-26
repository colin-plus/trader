"""API 路由：行情 / 分价 / 资金流 / 财务 / 标的 / 我的 / 安全边际。"""
import json
import pathlib
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app import db, performance

router = APIRouter(prefix="/api")


@router.get("/stocks/search")
def search_stocks(q: str = Query(..., min_length=1, max_length=20)):
    """股票搜索（代码/名称模糊匹配，返回前 20 条）——供前端输入自动补全"""
    like = f"%{q}%"
    rows = db.query_all(
        "SELECT code, name, type FROM investable_asset "
        "WHERE code LIKE ? OR name LIKE ? "
        "ORDER BY (code LIKE ?) DESC, code LIMIT 20",
        [like, like, f"{q}%"],
    )
    return rows


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


@router.get("/margin/macro")
def margin_macro():
    """宏观基准（10 年期国债收益率）"""
    return db.query_all("SELECT date, cn10y FROM margin_macro ORDER BY date DESC LIMIT 30")


@router.get("/margin/factors/{code}")
def margin_factors(code: str):
    """估值因子历史（按报告期）"""
    if code not in _valid_codes():
        raise HTTPException(404, f"未跟踪的股票代码: {code}")
    return db.query_all(
        "SELECT report_date, eps, bps, dps, total_shares, float_shares "
        "FROM margin_factor WHERE code = ? ORDER BY report_date DESC",
        [code],
    )


@router.get("/margin/daily/{code}")
def margin_daily(code: str, days: int = Query(60, ge=5, le=1000)):
    """估值日快照（PE/PB/股息率序列）"""
    if code not in _valid_codes():
        raise HTTPException(404, f"未跟踪的股票代码: {code}")
    return db.query_all(
        "SELECT date, pe, pb, dividend_yield FROM margin_daily "
        "WHERE code = ? ORDER BY date DESC LIMIT ?",
        [code, days],
    )


@router.get("/margin/evaluations")
def margin_evaluations(code: Optional[str] = None):
    """安全边际评估记录（可按标的过滤）"""
    if code:
        return db.query_all(
            "SELECT id, code, eval_date, price, pe, pb, dividend_yield, pe_percentile, "
            "pb_percentile, margin_level, discount, decision, note "
            "FROM margin_evaluation WHERE code = ? ORDER BY eval_date DESC, id DESC",
            [code],
        )
    return db.query_all(
        "SELECT id, code, eval_date, price, pe, pb, dividend_yield, pe_percentile, "
        "pb_percentile, margin_level, discount, decision, note "
        "FROM margin_evaluation ORDER BY eval_date DESC, id DESC"
    )


@router.get("/margin/status/{code}")
def margin_status(code: str):
    """单标的安全边际状态（最新估值 + 5年分位 + 评估历史计数）"""
    if code not in _valid_codes():
        raise HTTPException(404, f"未跟踪的股票代码: {code}")
    name = _asset_name(code)
    latest = db.query_all(
        "SELECT date, pe, pb, dividend_yield FROM margin_daily "
        "WHERE code = ? ORDER BY date DESC LIMIT 1",
        [code],
    )
    factor = db.query_all(
        "SELECT report_date, eps, bps, dps FROM margin_factor "
        "WHERE code = ? ORDER BY report_date DESC LIMIT 1",
        [code],
    )
    # 最新收盘价（价格在 daily_kline，margin_daily 只有估值）
    price_row = db.query_all(
        "SELECT close FROM daily_kline WHERE code = ? ORDER BY date DESC LIMIT 1",
        [code],
    )
    # 近 5 年 PE/PB 分位（当前值在历史序列中的百分位）
    pe_pct = pb_pct = None
    if latest:
        pe = latest[0]["pe"]
        pb = latest[0]["pb"]
        if pe is not None:
            pe_hist = db.query_all(
                "SELECT pe FROM margin_daily WHERE code = ? AND pe IS NOT NULL "
                "AND date >= current_date - INTERVAL '5 years' ORDER BY pe",
                [code],
            )
            if pe_hist:
                below = sum(1 for h in pe_hist if h["pe"] <= pe)
                pe_pct = round(below / len(pe_hist) * 100, 1)
        if pb is not None:
            pb_hist = db.query_all(
                "SELECT pb FROM margin_daily WHERE code = ? AND pb IS NOT NULL "
                "AND date >= current_date - INTERVAL '5 years' ORDER BY pb",
                [code],
            )
            if pb_hist:
                below = sum(1 for h in pb_hist if h["pb"] <= pb)
                pb_pct = round(below / len(pb_hist) * 100, 1)
    evals = db.query_all(
        "SELECT COUNT(*) AS n FROM margin_evaluation WHERE code = ?", [code]
    )
    return {
        "code": code,
        "name": name,
        "latest": latest[0] if latest else None,
        "factor": factor[0] if factor else None,
        "price": price_row[0]["close"] if price_row else None,
        "percentile_5y": {"pe": pe_pct, "pb": pb_pct},
        "evaluation_count": evals[0]["n"] if evals else 0,
    }


@router.get("/margin/dashboard")
def margin_dashboard():
    """评估看板：每标的最近一次评估记录（含名称）"""
    return db.query_all(
        """
        WITH ranked AS (
            SELECT e.*, ROW_NUMBER() OVER (PARTITION BY code ORDER BY eval_date DESC, id DESC) AS rn
            FROM margin_evaluation e
        )
        SELECT r.code, a.name, r.eval_date, r.price, r.pe, r.pb, r.dividend_yield,
               r.pe_percentile, r.pb_percentile, r.margin_level, r.decision, r.note
        FROM ranked r
        JOIN investable_asset a ON a.code = r.code
        WHERE r.rn = 1
        ORDER BY a.name
        """
    )


@router.post("/margin/evaluations")
def create_evaluation(body: dict):
    """按需评估：委托独立进程自动计算结论并落库（只收 code，失败返回原因）"""
    import subprocess
    import sys as _sys

    code = str(body.get("code", "")).strip()
    if not code:
        raise HTTPException(400, "code 必填")
    script = pathlib.Path(__file__).parent.parent.parent / "scripts" / "write_evaluation.py"
    r = subprocess.run(
        [_sys.executable, str(script)],
        input=json.dumps({"code": code}),
        capture_output=True,
        text=True,
        timeout=15,
    )
    if r.returncode != 0:
        raise HTTPException(400, r.stderr.strip() or "评估失败")
    return json.loads(r.stdout)


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
