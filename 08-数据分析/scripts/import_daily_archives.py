#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 vault 归档同步进 duckdb（只读 vault，不修改任何笔记）。

  03-市场研究/个股档案/<标的>/资金流向.md   表格 → daily_capital_flow
  03-市场研究/个股档案/<标的>/分价表数据.csv        → volume_profile

幂等：INSERT OR REPLACE（主键 code+date / code+date+price）。
金额单位与既有表一致：亿元（表里 -0.04 即 -0.04 亿）。
"""
import re
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent          # 08-数据分析
DB = ROOT / "data" / "trader.duckdb"
ARCHIVE = Path("/Users/zhanglubing/Obsidian/trader/03-市场研究/个股档案")
FOLDER_RE = re.compile(r"^(.+)（([0-9]{6})）$")


def amount(s):
    s = s.strip().replace("+", "")
    if not s or s == "待补":
        return 0.0
    return float(s.replace("亿", ""))


def pct(s):
    s = s.strip().replace("%", "")
    if not s or s == "待补":
        return 0.0
    return float(s)


def targets():
    if not ARCHIVE.is_dir():
        return []
    out = []
    for d in sorted(ARCHIVE.iterdir()):
        if not d.is_dir():
            continue
        m = FOLDER_RE.match(d.name)
        if m:
            out.append((m.group(2), d))
    return out


def fflow_rows():
    rows = []
    for code, d in targets():
        md = d / "资金流向.md"
        if not md.exists():
            continue
        in_tbl = False
        for line in md.read_text(encoding="utf-8").splitlines():
            if line.startswith("| 日期 |"):
                in_tbl = True
                continue
            if not in_tbl:
                continue
            if not line.startswith("|"):
                break
            if not line.startswith("| "):
                continue
            p = [x.strip() for x in line.strip("|").split("|")]
            if len(p) < 9 or not p[0].startswith("20"):
                continue
            try:
                rows.append((code, p[0], amount(p[1]), amount(p[3]), amount(p[4]),
                             amount(p[5]), amount(p[6]), pct(p[2]), float(p[7]), pct(p[8])))
            except ValueError:
                continue
    return rows


def vp_rows():
    rows = []
    for code, d in targets():
        csv = d / "分价表数据.csv"
        if not csv.exists():
            continue
        lines = csv.read_text(encoding="utf-8").splitlines()
        for line in lines[1:]:
            f = line.split(",")
            if len(f) < 6 or not f[0].startswith("20"):
                continue
            try:
                rows.append((code, f[0], float(f[1]), int(f[2]),
                             int(f[4] or 0), int(f[5] or 0)))
            except ValueError:
                continue
    return rows


def main():
    if not DB.exists():
        print("duckdb 不存在: %s" % DB, file=sys.stderr)
        return 1
    ff, vp = fflow_rows(), vp_rows()
    try:
        con = duckdb.connect(str(DB))
        if ff:
            con.executemany(
                "INSERT OR REPLACE INTO daily_capital_flow "
                "(code,date,zhuli,zdc,dd,zd,xd,pct,close,chg) VALUES (?,?,?,?,?,?,?,?,?,?)", ff)
        if vp:
            con.executemany(
                "INSERT OR REPLACE INTO volume_profile (code,date,price,vol,buy,sell) "
                "VALUES (?,?,?,?,?,?)", vp)
        a = con.execute("select count(*), max(date) from daily_capital_flow").fetchone()
        b = con.execute("select count(*), max(date) from volume_profile").fetchone()
        c = con.execute("select count(distinct code) from volume_profile").fetchone()[0]
        con.close()
    except Exception as e:  # noqa: BLE001
        print("duckdb 写入失败（可能被其他进程占用）: %s" % e, file=sys.stderr)
        return 1
    print("归档入库：资金流 %d 行（最新 %s）｜分价 %d 行 / %d 只（最新 %s）"
          % (a[0], a[1], b[0], c, b[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
