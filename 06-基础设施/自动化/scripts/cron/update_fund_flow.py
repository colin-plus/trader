#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资金流向日更：覆盖全部个股档案标的（自动发现）。

- 数据源：东方财富资金流 push2his fflow daykline（主力=超大单+大单，第三方估算，仅供参考）
- 落盘：03-市场研究/个股档案/<标的>/资金流向.md（表格 + 近5日小结 + 图表），新标的自动建档
- 幂等：按日期合并重写，可重复运行；接口窗口 12 日，天然补漏
- 失败：单只失败不影响其他标的，最终 exit 1 触发 cron 告警
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from vault_stocks import discover, curl_get, jsonp, git_commit  # noqa: E402

URL = ("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?lmt=12&klt=101"
       "&secid={secid}&fields1=f1,f2,f3,f7"
       "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65&cb=__cb_x")
# 降级源（2026-10-14 实测可用）：push2his 被限流时用 datacenter 报表，
# 但它只给最近 1 个交易日、只有超大单/大单两档真实，中单/小单记 0。
DC_URL = ("https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_DMSK_TS_STOCKNEW"
          "&columns=ALL&filter=(SECUCODE%3D%22{secucode}%22)&pageNumber=1&pageSize=5"
          "&sortColumns=TRADE_DATE&sortTypes=-1")
TX_KLINE = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,2,qfq"

SKELETON = """---
type: 档案
ticker: {code}
created: {today}
updated: {today}
tags: [类型/股票, 市场/A股, 个股/{name}, 分析/技术面]
---

# {name}（{code}）资金流向

> 每日主力资金净流向跟踪。数据源：东方财富资金流（按单笔金额分超大单/大单/中单/小单，**主力=超大单+大单，第三方估算，仅供参考**）。每日收盘后由 cron 自动更新（15:40）。
> 用法：连续流入=资金关注，连续流出+股价滞涨=警惕；资金流是辅助指标，不单独作为决策依据。
> 归档说明（2026-10-14 起）：本文件由 cron 对全部个股档案标的自动建/维护，作为数据存档供后续分析；持仓标的的当日交易记录见对应交易计划。
"""

TBL_HEADER = "| 日期 | 主力净流 | 占比 | 超大单 | 大单 | 中单 | 小单 | 收盘 | 涨跌 | 信号 |"
TBL_SEP = "|------|---------|------|--------|------|------|------|------|------|------|"
SUMMARY_HEADER = "## 近 5 日趋势小结（自动更新）"
CHART_HEADER = "## 资金流向图（近 20 日，自动更新）"


def fetch(secid, attempts=3):
    last = None
    for i in range(attempts):
        try:
            code, txt = curl_get(URL.format(secid=secid), "https://data.eastmoney.com/")
            if code != 200:
                raise RuntimeError("HTTP %d" % code)
            klines = (jsonp(txt, "__cb_x").get("data") or {}).get("klines") or []
            if klines:
                return klines
            raise RuntimeError("接口无数据")
        except Exception as e:  # noqa: BLE001
            last = e
            if i < attempts - 1:
                time.sleep(4 * (i + 1))
    raise RuntimeError("东财资金流接口失败: %s" % last)


def tx_volume_hand(code):
    """腾讯日 K 的当日成交量（手），用于降级源近似估算主力占比。"""
    sym = ("sh" if code.startswith("6") else "sz") + code
    code_http, txt = curl_get(TX_KLINE.format(sym=sym), "https://gu.qq.com/")
    if code_http != 200:
        raise RuntimeError("HTTP %d" % code_http)
    node = json.loads(txt)["data"][sym]
    k = node.get("qfqday") or node.get("day")
    if not k:
        raise RuntimeError("腾讯 K 线无数据")
    return float(k[-1][5])


def fetch_dc(code, name):
    """降级：datacenter 报表 → 接口原始行（15 列，兼容 parse_line）。

    仅超大单/大单两档真实；中单/小单记 0（文件头"数据说明"已注明该口径）。
    占比用 腾讯成交量×100×收盘价 近似成交额后折算（会被后续 push2his 精确值覆盖）。
    """
    secucode = code + (".SH" if code.startswith("6") else ".SZ")
    code_http, txt = curl_get(DC_URL.format(secucode=secucode), "https://data.eastmoney.com/")
    if code_http != 200:
        raise RuntimeError("HTTP %d" % code_http)
    rows = (json.loads(txt).get("result") or {}).get("data") or []
    if not rows:
        raise RuntimeError("报表无数据")
    r = rows[0]
    date = r["TRADE_DATE"][:10]
    prime = float(r["PRIME_INFLOW"])
    sup = float(r["SUPERDEAL_INFLOW"]) - float(r["SUPERDEAL_OUTFLOW"])
    big = float(r["BIGDEAL_INFLOW"]) - float(r["BIGDEAL_OUTFLOW"])
    close = float(r["CLOSE_PRICE"])
    chg = float(r["CHANGE_RATE"])
    try:
        amount = tx_volume_hand(code) * 100 * close
        pct = prime / amount * 100 if amount else 0.0
    except Exception:  # noqa: BLE001
        pct = 0.0
    line = ",".join([date, "%.0f" % prime, "0", "0", "%.0f" % big, "%.0f" % sup,
                     "%.2f" % pct, "0", "0", "0", "0",
                     "%.2f" % close, "%.2f" % chg, "0", "0"])
    return [line]


def signal(zhuli, pct, chg):
    if zhuli > 0 and pct >= 10:
        return "明显流入"
    if zhuli > 0:
        return "流入"
    if pct >= -2:
        return "基本平衡"
    return "流出"


def parse_line(line):
    p = line.split(",")
    return {
        "date": p[0],
        "zhuli": float(p[1]),
        "xd": float(p[2]),
        "zd": float(p[3]),
        "dd": float(p[4]),
        "zdc": float(p[5]),
        "pct": float(p[6]),
        "close": p[11],
        "chg": p[12],
    }


def fmt_num(v):
    return "待补" if v is None else "%.2f亿" % (v / 1e8)


def fmt_row(r):
    zl = "%+.2f亿" % (r["zhuli"] / 1e8)
    pct = "%.2f%%" % r["pct"]
    zdc = "%+.2f亿" % (r["zdc"] / 1e8)
    dd = "%+.2f亿" % (r["dd"] / 1e8)
    zd = fmt_num(r.get("zd"))
    xd = fmt_num(r.get("xd"))
    return "| %s | %s | %s | %s | %s | %s | %s | %s | %s%% | %s |" % (
        r["date"], zl, pct, zdc, dd, zd, xd, r["close"], r["chg"],
        signal(r["zhuli"], r["pct"], r["chg"]))


def summary(rows):
    last5 = rows[-5:]
    total = sum(r["zhuli"] for r in last5) / 1e8
    streak = 0
    for r in reversed(last5):
        if r["zhuli"] > 0:
            streak += 1
        else:
            break
    if streak >= 3:
        direction = "连续 %d 日净流入，资金持续关注" % streak
    elif streak == 0:
        direction = "最近 1 日净流出"
    else:
        direction = "最近 %d 日净流入" % streak
    return (SUMMARY_HEADER + "\n\n"
            + "- 主力 5 日净流合计：约 %+.2f 亿\n" % total
            + "- %s\n" % direction
            + "- 解读：资金流为第三方估算，仅作辅助参考（详见文件头说明）\n")


def chart_block(rows):
    last = rows[-20:]
    labels = ", ".join('"%s"' % r["date"][5:] for r in last)

    def split_series(vals, label_pos, label_neg):
        pos = [max(v, 0) for v in vals]
        neg = [min(v, 0) for v in vals]
        return [
            "  - title: %s\n    data: [%s]" % (label_pos, ", ".join("%.2f" % v for v in pos)),
            "  - title: %s\n    data: [%s]" % (label_neg, ", ".join("%.2f" % v for v in neg)),
        ]

    def axis(vals_all):
        lo = min(-1, int(min(vals_all)) - 1)
        hi = max(1, int(max(vals_all)) + 1)
        return "yAxis:\n  - min: %d\n    max: %d" % (lo, hi)

    all_vals = [r[k] / 1e8 for r in last for k in ("zhuli", "zdc", "dd", "zd", "xd")
                if k in r and r[k] is not None]

    s1 = []
    zl = [r["zhuli"] / 1e8 for r in last]
    s1.append("  - title: 主力净流入\n    data: [%s]" % ", ".join("%.2f" % v for v in zl))
    s1 += split_series(zl, "主力流入(>0)", "主力流出(<0)")
    if all(r.get("zd") is not None and r.get("xd") is not None for r in last):
        sh = [(r["zd"] + r["xd"]) / 1e8 for r in last]
        s1.append("  - title: 散户净流入\n    data: [%s]" % ", ".join("%.2f" % v for v in sh))
        s1 += split_series(sh, "散户流入(>0)", "散户流出(<0)")
    chart1 = ("### 主力 vs 散户（0 轴分色）\n\n```chart\ntype: line\nlabels: [%s]\nseries:\n"
              % labels + "\n".join(s1)
              + "\nfill: true\nbeginAtZero: true\ntension: 0.4\nlegend: true\n"
              + axis(all_vals) + "\n```\n")

    s2 = []
    for key, label in (("zdc", "超大单"), ("dd", "大单"), ("zd", "中单"), ("xd", "小单")):
        if all(key in r and r[key] is not None for r in last):
            s2.append("  - title: %s\n    data: [%s]"
                      % (label, ", ".join("%.2f" % (r[key] / 1e8) for r in last)))
    chart2 = ("### 资金谱系明细（4 档）\n\n```chart\ntype: line\nlabels: [%s]\nseries:\n"
              % labels + "\n".join(s2)
              + "\nfill: true\nbeginAtZero: true\ntension: 0.4\nlegend: true\n"
              + axis(all_vals) + "\n```\n")

    return (CHART_HEADER + "\n\n"
            + "> 交互：点击图例可单独查看某条线；散户=中单+小单。\n\n"
            + chart1 + "\n" + chart2)


def replace_section(text, header_line, new_block, stop_pattern=r"^## "):
    esc = re.escape(header_line)
    pattern = re.compile(r"^" + esc + r".*?(?=" + stop_pattern + r"|\Z)", re.M | re.S)
    m = pattern.search(text)
    if not m:
        return text, False
    return text[:m.start()] + new_block.rstrip() + "\n" + text[m.end():], True


def insert_after_last(text, prefix, block):
    lines = text.split("\n")
    idx = None
    for i, ln in enumerate(lines):
        if ln.startswith(prefix):
            idx = i
    if idx is None:
        return text.rstrip() + "\n\n" + block.rstrip() + "\n"
    lines.insert(idx + 1, "\n" + block.rstrip() + "\n")
    return "\n".join(lines)


def parse_amount(s):
    s = s.replace("+", "")
    if not s or s == "待补":
        return 0
    return float(s.replace("亿", "")) * 1e8


def parse_existing_rows(txt):
    rows = []
    in_table = False
    for line in txt.splitlines():
        if line.startswith("| 日期 |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        if not line.startswith("| "):
            continue
        p = [x.strip() for x in line.strip("|").split("|")]
        if len(p) < 9 or not p[0].startswith("20"):
            continue
        try:
            rows.append({
                "date": p[0],
                "zhuli": float(p[1].replace("亿", "").replace("+", "")) * 1e8 if p[1].endswith("亿") else float(p[1].replace("+", "")),
                "xd": parse_amount(p[6]),
                "zd": parse_amount(p[5]),
                "dd": parse_amount(p[4]),
                "zdc": parse_amount(p[3]),
                "pct": float(p[2].rstrip("%")),
                "close": p[7],
                "chg": p[8].rstrip("%"),
            })
        except (ValueError, IndexError):
            continue
    return rows


def merge_rows(existing, new_rows, prefer_existing=False):
    merged = dict((r["date"], r) for r in existing)
    for r in new_rows:
        if prefer_existing and r["date"] in merged:
            continue          # 降级数据不覆盖已有的精确数据
        merged[r["date"]] = r
    return [merged[d] for d in sorted(merged)]


def update_file(path, rows, name, code, prefer_existing=False):
    """写入/更新一份资金流向.md 并返回新文本；文件不存在则自动建档（表+小结+图表）。"""
    created = not path.exists()
    if created:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SKELETON.format(name=name, code=code,
                                        today=dt.date.today().isoformat()), encoding="utf-8")
    txt = path.read_text(encoding="utf-8")
    existing = parse_existing_rows(txt)
    all_rows = merge_rows(existing, rows, prefer_existing=prefer_existing)
    table_block = TBL_HEADER + "\n" + TBL_SEP + "\n" + "\n".join(fmt_row(r) for r in all_rows)
    summary_block = summary(all_rows)
    chart = chart_block(all_rows)

    if created and not existing:
        txt = (txt.rstrip() + "\n\n" + table_block + "\n\n"
               + summary_block.rstrip() + "\n\n" + chart.rstrip() + "\n")
    else:
        txt, hit = replace_section(txt, "| 日期 | 主力净流", table_block, stop_pattern=r"^## |^> ")
        if not hit:
            if "## " in txt:
                head, _, rest = txt.partition("## ")
                txt = head + table_block + "\n\n## " + rest
            else:
                txt = txt.rstrip() + "\n\n" + table_block + "\n"
        txt, hit = replace_section(txt, SUMMARY_HEADER, summary_block, stop_pattern=r"^> |^## ")
        if not hit:
            txt = insert_after_last(txt, "| 20", summary_block)
        txt, hit = replace_section(txt, CHART_HEADER, chart)
        if not hit:
            txt = insert_after_last(txt, "- 解读：", chart)
    path.write_text(txt, encoding="utf-8")
    return txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="只跑指定代码，逗号分隔")
    ap.add_argument("--inject", default="",
                    help="注入模式：读取 {'名称'|'secid'|'代码': [klines原始行]} 的 JSON，"
                         "供浏览器取数后落盘（东财封禁时的人工/agent 补救路径）")
    ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="无新增且无失败时不输出（供补漏任务）")
    ap.add_argument("--pause", type=float, default=3.0, help="标的间隔秒数")
    args = ap.parse_args()

    only = set(c.strip() for c in args.only.split(",") if c.strip())
    stocks = [s for s in discover() if not only or s["code"] in only]
    if not stocks:
        print("未发现个股档案标的", file=sys.stderr)
        return 1

    injected = None
    if args.inject:
        injected = json.loads(Path(args.inject).read_text(encoding="utf-8"))

    updated, degraded, failed = [], [], []
    for i, s in enumerate(stocks):
        try:
            prefer_existing = False
            if injected is not None:
                klines = (injected.get(s["name"]) or injected.get(s["secid"])
                          or injected.get(s["code"]))
                if not klines:
                    raise RuntimeError("注入文件中无此标的")
            else:
                try:
                    klines = fetch(s["secid"])
                except Exception as e1:  # noqa: BLE001
                    # push2his 被限流 → datacenter 降级（仅最近 1 日、只有超大/大单两档真实）
                    klines = fetch_dc(s["code"], s["name"])
                    prefer_existing = True
                    degraded.append(s["name"])
            rows = [parse_line(k) for k in klines]
            md = s["dir"] / "资金流向.md"
            before = md.read_text(encoding="utf-8") if md.exists() else ""
            after = update_file(md, rows, s["name"], s["code"], prefer_existing=prefer_existing)
            if after != before:
                updated.append(s["name"])
        except Exception as e:  # noqa: BLE001
            failed.append("%s: %s" % (s["name"], e))
        if i < len(stocks) - 1:
            time.sleep(args.pause)

    if updated or failed or not args.quiet:
        print("资金流向日更：%d 只档案股，更新 %d 只%s"
              % (len(stocks), len(updated),
                 ("，失败 %d 只" % len(failed)) if failed else ""))
        if updated:
            print("  已更新：" + "、".join(updated))
        if degraded:
            print("  ⚠️ push2his 不可用，以下标的走了 datacenter 降级源（仅主力/超大/大单真实，"
                  "中/小单记 0）：" + "、".join(degraded), file=sys.stderr)
        for f in failed:
            print("  ✗ " + f, file=sys.stderr)

    if not args.no_commit and (updated or failed):
        msg = git_commit("资金流向日更（cron 自动）", paths=["03-市场研究/个股档案"])
        if msg and not args.quiet:
            print("  git: " + msg)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
