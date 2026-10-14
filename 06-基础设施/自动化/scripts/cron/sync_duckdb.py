#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""归档入库：调用 08-数据分析 的 loader，把 vault 归档同步进 duckdb。

放在 cron 16:30 独立执行：入库失败不影响盘后日更（两者解耦）。
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from vault_stocks import VAULT  # noqa: E402

PROJECT = VAULT / "08-数据分析"
PY = PROJECT / ".venv/bin/python3"
LOADER = PROJECT / "scripts/import_daily_archives.py"


def main():
    if not PY.exists() or not LOADER.exists():
        print("跳过入库：缺少 %s 或 %s" % (PY, LOADER))
        return 0
    try:
        p = subprocess.run([str(PY), str(LOADER)], capture_output=True, text=True,
                           timeout=900, cwd=str(PROJECT))
    except subprocess.TimeoutExpired:
        print("✗ 入库超时（>900s）", file=sys.stderr)
        return 1
    sys.stdout.write(p.stdout)
    if p.returncode != 0:
        sys.stderr.write(p.stderr[-1500:])
        print("✗ duckdb 入库失败（vault 归档不受影响）", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
