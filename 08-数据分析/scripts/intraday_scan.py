#!/usr/bin/env python3
"""盘中突破扫描（实时快照版）——不写库，纯"预演"视图。

为什么单独做而不是复用 build_breakout_features.py：
- 日线管道（新浪）在盘中**拿不到当天数据**（只返回已收盘交易日）
- 如果把未收盘的 K 线写进 daily_kline / breakout_feature，会污染已确认的历史，
  且量能（才走了几十分钟）必然失真
- 本脚本用腾讯实时快照在内存里拼出"今日未收盘 K 线"，与库内已确认的历史（breakout_feature）
  做增量推演，只输出结果、不改任何表

口径与注意事项（必须与 build_breakout_features.py 一致，否则不可比）：
- 价格：库内为前复权，最新日锚定原始价；今日无除权时 现价 ≈ 前复权价（有除权需重算）
- 成交量/成交额：**实时值按已开市时间线性折算成全日预估**（估算，非事实），
  用于让量能门槛可比；折算系数 = 240 / 已开市分钟
- ATR：用 10-09 的 ATR 与今日真实波幅做一次 Wilder 递推
- run 状态：从库内最后一日的 run_pos_60 / run_level_60 增量推演

用法：
    .venv/bin/python scripts/intraday_scan.py                      # 默认同网页参数
    .venv/bin/python scripts/intraday_scan.py --k 0.5 --min-pass 2
    .venv/bin/python scripts/intraday_scan.py --codes 301513,600027 # 只看指定标的
"""
import argparse
import datetime as dt
import os
import re
import sys
import time
from pathlib import Path

# ---- 绕过失效的 macOS 系统代理 ----
import requests.utils
import requests.sessions

requests.utils.get_environ_proxies = lambda url, no_proxy=None: {}
requests.sessions.get_environ_proxies = lambda url, no_proxy=None: {}
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import duckdb  # noqa: E402
import requests  # noqa: E402

MARKET = Path.home() / "Github" / "market" / "data" / "market.duckdb"
TRADER = ROOT / "data" / "trader.duckdb"
BATCH = 60            # 腾讯单次请求代码数
QT_URL = "https://qt.gtimg.cn/q="


def symbol_of(code):
    return ("sh" if code.startswith("6") else "sz") + code


def trading_minutes(now: dt.datetime) -> int:
    """已开市分钟数（含午休扣减）。9:30-11:30 + 13:00-15:00 共 240 分钟。"""
    t = now.time()
    if t < dt.time(9, 30):
        return 0
    if t <= dt.time(11, 30):
        return (now.hour * 60 + now.minute) - (9 * 60 + 30)
    if t < dt.time(13, 0):
        return 120
    if t <= dt.time(15, 0):
        return 120 + (now.hour * 60 + now.minute) - (13 * 60)
    return 240


def fetch_snapshot(codes):
    """腾讯批量实时快照 → {code: dict}"""
    out = {}
    sess = requests.Session()
    sess.trust_env = False
    for i in range(0, len(codes), BATCH):
        chunk = codes[i:i + BATCH]
        url = QT_URL + ",".join(symbol_of(c) for c in chunk)
        for attempt in range(3):
            try:
                r = sess.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                r.encoding = "gbk"
                break
            except Exception:
                time.sleep(1.0 + attempt)
        else:
            continue
        for line in r.text.strip().split(";"):
            line = line.strip()
            if not line or "=" not in line:
                continue
            head, _, body = line.partition("=")
            code = re.sub(r"\D", "", head)
            f = body.strip().strip('"').split("~")
            if len(f) < 46 or not f[3]:
                continue
            try:
                out[code] = {
                    "name": f[1], "price": float(f[3]), "prev_close": float(f[4]),
                    "open": float(f[5] or 0), "high": float(f[33] or 0), "low": float(f[34] or 0),
                    "vol_hand": float(f[36] or 0), "amount_wan": float(f[37] or 0),
                    "turnover": float(f[38] or 0), "ts": f[30],
                }
            except (ValueError, IndexError):
                continue
        time.sleep(0.12)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default=None, help="逗号分隔，只看这些标的")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--m", type=int, default=1)
    ap.add_argument("--k", type=float, default=1.0)
    ap.add_argument("--rmin", type=float, default=1.5)
    ap.add_argument("--rmax", type=float, default=3.0)
    ap.add_argument("--max-elapsed", type=int, default=10)
    ap.add_argument("--min-pass", type=int, default=3)
    ap.add_argument("--run-max", type=int, default=3, help="突破距今上限（run_pos）")
    args = ap.parse_args()

    now = dt.datetime.now()
    mins = trading_minutes(now)
    scale = max(1.0, 240.0 / mins) if 0 < mins < 240 else 1.0
    print(f"盘中扫描 {now:%Y-%m-%d %H:%M:%S}｜已开市 {mins} 分钟｜量能折算系数 ×{scale:.2f}"
          f"（全日预估，非事实）\n")

    m = duckdb.connect(str(MARKET), read_only=True)
    t = duckdb.connect(str(TRADER), read_only=True)

    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    else:
        codes = [r[0] for r in m.execute(
            "SELECT code FROM stock WHERE is_active AND regexp_matches(code, '^(60|00|30)\\d{4}$') ORDER BY code"
        ).fetchall()]
    print(f"取快照：{len(codes)} 只 ...")
    snap = fetch_snapshot(codes)
    print(f"  拿到 {len(snap)} 只\n")

    # 库内已确认历史的最后一日 + 近 N 日高点（算今日唐奇安上轨）
    last_date = t.execute("SELECT MAX(date) FROM breakout_feature").fetchone()[0]
    hist = t.execute(
        f"""
        WITH h AS (
            SELECT code, date, close, high, atr, amt_base, run_pos_{args.n} AS run_pos,
                   run_level_{args.n} AS run_level,
                   MAX(high) OVER (PARTITION BY code ORDER BY date ROWS BETWEEN {args.n} PRECEDING AND CURRENT ROW) AS hi_win
            FROM breakout_feature
            WHERE date >= CAST(? AS DATE) - INTERVAL 200 DAY
        )
        SELECT code, date, close, high, atr, amt_base, run_pos, run_level, hi_win
        FROM h WHERE date = ?
        """, [last_date, last_date],
    ).fetchdf()
    prev = {r["code"]: r for _, r in hist.iterrows()}
    m.close(); t.close()

    rows = []
    for code, s in snap.items():
        p = prev.get(code)
        if p is None or not p["amt_base"]:
            continue
        # 今日唐奇安上轨 = 截至上一交易日的 N 日最高（窗口含最后一日自身）
        res_today = float(p["hi_win"])
        close = s["price"]
        prev_close = s["prev_close"]
        # ATR：用上一日 ATR 与今日真实波幅做一次 Wilder 递推
        atr_prev = float(p["atr"]) if p["atr"] else None
        if atr_prev:
            tr = max(s["high"] - s["low"], abs(s["high"] - prev_close), abs(s["low"] - prev_close))
            atr = (13 * atr_prev + tr) / 14
        else:
            atr = None
        # run 状态增量推演
        run_pos = int(p["run_pos"]) if p["run_pos"] else 0
        run_level = float(p["run_level"]) if p["run_level"] else None
        if run_pos > 0 and run_level and close > run_level:
            run_pos += 1
        elif run_pos > 0 and run_level and close <= run_level:
            run_pos, run_level = 0, None          # 跌破冻结关键位 → run 失效
        elif run_pos == 0 and close > res_today:
            run_pos, run_level = 1, res_today     # 新 run
        else:
            run_pos, run_level = 0, None

        est_amount = s["amount_wan"] * 1e4 * scale
        r_vol = est_amount / float(p["amt_base"])
        d = (close - run_level) if (run_pos > 0 and run_level) else None
        a_pct = (d / run_level) if (d is not None and run_level) else None
        z_atr = (d / atr) if (d is not None and atr) else None

        ok_amp = z_atr is not None and z_atr >= args.k
        ok_time = args.m + 1 <= run_pos <= args.max_elapsed
        # 涨停豁免：现价已达涨停价（用涨幅 ≥ 9.7%/19.7% 近似，按板块）
        limit_pct = 20.0 if code.startswith("30") else 10.0
        is_limit = (close / prev_close - 1) * 100 >= limit_pct - 0.3
        ok_vol = (args.rmin <= r_vol <= args.rmax) or is_limit
        rows.append({
            "code": code, "name": s["name"], "close": close, "chg": (close / prev_close - 1) * 100,
            "run_pos": run_pos, "run_level": run_level, "res_today": res_today,
            "a_pct": a_pct, "z_atr": z_atr, "r_vol": r_vol, "atr_pct": (atr / close * 100) if atr else None,
            "turnover": s["turnover"], "is_limit": is_limit,
            "pass_count": int(ok_amp) + int(ok_time) + int(ok_vol),
            "ok_amp": ok_amp, "ok_time": ok_time, "ok_vol": ok_vol,
        })

    rows.sort(key=lambda r: (-r["pass_count"], -(r["z_atr"] or -99)))
    hit = [r for r in rows if r["pass_count"] >= args.min_pass and 1 <= r["run_pos"] <= args.run_max]
    print(f"候选：{len(rows)} 只｜满足 ≥{args.min_pass} 道且突破距今 ≤{args.run_max} 日：{len(hit)} 只\n")
    print(f"{'代码':<8}{'名称':<8}{'现价':>8}{'今日':>8}{'距今':>6}{'关键位':>8}{'幅度':>8}{'z×ATR':>8}{'量能':>7}{'门槛':>6}{'涨停':>5}")
    for r in hit[:40]:
        ago = {1: "今天", 2: "昨天", 3: "2天前"}.get(r["run_pos"], f"{r['run_pos']-1}天前")
        print(f"{r['code']:<8}{r['name']:<8}{r['close']:>8.2f}{r['chg']:>7.2f}%{ago:>6}"
              f"{r['run_level'] or 0:>8.2f}{(r['a_pct'] or 0)*100:>7.2f}%{(r['z_atr'] or 0):>8.2f}"
              f"{r['r_vol']:>7.2f}{r['pass_count']:>5}/3{'  是' if r['is_limit'] else ''}")
    print("\n⚠️ 盘中预演：现价随时可能变化，量能为按时间折算的全日预估，不构成收盘确认。")
    return rows, hit


if __name__ == "__main__":
    main()
