#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日更管道共享工具：标的发现 / HTTP 抓取 / git 提交。

标的以 vault 为唯一来源：03-市场研究/个股档案/<名称>（<6位代码>）/
—— 新增档案自动纳入日更，不需要改脚本或任务配置。

抓取统一走系统 curl：本机 requests 直连东财会被 403，curl（走系统代理）稳定；
注意保留完整桌面 UA 与 Referer，否则同样 403。
"""
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

VAULT = Path("/Users/zhanglubing/Obsidian/trader")
ARCHIVE = VAULT / "03-市场研究/个股档案"
PROFILE_SCRIPTS = Path("/Users/zhanglubing/.hermes/profiles/trader/scripts")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
FOLDER_RE = re.compile(r"^(?P<name>.+)（(?P<code>[0-9]{6})）$")


def discover():
    """扫描个股档案目录 → [{folder,name,code,secid,sym,dir}]，按代码排序。"""
    out = []
    if not ARCHIVE.is_dir():
        return out
    for d in sorted(ARCHIVE.iterdir()):
        if not d.is_dir():
            continue
        m = FOLDER_RE.match(d.name)
        if not m:
            continue
        code = m.group("code")
        market = "1" if code.startswith("6") else "0"   # 沪市 1. / 深市与北交所 0.
        out.append({
            "folder": d.name,
            "name": m.group("name"),
            "code": code,
            "secid": market + "." + code,
            "sym": ("sh" if market == "1" else "sz") + code,
            "dir": d,
        })
    return out


def curl_get(url, referer, timeout=25):
    """系统 curl 抓取 → (http_code, text)；连不上才抛异常。"""
    cmd = ["/usr/bin/curl", "-s", "--max-time", str(timeout), "-A", UA,
           "-H", "Referer: " + referer, "-w", "\n__HTTP__%{http_code}", url]
    p = subprocess.run(cmd, capture_output=True)
    text = p.stdout.decode("utf-8", "ignore")
    code = 0
    m = re.search(r"\n__HTTP__([0-9]{3})\s*$", text)
    if m:
        code = int(m.group(1))
        text = text[:m.start()]
    if code == 0:
        err = p.stderr.decode("utf-8", "ignore").strip()[:160]
        raise RuntimeError("curl exit %d %s" % (p.returncode, err))
    return code, text


def jsonp(text, marker=None):
    """剥 JSONP 包装 → Python 对象。marker 给定时从 marker 后的 '(' 开始取 JSON。"""
    if marker:
        k = text.find(marker + "(")
        i = k + len(marker) + 1 if k >= 0 else -1
    else:
        i = text.find("(") + 1
    j = text.rfind(")")
    if i <= 0 or j <= i:
        raise ValueError("非 JSONP 响应: " + text.strip()[:120])
    return json.loads(text[i:j])


def jitter(lo=2.0, hi=4.0):
    time.sleep(random.uniform(lo, hi))


def git_commit(message, vault=VAULT):
    """vault 有改动则 add/commit/push；无改动返回 None。push 失败只告警。"""
    def run(*args):
        return subprocess.run(["git", "-C", str(vault)] + list(args),
                              capture_output=True, text=True)
    if not run("status", "--porcelain").stdout.strip():
        return None
    run("add", "-A")
    c = run("commit", "-m", message)
    if c.returncode != 0:
        raise RuntimeError("git commit 失败: " + (c.stderr or c.stdout).strip()[:200])
    p = run("push", "origin", "main")
    if p.returncode != 0:
        print("⚠️ git push 失败（本地已提交）: " + (p.stderr or p.stdout).strip()[:200],
              file=sys.stderr)
    return "已提交"


if __name__ == "__main__":
    for s in discover():
        print(s["secid"], s["name"], s["folder"])
