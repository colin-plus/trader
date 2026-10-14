#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分价成交量日更：覆盖全部个股档案标的（自动发现）。

口径（重要）：
  * **当日分价与主动买卖同源**——优先东财逐笔（details），不可用时用腾讯逐笔；
    逐笔自带成交方向，按 0.01 元档聚合既得"分价档"又得"主动买/卖"，
    避免"分钟价格栅格"把主动买卖数据截断（实测会丢掉 20%~50% 的主动买卖量）。
  * 窗口内更早的交易日（接口只给最近 5 个交易日）用分钟数据：东财 trends2 → 新浪 1 分钟 bar。
  * 落盘按日**不覆盖**：一个交易日只写一次（首落盘源为准），已归档的日期不再改写；
    --force 才强制重写当日。这样同一天不会出现两个口径混写。

用法：
  python3 collect_fenjia.py [--only 603203,601838] [--force] [--no-commit] [--quiet]
"""
import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from vault_stocks import discover, curl_get, jsonp, git_commit, PROFILE_SCRIPTS  # noqa: E402

sys.path.insert(0, str(PROFILE_SCRIPTS))
from apply_fenjia import update_files  # noqa: E402

EM_TRENDS = ("https://push2his.eastmoney.com/api/qt/stock/trends2/get?secid={secid}"
             "&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13"
             "&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=5&iscr=0&cb=__cb_x")
EM_DETAILS = ("https://push2.eastmoney.com/api/qt/stock/details/get?secid={secid}"
              "&fields1=f1,f2,f3,f4,f5&fields2=f51,f52,f53,f54,f55"
              "&pos=-100000&count=100000&cb=__cb_y")
SINA_KLINE = ("https://quotes.sina.cn/cn/api/jsonp_v2.php/__cb_s/CN_MarketDataService.getKLineData"
              "?symbol={sym}&scale=1&ma=no&datalen=1023")
TX_DETAIL = "https://stock.gtimg.cn/data/index.php?appn=detail&action=data&c={sym}&p={p}"
TX_PAGE_RE = None


def _retry(fn, attempts=3):
    """网络抖动重试（东财、新浪都是时通时断）。"""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            if i < attempts - 1:
                time.sleep(1.5 * (i + 1))
    raise last


def em_trends(secid):
    """东财 5 日 1 分钟分时 → [[date, price, hands], ...]"""
    code, txt = curl_get(EM_TRENDS.format(secid=secid), "https://quote.eastmoney.com/")
    if code != 200:
        raise RuntimeError("HTTP %d" % code)
    trends = (jsonp(txt, "__cb_x").get("data") or {}).get("trends") or []
    if not trends:
        raise RuntimeError("无分时数据")
    agg = defaultdict(int)
    for line in trends:
        f = line.split(",")
        if len(f) < 6:
            continue
        agg[(f[0][:10], round(float(f[2]), 2))] += int(round(float(f[5])))
    return [[d, p, v] for (d, p), v in sorted(agg.items())]


def sina_rows(sym, ndays=5):
    """新浪 1 分钟 bar → [[date, price, hands], ...]（volume 股 ÷100 = 手）"""
    code, txt = curl_get(SINA_KLINE.format(sym=sym), "https://finance.sina.com.cn/")
    if code != 200:
        raise RuntimeError("HTTP %d" % code)
    arr = jsonp(txt, "__cb_s")
    if not arr:
        raise RuntimeError("新浪无数据")
    byday = defaultdict(lambda: defaultdict(float))
    for a in arr:
        byday[a["day"][:10]][round(float(a["close"]), 2)] += float(a["volume"]) / 100.0
    out = []
    for d in sorted(byday)[-ndays:]:
        for p, v in sorted(byday[d].items()):
            out.append([d, p, int(round(v))])
    return out


def em_ticks(secid):
    """东财当日逐笔 → (agg, bs, neutral)：agg{价格:手数} / bs{价格:[买,卖]}"""
    code, txt = curl_get(EM_DETAILS.format(secid=secid), "https://quote.eastmoney.com/")
    if code != 200:
        raise RuntimeError("HTTP %d" % code)
    details = (jsonp(txt, "__cb_y").get("data") or {}).get("details") or []
    if not details:
        raise RuntimeError("无逐笔数据")
    agg = defaultdict(float)
    bs = defaultdict(lambda: [0.0, 0.0])
    neutral = 0.0
    for x in details:
        f = x.split(",")
        p = round(float(f[1]), 2)
        h = float(f[2])
        agg[p] += h
        if f[4] == "2":
            bs[p][0] += h
        elif f[4] == "1":
            bs[p][1] += h
        else:
            neutral += h
    return agg, bs, neutral


def tx_ticks(sym, max_pages=900, pause=0.15, budget=180.0):
    """腾讯逐笔（备用）→ (agg, bs, neutral)，分页取到没有数据为止"""
    import re
    page_re = re.compile(r'=\[(.*?),\s*"(.*)"\]\s*;?', re.S)
    agg = defaultdict(float)
    bs = defaultdict(lambda: [0.0, 0.0])
    neutral = 0.0
    seen = set()
    empty = 0
    started = time.time()
    for p in range(max_pages):
        if time.time() - started > budget:
            break
        try:
            code, txt = curl_get(TX_DETAIL.format(sym=sym, p=p), "https://gu.qq.com/", 15)
        except Exception:  # noqa: BLE001
            break
        if code != 200:
            break
        m = page_re.search(txt)
        if not m:
            empty += 1
            if empty >= 2:
                break
            continue
        empty = 0
        for row in m.group(2).split("|"):
            f = row.split("/")
            if len(f) < 7:
                continue
            try:
                idx = int(f[0])
            except ValueError:
                continue
            if idx in seen:
                continue
            seen.add(idx)
            price = round(float(f[2]), 2)
            hands = float(f[4])
            agg[price] += hands
            side = f[6].strip()
            if side == "B":
                bs[price][0] += hands
            elif side == "S":
                bs[price][1] += hands
            else:
                neutral += hands
        time.sleep(pause)
    if not agg:
        raise RuntimeError("腾讯逐笔无数据")
    return agg, bs, neutral


def csv_last_date(path):
    """CSV 已归档的最新日期。"""
    if not path.exists():
        return ""
    last = ""
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        f = line.split(",")
        if f and f[0].startswith("20") and f[0] > last:
            last = f[0]
    return last


def fmt_bs(bs):
    return dict(("%.2f" % k, [int(round(v[0])), int(round(v[1]))]) for k, v in bs.items())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只跑指定代码，逗号分隔")
    ap.add_argument("--force", action="store_true", help="强制重写当日（默认按日不覆盖）")
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--pause", type=float, default=1.0, help="标的间隔秒数")
    ap.add_argument("--tx-budget", type=float, default=900.0, help="腾讯逐笔总预算（秒）")
    args = ap.parse_args()

    only = set(c.strip() for c in args.only.split(",") if c.strip())
    stocks = [s for s in discover() if not only or s["code"] in only]
    if not stocks:
        print("未发现个股档案标的", file=sys.stderr)
        return 1

    done, failed, warns, skipped = [], [], [], []
    tx_left = args.tx_budget
    for i, s in enumerate(stocks):
        try:
            if not args.force and csv_last_date(s["dir"] / "分价表数据.csv"):
                pass  # 仍需取数判断当日是否已归档，见下
            # 1) 分钟窗口（用于回补窗口内更早的交易日）
            minute, src_min = None, ""
            try:
                minute = _retry(lambda: em_trends(s["secid"]))
                src_min = "东财分时"
            except Exception as e1:  # noqa: BLE001
                try:
                    minute = _retry(lambda: sina_rows(s["sym"]))
                    src_min = "新浪分钟"
                except Exception as e2:  # noqa: BLE001
                    raise RuntimeError("分钟数据不可用（东财 %s / 新浪 %s）" % (e1, e2))
            day = max(r[0] for r in minute)

            # 2) 当日已归档且非强制 → 无需再取逐笔
            if not args.force and csv_last_date(s["dir"] / "分价表数据.csv") >= day:
                skipped.append("%s: %s 已归档" % (s["name"], day))
                continue

            # 3) 当日逐笔单源（分价 + 主动买卖）
            tick_agg, tick_bs, tick_src, warn = None, None, "", ""
            try:
                tick_agg, tick_bs, _ = _retry(lambda: em_ticks(s["secid"]))
                tick_src = "东财逐笔"
            except Exception as e3:  # noqa: BLE001
                if tx_left > 5:
                    t0 = time.time()
                    tick_agg, tick_bs, neutral = tx_ticks(s["sym"], budget=min(180.0, tx_left))
                    tx_left -= time.time() - t0
                    tick_src = "腾讯逐笔"
                else:
                    warn = "逐笔不可用且腾讯预算用尽（%s）" % e3
            if tick_agg:
                day_hands = sum(tick_agg.values())
                tick_total = sum(v[0] + v[1] for v in tick_bs.values())
                # --force 只重写当日：窗口内更早交易日的历史（含其逐笔主动买卖）无法再取，
                # 绝不能因为强制重跑而丢掉。
                rows = [] if args.force else [r for r in minute if r[0] != day]
                rows += [[day, p, int(round(v))] for p, v in sorted(tick_agg.items())]
                bs = fmt_bs(tick_bs)
                src = "%s + %s" % (src_min, tick_src)
                if day_hands:
                    warn = warn or ("主动买卖覆盖率 %.0f%%（其余为中性盘）"
                                    % (100.0 * tick_total / day_hands))
            else:
                rows = [r for r in minute if r[0] == day]
                bs = {}
                src = src_min + "(无逐笔)"
                warns.append("%s: %s，主动买卖列留空" % (s["name"], warn or "逐笔不可用"))

            wrote = update_files(s["folder"], rows, bs, bs_date=day, force=args.force)
            if wrote:
                done.append("%s %s 当日%d档/BS%d档" % (s["name"], src,
                                                  len([r for r in rows if r[0] == day]), len(bs)))
            else:
                skipped.append("%s: %s 已归档" % (s["name"], day))
        except Exception as e:  # noqa: BLE001
            failed.append("%s: %s" % (s["name"], e))
        if i < len(stocks) - 1:
            time.sleep(args.pause)

    if done or failed or not args.quiet:
        print("分价成交量日更：%d 只档案股，写入 %d 只，跳过 %d 只%s"
              % (len(stocks), len(done), len(skipped),
                 ("，失败 %d 只" % len(failed)) if failed else ""))
        for d in done:
            print("  ✓ " + d)
        for k in skipped:
            print("  – " + k)
        for w in warns:
            print("  ⚠️ " + w, file=sys.stderr)
        for f in failed:
            print("  ✗ " + f, file=sys.stderr)

    if not args.no_commit and (done or failed):
        msg = git_commit("分价成交量日更（cron 自动）")
        if msg and not args.quiet:
            print("  git: " + msg)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
