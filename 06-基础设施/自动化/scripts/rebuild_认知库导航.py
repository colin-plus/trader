#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rebuild_认知库导航.py —— 按 认知库顺序.txt 重建认知库的线性导航

做三件事：
  1. 校验顺序清单与实际文件一一对应（漏项/死链/重复即报错退出，不写任何文件）
  2. 给每条认知笔记写入标签（认知/序号、认知/章节）并在正文末尾生成「导航」块
  3. 重建 01-底层知识/认知库/认知库.md 索引（章节 + 有序链接 + 阅读进度图）

幂等：导航块由固定标记包裹，重跑只替换该块，不累积。改顺序后直接重跑即可。

用法：
    python3 06-基础设施/自动化/scripts/rebuild_认知库导航.py            # 写入
    python3 06-基础设施/自动化/scripts/rebuild_认知库导航.py --dry-run  # 只报告
"""
import os
import re
import sys
import datetime

VAULT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
NOTE_DIR = os.path.join(VAULT, '01-底层知识', '认知库')
ORDER_FILE = os.path.join(VAULT, '06-基础设施', '自动化', 'scripts', '认知库顺序.txt')
INDEX_FILE = os.path.join(NOTE_DIR, '认知库.md')

BEGIN = '<!-- 导航:begin（由 rebuild_认知库导航.py 生成，勿手改） -->'
END = '<!-- 导航:end -->'


def parse_order(path):
    """解析顺序清单 -> [(章节号, 章节名, 导语, [概念...]), ...]"""
    chapters = []
    cur = None
    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip('\n')
            s = line.strip()
            if not s:
                continue
            # 先判 ## 章节，再判 # 注释（顺序反了会把章节当注释吞掉）
            m = re.match(r'^##\s+(.+)$', s)
            if m:
                title = m.group(1).strip()
                mm = re.match(r'^([一二三四五六七八九十]+)、(.+?)(?:\s*（\d+\s*条）)?$', title)
                num, name = (mm.group(1), mm.group(2)) if mm else ('', title)
                cur = {'num': num, 'name': name, 'intro': '', 'items': []}
                chapters.append(cur)
                continue
            if s.startswith('#'):
                continue
            if s.startswith('>'):
                if cur is not None:
                    cur['intro'] = s.lstrip('> ').strip()
                continue
            # 条目行：允许 "1. 概念名" 或裸 "概念名"
            item = re.sub(r'^\d+[.、]\s*', '', s).strip()
            if item and cur is not None:
                cur['items'].append(item)
    return [c for c in chapters if c['items']]


def validate(chapters):
    files = {f[:-3] for f in os.listdir(NOTE_DIR)
             if f.endswith('.md') and f != '认知库.md'}
    listed = [it for c in chapters for it in c['items']]
    problems = []
    dup = sorted({x for x in listed if listed.count(x) > 1})
    if dup:
        problems.append('顺序清单内重复: %s' % dup)
    missing = sorted(files - set(listed))
    if missing:
        problems.append('库中有但清单漏掉（%d 条）: %s' % (len(missing), missing))
    dead = sorted(set(listed) - files)
    if dead:
        problems.append('清单中有但无文件（死链，%d 条）: %s' % (len(dead), dead))
    return files, problems


def build_seq(chapters):
    """返回 seq[概念] = dict(n, total, chap, chap_name, prev, next)"""
    total = sum(len(c['items']) for c in chapters)
    flat = [(c, it) for c in chapters for it in c['items']]
    seq = {}
    for i, (c, it) in enumerate(flat):
        seq[it] = {
            'n': i + 1,
            'total': total,
            'chap': c['name'],
            'chap_num': c['num'],
            'prev': flat[i - 1][1] if i > 0 else None,
            'next': flat[i + 1][1] if i < total - 1 else None,
        }
    return seq, flat


def split_frontmatter(text):
    """返回 (frontmatter 行列表 或 None, 正文)"""
    m = re.match(r'^---\n(.*?)\n---\n?', text, re.S)
    if not m:
        return None, text
    return m.group(1).split('\n'), text[m.end():]


def set_scalar(fm_lines, key, value):
    """在 frontmatter 行列表中设置标量字段（保留其余内容与顺序）"""
    out, done = [], False
    for line in fm_lines:
        if re.match(r'^%s\s*:' % re.escape(key), line):
            out.append('%s: %s' % (key, value))
            done = True
        else:
            out.append(line)
    if not done:
        out.append('%s: %s' % (key, value))
    return out


def set_nav_tags(fm_lines, n, chap_name):
    """维护标签数组里的 认知/序号 与 认知/章节（幂等替换）"""
    want = ['认知/%03d' % n, '认知/章节-%s' % chap_name]
    # 找出 tags: 块的行号区间
    start = None
    for i, line in enumerate(fm_lines):
        if re.match(r'^tags\s*:', line):
            start = i
            break
    if start is None:
        fm_lines.append('tags:')
        start = len(fm_lines) - 1
        for w in want:
            fm_lines.append('  - %s' % w)
        return fm_lines
    end = start + 1
    while end < len(fm_lines) and re.match(r'^\s+-\s', fm_lines[end]):
        end += 1
    kept = [l for l in fm_lines[start + 1:end]
            if not re.match(r'^\s+-\s*认知/', l)]
    new = kept + ['  - %s' % w for w in want]
    return fm_lines[:start + 1] + new + fm_lines[end:]


def nav_block(concept, info):
    prev = '[[%s]]' % info['prev'] if info['prev'] else '（已是第一条）'
    nxt = '[[%s]]' % info['next'] if info['next'] else '（已是最后一条）'
    if info['n'] == 1:
        prev = '**本条起**'
    if info['n'] == info['total']:
        nxt = '**本条终**'
    return '\n'.join([
        BEGIN,
        '## 导航',
        '',
        '**上一条** %s ｜ **返回目录** [[认知库]] ｜ **下一条** %s' % (prev, nxt),
        '第 %d / %d 条 ｜ 第%s章 %s' % (info['n'], info['total'], info['chap_num'], info['chap']),
        END,
    ])


def strip_old_nav(body):
    body = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END) + r'\n?', '', body, flags=re.S)
    return body.rstrip('\n') + '\n'


def rebuild_notes(seq, dry_run):
    changed = []
    for concept, info in sorted(seq.items(), key=lambda kv: kv[1]['n']):
        path = os.path.join(NOTE_DIR, concept + '.md')
        with open(path, encoding='utf-8') as f:
            text = f.read()
        fm, body = split_frontmatter(text)
        if fm is None:
            print('!! 无 frontmatter，跳过: %s' % concept)
            continue
        fm = set_scalar(fm, '认知序号', info['n'])
        fm = set_scalar(fm, '认知章节', info['chap'])
        fm = set_nav_tags(fm, info['n'], info['chap'])
        body = strip_old_nav(body) + '\n' + nav_block(concept, info) + '\n'
        new_text = '---\n' + '\n'.join(fm) + '\n---\n' + body
        if new_text != text:
            changed.append(concept)
            if not dry_run:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_text)
    return changed


def rebuild_index(chapters, seq, dry_run):
    today = datetime.date.today().isoformat()
    total = sum(len(c['items']) for c in chapters)
    L = []
    L.append('---')
    L.append('type: 索引')
    L.append('created: 2026-08-21')
    L.append('updated: %s' % today)
    L.append('tags:')
    L.append('  - 重要')
    L.append('---')
    L.append('')
    L.append('# 认知库')
    L.append('')
    L.append('> 按**概念**组织的认知库（MOC）——每条认知一个文件，概念名为文件名，跨书来源挂 frontmatter。')
    L.append('> 与 [[精读提炼]]（按书组织）互为双视图：认知库=从认知看书，精读提炼=从书看认知。')
    L.append('>')
    L.append('> **阅读方式**：本页是**有序目录**，共 %d 条，每条只归属一个章节。' % total)
    L.append('> 顺读用每篇笔记底部的「上一条 / 下一条」；顺序清单见 [[认知库顺序说明]]。')
    L.append('')
    L.append('## 总览')
    L.append('')
    L.append('| 章 | 章节 | 条数 | 位置 |')
    L.append('| -- | ---- | ---- | ---- |')
    n = 0
    for c in chapters:
        lo, hi = n + 1, n + len(c['items'])
        n = hi
        rng = '第 %d 条' % lo if lo == hi else '第 %d–%d 条' % (lo, hi)
        L.append('| %s | [[#%s、%s\\|%s]] | %d | %s |'
                 % (c['num'], c['num'], c['name'], c['name'], len(c['items']), rng))
    L.append('| — | **合计** | **%d** | 第 1–%d 条 |' % (total, total))
    L.append('')
    for c in chapters:
        L.append('## %s、%s' % (c['num'], c['name']))
        L.append('')
        if c['intro']:
            L.append('> %s' % c['intro'])
            L.append('')
        for it in c['items']:
            L.append('- `%03d` [[%s]]' % (seq[it]['n'], it))
        L.append('')
    L.append('---')
    L.append('')
    L.append('## 使用说明')
    L.append('')
    L.append('1. **顺读**：任一条底部有「上一条 / 下一条」，可 1 → %d 一路读完不断链' % total)
    L.append('2. **跳章**：用上方「总览」表跳到章节锚点')
    L.append('3. **新增认知**：复制 [[认知库模板]]，文件名=概念名；再到顺序清单登记，重跑脚本')
    L.append('4. **改顺序**：编辑 [[认知库顺序说明]] 指向的 `认知库顺序.txt`，重跑脚本（笔记与索引一起更新）')
    L.append('5. **引用**：`[[概念名]]` 精准链接；`![[概念名]]` 嵌入内容')
    L.append('')
    L.append('## 相关')
    L.append('')
    L.append('- [[认知库顺序说明]] — 顺序清单与维护方式')
    L.append('- [[精读提炼]] — 按书组织的精读笔记（另一视图）')
    L.append('- [[跨书概念索引]] — 同一概念在各书的出处')
    L.append('- [[认知库模板]] — 认知文件模板')
    L.append('')
    text = '\n'.join(L)
    if not dry_run:
        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            f.write(text)
    return text


def main():
    dry_run = '--dry-run' in sys.argv
    chapters = parse_order(ORDER_FILE)
    files, problems = validate(chapters)
    if problems:
        print('校验未通过，未写入任何文件：')
        for p in problems:
            print('  - %s' % p)
        return 1
    seq, flat = build_seq(chapters)
    print('顺序清单校验通过：%d 条 / %d 章 / 库中 %d 个文件'
          % (len(seq), len(chapters), len(files)))
    if dry_run:
        print('--dry-run：不写入。前 5 条与后 3 条预览：')
        for c, it in flat[:5] + flat[-3:]:
            i = seq[it]
            print('  %03d  [%s] %s  ← 上:%s 下:%s'
                  % (i['n'], i['chap'], it, i['prev'], i['next']))
        return 0
    changed = rebuild_notes(seq, dry_run)
    rebuild_index(chapters, seq, dry_run)
    print('已更新笔记 %d 篇，索引 1 篇' % len(changed))
    return 0


if __name__ == '__main__':
    sys.exit(main())
