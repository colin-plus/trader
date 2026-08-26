"""Performance（收益统计）——领域概念计算层。

不建表：由 position（持仓快照）+ transaction（交易事实）+ daily_kline（市价）实时计算。
口径约定：最终对账以券商 APP 数字为准，本层为辅助分析（胜率/盈亏分布/持仓市值）。
"""
from typing import Optional

from app import db


def _latest_close(code: str) -> Optional[float]:
    """最新收盘价"""
    rows = db.query_all(
        "SELECT close FROM daily_kline WHERE code = ? ORDER BY date DESC LIMIT 1", [code]
    )
    return rows[0]["close"] if rows else None


def asset_performance(code: str) -> dict:
    """单标的收益统计"""
    pos = db.query_all("SELECT shares, cost, updated_at FROM position WHERE code = ?", [code])
    info = db.query_all("SELECT name, type FROM investable_asset WHERE code = ?", [code])
    name = info[0]["name"] if info else code
    typ = info[0]["type"] if info else "stock"

    shares = pos[0]["shares"] if pos else 0
    cost = pos[0]["cost"] if pos else None
    latest = _latest_close(code)

    market_value = round(shares * latest, 2) if shares and latest else None
    # 持仓浮盈（以持仓表成本为准）
    unrealized = round((latest - cost) * shares, 2) if shares and latest and cost else None
    unrealized_pct = round((latest - cost) / cost * 100, 2) if shares and latest and cost else None

    # 已实现盈亏：Σ卖出净收 − Σ卖出股数 × 持仓成本（券商口径 position.cost）
    sells = db.query_all(
        "SELECT amount, fee, shares FROM transaction WHERE code = ? AND direction = 'sell'", [code]
    )
    realized = None
    if sells and cost:
        sell_net = sum(r["amount"] - r["fee"] for r in sells)
        sell_shares = sum(r["shares"] for r in sells)
        realized = round(sell_net - sell_shares * cost, 2)

    txn_rows = db.query_all(
        "SELECT COUNT(*) AS n, "
        "SUM(CASE WHEN direction='buy' THEN 1 ELSE 0 END) AS buys, "
        "SUM(CASE WHEN direction='sell' THEN 1 ELSE 0 END) AS sells "
        "FROM transaction WHERE code = ?", [code],
    )
    txn = txn_rows[0] if txn_rows else {"n": 0, "buys": 0, "sells": 0}

    return {
        "code": code,
        "name": name,
        "type": typ,
        "position": {
            "shares": shares,
            "cost": cost,
            "market_value": market_value,
            "unrealized": unrealized,
            "unrealized_pct": unrealized_pct,
        },
        "realized": realized,
        "transactions": {"total": txn["n"], "buys": txn["buys"], "sells": txn["sells"]},
        "latest_close": latest,
    }


def summary() -> dict:
    """全账户收益统计汇总"""
    positions = db.query_all("SELECT code, shares, cost FROM position")
    total_market_value = 0.0
    total_cost = 0.0
    total_realized = 0.0
    per_asset = []
    for p in positions:
        ap = asset_performance(p["code"])
        mv = ap["position"]["market_value"] or 0
        total_market_value += mv
        total_cost += p["cost"] * p["shares"]
        total_realized += ap["realized"] or 0
        per_asset.append(ap)
    total_unrealized = round(total_market_value - total_cost, 2)
    return {
        "assets_count": len(per_asset),
        "total_market_value": round(total_market_value, 2),
        "total_cost": round(total_cost, 2),
        "total_unrealized": total_unrealized,
        "total_unrealized_pct": round(total_unrealized / total_cost * 100, 2) if total_cost else None,
        "total_realized": round(total_realized, 2),
        "assets": per_asset,
    }
