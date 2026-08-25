#!/usr/bin/env python3
"""初始化 duckdb：建表 + 导入数据。

数据源：
- daily_kline：腾讯 fqkline 接口（全量历史）
- fenjia：vault 内 个股档案/*/分价表数据.csv（累积数据）
- fund_flow：vault 内 个股档案/*/资金流向.md（表格行解析）
"""
import json
import pathlib
import re
import sys
import urllib.request

import duckdb
import pandas as pd

VAULT = pathlib.Path("/Users/zhanglubing/Obsidian/trader")
DB_PATH = pathlib.Path(__file__).parent.parent / "data" / "trader.duckdb"
ARCHIVE = VAULT / "03-市场研究" / "个股档案"

# 关注的股票：(代码, 名称, 腾讯代码)
STOCKS = [
    ("603005", "晶方科技", "sh603005"),
    ("601838", "成都银行", "sh601838"),
    ("003043", "华亚智能", "sz003043"),
]


def fetch_kline(tencent_code, n=400):
    """腾讯日线接口（本机可直连，稳定）"""
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={tencent_code},day,,,{n},qfq"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=20).read())
    node = d["data"][tencent_code]
    k = node.get("qfqday") or node.get("day")
    rows = []
    for r in k:
        rows.append({
            "code": tencent_code[2:],
            "date": r[0],
            "open": float(r[1]),
            "close": float(r[2]),
            "high": float(r[3]),
            "low": float(r[4]),
            "volume": float(r[5]),
        })
    return rows


def load_fenjia(code):
    """从 vault 分价表数据.csv 读累积数据"""
    for folder in ARCHIVE.iterdir():
        if not folder.is_dir():
            continue
        csv = folder / "分价表数据.csv"
        if not csv.exists():
            continue
        # 文件夹名：名称（代码）
        m = re.search(r"（(\d{6})）", folder.name)
        if m and m.group(1) == code:
            df = pd.read_csv(csv)
            df = df.rename(columns={"日期": "date", "价格": "price", "手数": "vol"})
            df["code"] = code
            df = df[["code", "date", "price", "vol"]]
            df["buy"] = pd.to_numeric(df["主动买"], errors="coerce").fillna(0).astype(int) if "主动买" in df.columns else 0
            df["sell"] = pd.to_numeric(df["主动卖"], errors="coerce").fillna(0).astype(int) if "主动卖" in df.columns else 0
            return df
    return pd.DataFrame()


def load_fund_flow(code):
    """从 vault 资金流向.md 解析表格行"""
    for folder in ARCHIVE.iterdir():
        if not folder.is_dir():
            continue
        m = re.search(r"（(\d{6})）", folder.name)
        if not (m and m.group(1) == code):
            continue
        md = folder / "资金流向.md"
        if not md.exists():
            return pd.DataFrame()
        rows = []
        in_table = False
        for line in md.read_text(encoding="utf-8").splitlines():
            if line.startswith("| 日期 |"):
                in_table = True
                continue
            if not in_table:
                continue
            if not line.startswith("| "):
                if line.startswith("|---") or line.startswith("|--"):
                    continue  # 分隔线
                break
            p = [x.strip() for x in line.strip("|").split("|")]
            if len(p) < 9 or not p[0].startswith("20"):
                continue

            def to_yi(s):
                s = s.replace("+", "")
                return float(s.replace("亿", "")) if s else 0.0

            rows.append({
                "code": code,
                "date": p[0],
                "zhuli": to_yi(p[1]),       # 主力净流入（亿）
                "zdc": to_yi(p[3]),          # 超大单
                "dd": to_yi(p[4]),           # 大单
                "zd": to_yi(p[5]),           # 中单
                "xd": to_yi(p[6]),           # 小单
                "pct": float(p[2].rstrip("%")),
                "close": float(p[7]),
                "chg": float(p[8].rstrip("%")),
            })
        return pd.DataFrame(rows)
    return pd.DataFrame()


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))

    con.execute("CREATE TABLE IF NOT EXISTS daily_kline (code VARCHAR, date DATE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE)")
    con.execute("CREATE TABLE IF NOT EXISTS fenjia (code VARCHAR, date DATE, price DOUBLE, vol INTEGER, buy INTEGER, sell INTEGER)")
    con.execute("CREATE TABLE IF NOT EXISTS fund_flow (code VARCHAR, date DATE, zhuli DOUBLE, zdc DOUBLE, dd DOUBLE, zd DOUBLE, xd DOUBLE, pct DOUBLE, close DOUBLE, chg DOUBLE)")
    con.execute("CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value VARCHAR)")

    for code, name, tcode in STOCKS:
        # 日线
        rows = fetch_kline(tcode)
        df = pd.DataFrame(rows)
        con.execute("DELETE FROM daily_kline WHERE code = ?", [code])
        con.register("tmp_df", df)
        con.execute(
            "INSERT INTO daily_kline (code, date, open, high, low, close, volume) "
            "SELECT code, date, open, high, low, close, volume FROM tmp_df"
        )
        print(f"✓ {name} 日线: {len(df)} 行")

        # 分价
        df = load_fenjia(code)
        if not df.empty:
            con.execute("DELETE FROM fenjia WHERE code = ?", [code])
            con.register("tmp_fj", df)
            con.execute(
                "INSERT INTO fenjia (code, date, price, vol, buy, sell) "
                "SELECT code, date, price, vol, buy, sell FROM tmp_fj"
            )
            print(f"✓ {name} 分价: {len(df)} 行")
        else:
            print(f"⚠ {name} 分价: 无数据")

        # 资金流
        df = load_fund_flow(code)
        if not df.empty:
            con.execute("DELETE FROM fund_flow WHERE code = ?", [code])
            con.register("tmp_ff", df)
            con.execute(
                "INSERT INTO fund_flow (code, date, zhuli, zdc, dd, zd, xd, pct, close, chg) "
                "SELECT code, date, zhuli, zdc, dd, zd, xd, pct, close, chg FROM tmp_ff"
            )
            print(f"✓ {name} 资金流: {len(df)} 行")
        else:
            print(f"⚠ {name} 资金流: 无数据")

    con.execute("INSERT OR REPLACE INTO meta VALUES ('updated_at', current_timestamp::VARCHAR)")
    con.close()
    print(f"\n数据库: {DB_PATH}")
    print("完成")


if __name__ == "__main__":
    main()
