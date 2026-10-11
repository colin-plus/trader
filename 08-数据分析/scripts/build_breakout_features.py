#!/usr/bin/env python3
"""构建「突破确认证据层」breakout_feature（全市场）。

口径权威文档见 docs/schema.md「表：breakout_feature」，改公式必须同步改文档。

设计要点：
- 只存**证据向量**，不存结论。阈值（3% / ATR倍数 / 确认天数 / 量能区间）由 API 查询时施加，
  调参不需要重跑本脚本。
- 唐奇安窗口 N ∈ {20,60,120} 三档同时物化，扫描页切换 N 无需重跑。
- 源数据 market.duckdb.stock_daily 是**未复权原始价**，本脚本用 stock_dividend 自建前复权因子。
- 禁止未来函数：res_level / amt_base 一律取 t−N ... t−1（不含当日）。

用法：
    .venv/bin/python scripts/build_breakout_features.py                 # 默认落最近 300 个交易日
    .venv/bin/python scripts/build_breakout_features.py --days 600
    .venv/bin/python scripts/build_breakout_features.py --dry-run       # 只算不写库
"""
import argparse
import pathlib
import sys
import time

import duckdb
import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).parent
DB_PATH = HERE.parent / "data" / "trader.duckdb"
MARKET_DB = pathlib.Path.home() / "Github" / "market" / "data" / "market.duckdb"

N_PRESETS = (20, 60, 120)
ATR_N = 14
VBASE = 20
VBASE_ALT = 50
# 落库列顺序（与 apply_schema.py SCHEMA['breakout_feature'] 的 columns 顺序一致）
OUT_COLS = [
    "code", "date", "open", "high", "low", "close", "amount", "volume",
    "atr", "atr_pct",
    "res_level_20", "res_level_60", "res_level_120", "box_range_atr",
    "run_pos_20", "run_level_20", "run_start_date_20", "d_abs_20",
    "run_pos_60", "run_level_60", "run_start_date_60", "d_abs_60",
    "run_pos_120", "run_level_120", "run_start_date_120", "d_abs_120",
    "amt_base", "r_vol", "amt_base_50", "r_vol_50",
    "pct_chg", "limit_up", "ret5", "ret10", "ret20",
]


def wilder_atr(tr: pd.Series, n: int) -> pd.Series:
    """Wilder 原始 ATR：种子 = 前 n 个 TR 的算术平均，之后 ATR_t = ((n-1)ATR_{t-1} + TR_t)/n。

    实现技巧：把第 n 个位置替换为种子值，再对 [种子, TR_n, TR_{n+1}, ...] 做
    adjust=False 的 EMA(α=1/n)，最后位移回原索引——数学上与原递推完全等价，且是向量化的。
    """
    arr = tr.to_numpy(dtype="float64")
    m = len(arr)
    if m < n:
        return pd.Series(np.full(m, np.nan), index=tr.index)
    seed = np.nanmean(arr[:n])
    tail = arr[n:]
    seq = np.concatenate([[seed], tail])
    out = pd.Series(seq).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    full = np.full(m, np.nan)
    full[n - 1:] = out
    full[:n - 1] = np.nan
    return pd.Series(full, index=tr.index)


def run_state_machine(close: np.ndarray, res: np.ndarray):
    """突破 run 状态机（逐日，向量化受限故用循环）。

    规则（见 docs/schema.md）：
      run 起点 t0 : C_t0 > res_t0 且 t0-1 不在 run 中
      run_level   : res_level_{t0}（**突破日冻结**；用当日 res 会因上轨上漂而永远判不出"站稳"）
      run 延续    : C_t > run_level（允许回踩，只要守住被突破的位）
      run 终止    : C_t <= run_level

    返回 (run_pos, run_level, run_start_idx)；不在 run 中时 run_pos=0、其余为 nan/-1。
    """
    n = len(close)
    pos = np.zeros(n, dtype="int32")
    lvl = np.full(n, np.nan)
    sidx = np.full(n, -1, dtype="int64")
    in_run = False
    rl = np.nan
    cnt = 0
    si = -1
    for i in range(n):
        c = close[i]
        r = res[i]
        if in_run:
            if c > rl:
                cnt += 1
                pos[i] = cnt
                lvl[i] = rl
                sidx[i] = si
                continue
            in_run = False
            cnt = 0
            si = -1
        # 不在 run 中（或刚终止）：判断能否开启新一轮
        if np.isfinite(r) and np.isfinite(c) and c > r:
            in_run = True
            rl = r
            cnt = 1
            si = i
            pos[i] = 1
            lvl[i] = rl
            sidx[i] = si
    return pos, lvl, sidx


def next_trading_days(dates: np.ndarray, k: int, start: np.datetime64) -> np.ndarray:
    """返回每个 date 之后第 k 个交易日（用于事后收益，严格按交易日而非自然日）。"""
    # dates 为某只股票升序的交易日数组
    n = len(dates)
    idx = np.arange(n) + k
    out = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
    ok = idx < n
    out[ok] = dates[idx[ok]]
    return out


def build_adj_factors(bars: pd.DataFrame, div: pd.DataFrame) -> np.ndarray:
    """自建前复权累计因子：F_t = Π_{ex_date > t} f_e，f_e = (1 − D/P_prev)/(1 + R)。"""
    factor = np.ones(len(bars), dtype="float64")
    if div.empty:
        return factor

    div = div.dropna(subset=["ex_date"]).copy()
    div["D"] = (div["dividend_per_10"].fillna(0.0)) / 10.0
    div["R"] = (div["bonus_ratio"].fillna(0.0) + div["transfer_ratio"].fillna(0.0)) / 10.0
    div = div.groupby(["code", "ex_date"], as_index=False).agg(D=("D", "sum"), R=("R", "sum"))

    # 除权日前最后一个交易日的收盘价（P_prev）——用 merge_asof backward，严格早于 ex_date
    bars_sorted = bars.sort_values(["date"])
    left = div.sort_values(["ex_date"]).copy()
    merged = pd.merge_asof(
        left,
        bars_sorted[["code", "date", "close"]].rename(columns={"date": "prev_date", "close": "prev_close"}),
        left_on="ex_date",
        right_on="prev_date",
        by="code",
        direction="backward",
        allow_exact_matches=False,
    )
    merged = merged.dropna(subset=["prev_close"])
    merged = merged[merged["prev_close"] > 0]
    if merged.empty:
        return factor
    merged["f"] = (1.0 - merged["D"] / merged["prev_close"]) / (1.0 + merged["R"])
    # 合理性护栏：因子必须落在 (0, 1]（除权只会向下调整历史价）
    bad = (merged["f"] <= 0.05) | (merged["f"] > 1.0001)
    if bad.any():
        print(f"  ! 剔除 {int(bad.sum())} 条异常复权因子（越界）", file=sys.stderr)
        merged = merged[~bad]

    # 按 code 分组：ex 升序 → 后缀乘积 → 对每根 bar 用 searchsorted 找第一个 ex_date > date
    codes = bars["code"].to_numpy()
    dates = bars["date"].to_numpy()
    order = np.argsort(dates, kind="stable")
    for code, grp in merged.groupby("code", sort=False):
        ex = np.sort(grp["ex_date"].to_numpy())
        f = grp.sort_values("ex_date")["f"].to_numpy(dtype="float64")
        suffix = np.cumprod(f[::-1])[::-1]  # suffix[i] = Π_{j>=i} f_j
        mask = codes == code
        idx = np.searchsorted(ex, dates[mask], side="right")
        vals = np.where(idx < len(ex), suffix[np.minimum(idx, len(ex) - 1)], 1.0)
        factor[mask] = vals
    return factor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=300, help="落库的最近交易日数")
    ap.add_argument("--warmup", type=int, default=220, help="额外多加载的预热交易日数")
    ap.add_argument("--dry-run", action="store_true", help="只计算不写库")
    args = ap.parse_args()

    t0 = time.time()
    if not MARKET_DB.exists():
        print(f"源库不存在: {MARKET_DB}", file=sys.stderr)
        sys.exit(1)

    mkt = duckdb.connect(str(MARKET_DB), read_only=True)
    trd = duckdb.connect(str(DB_PATH), read_only=True)
    valid_codes = {r[0] for r in trd.execute("SELECT code FROM investable_asset").fetchall()}
    trd.close()

    max_date = mkt.execute("SELECT MAX(date) FROM stock_daily").fetchone()[0]
    # 用真实交易日历回溯，而不是自然日减法
    cal = mkt.execute(
        "SELECT DISTINCT date FROM stock_daily WHERE date <= ? ORDER BY date DESC LIMIT ?",
        [max_date, args.days + args.warmup],
    ).fetchdf()
    since = cal["date"].min()
    print(f"源库最新交易日 {max_date}；加载自 {since}（{len(cal)} 个交易日，含 {args.warmup} 日预热）")

    bars = mkt.execute(
        """
        SELECT code, date, open, high, low, close, volume, amount
        FROM stock_daily WHERE date >= ? ORDER BY code, date
        """,
        [since],
    ).fetchdf()
    div = mkt.execute(
        """
        SELECT code, ex_date, dividend_per_10, bonus_ratio, transfer_ratio
        FROM stock_dividend
        WHERE progress = '实施分配' AND ex_date IS NOT NULL AND ex_date >= ? AND ex_date <= ?
        """,
        [since, max_date],
    ).fetchdf()
    mkt.close()

    bars = bars[bars["code"].isin(valid_codes)].copy()
    bars["date"] = pd.to_datetime(bars["date"])
    for c in ("open", "high", "low", "close", "amount"):
        bars[c] = bars[c].astype("float64")
    bars["volume"] = bars["volume"].astype("float64")
    print(f"行情 {len(bars):,} 行 / {bars['code'].nunique()} 只；分红 {len(div):,} 条")

    # ---------- 1. 自建前复权 ----------
    bars = bars.sort_values(["code", "date"]).reset_index(drop=True)
    factor = build_adj_factors(bars, div)
    bars["adj_factor"] = factor
    for c in ("open", "high", "low", "close"):
        bars[c] = bars[c] * bars["adj_factor"]
    n_adj = int((np.abs(bars["adj_factor"] - 1.0) > 1e-9).sum())
    print(f"复权：{n_adj:,} 行被调整（{n_adj / max(len(bars), 1):.1%}）")

    # ---------- 2. 逐股特征 ----------
    g = bars.groupby("code", sort=False)

    # 2.1 Wilder ATR
    prev_close = g["close"].shift(1)
    tr = np.maximum(
        bars["high"] - bars["low"],
        np.maximum((bars["high"] - prev_close).abs(), (bars["low"] - prev_close).abs()),
    )
    bars["tr"] = tr
    bars["atr"] = bars.groupby("code", sort=False)["tr"].transform(lambda s: wilder_atr(s, ATR_N))
    bars["atr_pct"] = bars["atr"] / bars["close"]

    # 2.2 唐奇安上轨（不含当日）+ 箱体紧致度
    for N in N_PRESETS:
        bars[f"res_level_{N}"] = bars.groupby("code", sort=False)["high"].transform(
            lambda s, N=N: s.rolling(N).max().shift(1)
        )
    hi60 = bars.groupby("code", sort=False)["high"].transform(lambda s: s.rolling(60).max().shift(1))
    lo60 = bars.groupby("code", sort=False)["low"].transform(lambda s: s.rolling(60).min().shift(1))
    bars["box_range_atr"] = (hi60 - lo60) / bars["atr"]

    # 2.3 量能基准（不含当日）
    bars["amt_base"] = bars.groupby("code", sort=False)["amount"].transform(
        lambda s: s.rolling(VBASE).mean().shift(1)
    )
    bars["r_vol"] = bars["amount"] / bars["amt_base"]
    bars["amt_base_50"] = bars.groupby("code", sort=False)["amount"].transform(
        lambda s: s.rolling(VBASE_ALT).mean().shift(1)
    )
    bars["r_vol_50"] = bars["amount"] / bars["amt_base_50"]

    # 2.4 涨跌幅 + 涨停
    bars["pct_chg"] = bars["close"] / prev_close - 1.0
    bars["limit_pct"] = np.where(bars["code"].str.startswith("30"), 20.0, 10.0)
    # ST 的 5% 板用全样本 99.5 分位推断（已知近似，见文档）
    q995 = bars.groupby("code", sort=False)["pct_chg"].transform(
        lambda s: s.abs().quantile(0.995)
    )
    bars.loc[(q995 >= 0.045) & (q995 <= 0.055), "limit_pct"] = 5.0
    bars["limit_up"] = bars["pct_chg"] >= (bars["limit_pct"] / 100.0 - 0.003)

    # 2.5 突破 run 状态机（三档 N）
    for N in N_PRESETS:
        res = bars[f"res_level_{N}"].to_numpy(dtype="float64")
        close = bars["close"].to_numpy(dtype="float64")
        pos = np.zeros(len(bars), dtype="int32")
        lvl = np.full(len(bars), np.nan)
        sdate = np.full(len(bars), np.datetime64("NaT", "ns"))
        dates_all = bars["date"].to_numpy()
        for _, idx in bars.groupby("code", sort=False).indices.items():
            p, l, si = run_state_machine(close[idx], res[idx])
            pos[idx] = p
            lvl[idx] = l
            # si 是**组内**位置，需经 idx 映射回全表位置
            ok = si >= 0
            if ok.any():
                sdate[idx[ok]] = dates_all[idx[si[ok]]]
        bars[f"run_pos_{N}"] = pos
        bars[f"run_level_{N}"] = lvl
        bars[f"run_start_date_{N}"] = sdate
        bars[f"d_abs_{N}"] = bars["close"] - lvl

    # 2.6 事后收益（校准用；严格按交易日）
    for k in (5, 10, 20):
        fwd = bars.groupby("code", sort=False)["close"].shift(-k)
        bars[f"ret{k}"] = fwd / bars["close"] - 1.0

    # ---------- 3. 落库 ----------
    bars["date"] = bars["date"].dt.date
    store_since = cal["date"].sort_values(ascending=False).iloc[min(args.days, len(cal)) - 1]
    out = bars[bars["date"] >= store_since.date() if hasattr(store_since, "date") else bars["date"] >= store_since]
    out = out[OUT_COLS].copy()
    out["volume"] = out["volume"].round().astype("int64")

    print(f"落库窗口自 {store_since}，共 {len(out):,} 行 / {out['code'].nunique()} 只")
    print("信号密度抽样（N=60, run_pos>=1）：")
    sig = out[out["run_pos_60"] >= 1]
    print(f"  处于突破 run 中的 (股票,日) 占比 {len(sig) / max(len(out), 1):.2%}")

    if args.dry_run:
        print("dry-run：未写库")
        return

    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute("DELETE FROM breakout_feature")
        con.register("df_out", out)
        cols = ", ".join(OUT_COLS)
        con.execute(f"INSERT INTO breakout_feature ({cols}, updated_at) SELECT {cols}, now() FROM df_out")
        n = con.execute("SELECT COUNT(*) FROM breakout_feature").fetchone()[0]
        con.execute(
            "INSERT OR REPLACE INTO meta VALUES ('breakout_feature_updated_at', ?)",
            [pd.Timestamp.now(tz="Asia/Shanghai").isoformat()],
        )
    finally:
        con.close()
    print(f"✓ breakout_feature 已写入 {n:,} 行，耗时 {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
