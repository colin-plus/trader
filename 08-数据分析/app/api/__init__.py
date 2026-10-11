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
            "SELECT e.id, e.code, a.name, e.eval_date, e.price, e.pe, e.pb, e.dividend_yield, "
            "e.pe_percentile, e.pb_percentile, e.margin_level, e.discount "
            "FROM margin_evaluation e JOIN investable_asset a ON a.code = e.code "
            "WHERE e.code = ? ORDER BY e.eval_date DESC, e.id DESC",
            [code],
        )
    return db.query_all(
        "SELECT e.id, e.code, a.name, e.eval_date, e.price, e.pe, e.pb, e.dividend_yield, "
        "e.pe_percentile, e.pb_percentile, e.margin_level, e.discount "
        "FROM margin_evaluation e JOIN investable_asset a ON a.code = e.code "
        "ORDER BY e.eval_date DESC, e.id DESC"
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
               r.pe_percentile, r.pb_percentile, r.margin_level, r.discount
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


# ==================== 突破确认（breakout_feature 证据层） ====================
# 设计：表里只存证据，阈值在查询时施加（见 docs/schema.md）。
# 唐奇安 N 与量能基准为物化预设，请求值会 snap 到最近档并在 params 中回报实际口径。

_BREAKOUT_N_PRESETS = (20, 60, 120)
_BREAKOUT_VBASE_PRESETS = (20, 50)


def _snap(value: float, presets) -> int:
    return min(presets, key=lambda p: abs(p - value))


def _breakout_latest_complete_date() -> Optional[str]:
    """最后一个"完整"交易日。

    market.duckdb 末尾常有残缺抓取（如仅 6 只股票），直接用 MAX(date) 会得到空结果。
    判据：当日股票数 ≥ 近 60 个交易日股票数中位数的 99%。
    """
    rows = db.query_all(
        """
        WITH d AS (SELECT date, COUNT(*) AS n FROM breakout_feature GROUP BY date),
             m AS (SELECT median(n) AS med FROM (SELECT n FROM d ORDER BY date DESC LIMIT 60))
        SELECT MAX(d.date) AS latest FROM d, m WHERE d.n >= 0.99 * m.med
        """
    )
    latest = rows[0]["latest"] if rows else None
    return latest.isoformat() if latest else None


@router.get("/breakout/meta")
def breakout_meta():
    """证据层元信息（数据覆盖、最新完整交易日、物化口径）"""
    rows = db.query_all(
        "SELECT COUNT(*) AS n, COUNT(DISTINCT code) AS n_codes, MIN(date) AS d0, MAX(date) AS d1 "
        "FROM breakout_feature"
    )
    r = rows[0] if rows else {}
    updated = db.query_all("SELECT value FROM meta WHERE key = 'breakout_feature_updated_at'")
    return {
        "date_min": r.get("d0").isoformat() if r.get("d0") else None,
        "date_max": r.get("d1").isoformat() if r.get("d1") else None,
        "latest_complete_date": _breakout_latest_complete_date(),
        "n_codes": r.get("n_codes", 0),
        "n_rows": r.get("n", 0),
        "updated_at": updated[0]["value"] if updated else None,
        "n_presets": list(_BREAKOUT_N_PRESETS),
        "vbase_presets": list(_BREAKOUT_VBASE_PRESETS),
        "note": "表内只存证据；阈值（k/theta/m/rmin/rmax）查询时施加，调参不需重跑 ETL。",
    }


@router.get("/breakout/scan")
def breakout_scan(
    date: Optional[str] = Query(None),
    n: int = Query(60),
    vbase: int = Query(20),
    m: int = Query(1, ge=0, le=10),
    mode: str = Query("atr", pattern="^(atr|abs|both)$"),
    k: float = Query(1.0),
    theta: float = Query(0.03),
    rmin: float = Query(1.5),
    rmax: float = Query(3.0),
    max_elapsed: int = Query(10, ge=1, le=60),
    run_min: int = Query(1, ge=1, le=60),
    run_max: Optional[int] = Query(None, ge=1, le=60),
    min_pass: int = Query(3, ge=1, le=3),
    limit: int = Query(100, ge=1, le=500),
):
    """全市场扫描：可选"突破距今多久"与"满足几道门槛"。

    **突破距今（run_pos = 自突破日起的交易日数，含突破当日）**：
      run_pos=1 → 今天突破；2 → 昨天突破；3 → 2 天前突破；N+1 → N 天前突破
      `run_min` / `run_max` 给出允许区间；`run_max` 缺省取 `max_elapsed`。
      太久以前的突破已无交易意义，用这个参数即可只看"今天/昨天/N 天前"。

    三道门槛各自独立判定，`pass_count` 是它们的和：
      幅度 ok_amp : 突破日 t0 的穿透幅度达到阈值（mode / k / theta）
      时间 ok_time: 自 t0 起已确认交易日数 run_pos ∈ [m+1, max_elapsed]
      量能 ok_vol : t0 的量能倍数落在 [rmin, rmax]（涨停封板日豁免）

    `min_pass=3` 等价于"三原则全部满足"；`min_pass=2` 用于**对比近似信号**。
    注意：选"今天突破"（run_pos=1）时，时间门槛必然未通过（还没经过确认），
    所以要把 `min_pass` 调到 2 才看得到——这是设计使然，不是 bug。
    """
    N = _snap(n, _BREAKOUT_N_PRESETS)
    VB = _snap(vbase, _BREAKOUT_VBASE_PRESETS)
    rcol = "r_vol" if VB == 20 else "r_vol_50"

    # 距今窗口：不超过 max_elapsed（未过期）
    run_max_eff = min(run_max or max_elapsed, max_elapsed)
    run_min_eff = min(run_min, run_max_eff)

    asof = date or _breakout_latest_complete_date()
    if not asof:
        raise HTTPException(404, "breakout_feature 为空，请先运行 scripts/build_breakout_features.py")

    # 注意：以下表达式在 g 里使用 j 的裸列名（a0 / z0 / r0 / lim0）
    if mode == "atr":
        amp = "(z0 >= ?)"
        amp_params = [k]
    elif mode == "abs":
        amp = "(a0 >= ?)"
        amp_params = [theta]
    else:
        amp = "(z0 >= ? AND a0 >= ?)"
        amp_params = [k, theta]

    sql = f"""
    WITH win AS (
        SELECT * FROM breakout_feature
        WHERE date BETWEEN CAST(? AS DATE) - INTERVAL 150 DAY AND CAST(? AS DATE)
    ),
    cur AS (SELECT * FROM win WHERE date = CAST(? AS DATE)),
    j AS (
        SELECT c.code, c.date, c.close, c.run_pos_{N} AS run_pos,
               c.run_start_date_{N} AS run_start_date, c.res_level_{N} AS res_level,
               c.box_range_atr, c.atr_pct,
               s.d_abs_{N} AS d0, s.run_level_{N} AS l0, s.atr AS atr0,
               s.{rcol} AS r0, s.limit_up AS lim0,
               s.ret5, s.ret10, s.ret20,
               s.d_abs_{N} / NULLIF(s.run_level_{N}, 0) AS a0,
               s.d_abs_{N} / NULLIF(s.atr, 0) AS z0
        FROM cur c
        JOIN win s ON s.code = c.code AND s.date = c.run_start_date_{N}
        WHERE c.run_pos_{N} > 0 AND s.run_level_{N} > 0 AND s.atr > 0
    ),
    g AS (
        SELECT j.*,
               CASE WHEN run_pos BETWEEN ? AND ? THEN 1 ELSE 0 END AS ok_time,
               CASE WHEN {amp} THEN 1 ELSE 0 END AS ok_amp,
               CASE WHEN (r0 >= ? AND r0 <= ?) OR COALESCE(lim0, FALSE) THEN 1 ELSE 0 END AS ok_vol
        FROM j
        WHERE run_pos BETWEEN ? AND ?
    ),
    s2 AS (SELECT g.*, (g.ok_time + g.ok_amp + g.ok_vol) AS pass_count FROM g)
    SELECT s2.*, COUNT(*) OVER () AS total, a.name
    FROM s2 LEFT JOIN investable_asset a ON a.code = s2.code
    WHERE s2.pass_count >= ?
    ORDER BY s2.pass_count DESC, s2.z0 DESC NULLS LAST
    LIMIT ?
    """
    params = ([asof, asof, asof, m + 1, max_elapsed] + amp_params
              + [rmin, rmax, run_min_eff, run_max_eff, min_pass, limit])
    rows = db.query_all(sql, params)
    total = rows[0].pop("total") if rows else 0

    out = []
    for r in rows:
        a0, z0, r0 = r.get("a0"), r.get("z0"), r.get("r0")
        pass_amp = bool(r.get("ok_amp"))
        pass_time = bool(r.get("ok_time"))
        pass_vol = bool(r.get("ok_vol"))  # 涨停封板日成交极小，SQL 中已豁免
        pass_count = int(r.get("pass_count") or 0)
        out.append({
            "code": r["code"], "name": r.get("name") or r["code"], "date": r["date"].isoformat(),
            "close": r["close"], "run_start_date": r["run_start_date"].isoformat() if r["run_start_date"] else None,
            "run_pos": r["run_pos"], "run_level": r["l0"], "a_pct": a0, "z_atr": z0,
            "days_ago": (r["run_pos"] - 1) if r.get("run_pos") is not None else None,
            "atr_pct": r.get("atr_pct"), "r_vol": r0, "res_level": r.get("res_level"),
            "box_range_atr": r.get("box_range_atr"), "is_limit_up": bool(r.get("lim0")),
            "pass_amp": pass_amp, "pass_time": pass_time, "pass_vol": pass_vol,
            "pass_count": pass_count, "passed": pass_count == 3,
            "ret5": r.get("ret5"), "ret10": r.get("ret10"), "ret20": r.get("ret20"),
        })
    return {
        "date": asof,
        "params": {"n": N, "vbase": VB, "m": m, "mode": mode, "k": k, "theta": theta,
                   "rmin": rmin, "rmax": rmax, "max_elapsed": max_elapsed, "min_pass": min_pass,
                   "run_min": run_min_eff, "run_max": run_max_eff},
        "count": total,
        "rows": out,
    }


@router.get("/breakout/{code}")
def breakout_detail(
    code: str,
    days: int = Query(120, ge=20, le=1000),
    n: int = Query(60),
    vbase: int = Query(20),
    m: int = Query(1, ge=0, le=10),
):
    """单标的突破证据序列（供 K 线叠加：关键位 / ATR / 量能倍数 / 状态）"""
    if code not in _valid_codes():
        raise HTTPException(404, f"未跟踪的股票代码: {code}")
    N = _snap(n, _BREAKOUT_N_PRESETS)
    VB = _snap(vbase, _BREAKOUT_VBASE_PRESETS)
    rcol = "r_vol" if VB == 20 else "r_vol_50"

    rows = db.query_all(
        f"""
        SELECT date, open, high, low, close, volume, amount,
               atr, atr_pct, res_level_{N} AS res_level,
               run_pos_{N} AS run_pos, run_level_{N} AS run_level,
               run_start_date_{N} AS run_start_date,
               d_abs_{N} AS d_abs, {rcol} AS r_vol, amt_base, limit_up,
               CASE WHEN run_level_{N} > 0 THEN d_abs_{N} / run_level_{N} END AS a_pct,
               CASE WHEN atr > 0 THEN d_abs_{N} / atr END AS z_atr
        FROM breakout_feature WHERE code = ? ORDER BY date DESC LIMIT ?
        """,
        [code, days + 1],
    )
    rows.reverse()
    # 多取 1 行是为了让第一行的状态能参考前一日；状态算完后再裁掉
    prev_pos = None
    for r in rows:
        pos = r.get("run_pos") or 0
        if pos == 1:
            state = "突破日"
        elif pos > 1 and pos < m + 1:
            state = "确认中"
        elif pos >= m + 1:
            state = "已确认"
        elif pos == 0 and (prev_pos or 0) > 0:
            state = "失效"
        else:
            state = "无"
        r["state"] = state
        r["is_breakout_day"] = pos == 1
        r["amt"] = r.pop("amount", None)
        r["limit_up"] = bool(r.get("limit_up"))
        r["date"] = r["date"].isoformat()
        if r.get("run_start_date"):
            r["run_start_date"] = r["run_start_date"].isoformat()
        prev_pos = pos
    if len(rows) > days:
        rows = rows[-days:]
    return {"code": code, "name": _asset_name(code),
            "params": {"n": N, "vbase": VB, "m": m, "days": days}, "rows": rows}


def _valid_codes() -> set:
    rows = db.query_all("SELECT code FROM investable_asset")
    return {r["code"] for r in rows}


def _asset_name(code: str) -> str:
    rows = db.query_all("SELECT name FROM investable_asset WHERE code = ?", [code])
    return rows[0]["name"] if rows else code
