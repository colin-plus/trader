#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识库结构自检（对应 2026-10-05 体检 P2-2「建立定期结构自检」）。

只读扫描，输出 7 类问题：
  1 坏链（指向不存在的笔记）
  2 歧义链（同名文件导致 [[链接]] 无法确定指向）
  3 目录缺同名索引笔记
  4 索引页与实际文件不符（认知库 / 精读提炼 / 跨书概念索引）
  5 孤儿笔记（无入链）
  6 frontmatter 问题 + type 分布
  7 未登记标签（对照 标签体系.md 词表）

用法：
    python3 结构自检.py                 # 扫全库
    python3 结构自检.py --base 01-底层知识   # 只扫某子目录

Obsidian 链接解析规则（本脚本据此判定）：
    带路径的链接按路径解析；不带路径的按文件名唯一匹配；同名多文件即歧义。
"""
import os, re, sys, argparse
from collections import defaultdict, Counter
import unicodedata

VAULT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
SKIP_DIRS = {'.git', '.obsidian', '.trash', '.venv', 'node_modules', '__pycache__'}

LINK_RE = re.compile(r'(?<!\!)\[\[([^\]]+?)\]\]')
EMBED_RE = re.compile(r'!\[\[([^\]]+?)\]\]')
META_OK = {'Home'}          # 无入链也属于正常（顶层入口）

# 已知占位符 / 示例：属"设计如此"，不算坏链（单独归类，不混进问题清单）
PLACEHOLDER_RE = re.compile(
    r'^(概念名|别名|茅台|认知A|认知B|认知-XXX-名称|认知名称|wikilink|《书A》-AI精读|'
    r'《书名》阅读笔记|文件名\.base(#.*)?|XXX.*|概念.*|笔记.*|链接.*)$')
TEMPLATE_DIR_MARK = os.sep + '模板' + os.sep


def norm(s):
    return unicodedata.normalize('NFC', s)


def strip_code(text):
    """去掉围栏代码块（``` 段）与行内代码（`...`），避免把文档示例当链接。"""
    text = re.sub(r'```.*?```', '', text, flags=re.S)
    text = re.sub(r'`+[^`]*`+', '', text)
    return text


def unescape_table_pipe(text):
    """Obsidian 表格单元格里的 `\\|` 是转义竖线，解析前还原为 |，
    否则 [[路径/笔记\\|显示名]] 会被误判成"路径以反斜杠结尾"的坏链。"""
    return text.replace('\\|', '|')


def is_placeholder(target):
    t = target.split('|')[0].split('#')[0].strip()
    t = t.replace('\\', '')
    return bool(PLACEHOLDER_RE.match(t))


def walk(base):
    md = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
        for f in files:
            if f.endswith('.zip'):
                continue
            md.append(norm(os.path.join(root, f)))
    return md


def rel(p):
    return os.path.relpath(p, VAULT)


class Audit:
    def __init__(self, base):
        self.base = os.path.abspath(base)
        self.all_files = walk(self.base)
        self.md_files = sorted(p for p in self.all_files if p.endswith('.md'))
        self.by_base = defaultdict(list)
        self.by_base_ext = defaultdict(list)
        for p in self.all_files:
            b = os.path.basename(p)
            self.by_base[os.path.splitext(b)[0]].append(p)
            self.by_base_ext[b].append(p)
        self.md_set = set(self.md_files)
        self.link_uses = []          # (源文件, 目标, 是否占位符)
        for p in self.md_files:
            txt = open(p, encoding='utf-8').read()
            txt = unescape_table_pipe(txt)
            txt = strip_code(txt)
            for m in LINK_RE.finditer(txt):
                self.link_uses.append((p, m.group(1), is_placeholder(m.group(1))))
            for m in EMBED_RE.finditer(txt):
                self.link_uses.append((p, m.group(1), is_placeholder(m.group(1))))

    def resolve(self, target):
        t = target.split('|')[0].split('#')[0].strip()
        if not t:
            return 'empty', []
        t = norm(t)
        for cand in (t, t + '.md'):
            if norm(cand) in self.md_set or norm(cand) in set(self.all_files):
                return 'ok', [cand]
        base = os.path.basename(t)
        if base in self.by_base_ext and len(self.by_base_ext[base]) == 1:
            return 'ok', self.by_base_ext[base]
        key = os.path.splitext(base)[0]
        if key in self.by_base:
            cands = self.by_base[key]
            if len(cands) == 1:
                return 'ok', cands
            if '/' in t:
                hits = [x for x in cands if norm(x).endswith(t) or norm(x).endswith(t + '.md')]
                if hits:
                    return 'ok', hits
            return 'ambiguous', cands
        return 'missing', []

    # ---------- 各项检查 ----------
    def check_links(self):
        broken, ambiguous, placeholders = [], [], []
        for src, raw, is_ph in self.link_uses:
            if is_ph:
                placeholders.append((src, raw))
                continue
            st, cands = self.resolve(raw)
            if st == 'missing':
                broken.append((src, raw))
            elif st == 'ambiguous':
                ambiguous.append((src, raw, cands))
        return broken, ambiguous, placeholders

    def check_dir_index(self):
        dirs = {os.path.dirname(p) for p in self.md_files if os.path.dirname(p)}
        out = []
        for d in sorted(dirs):
            b = os.path.basename(d)
            if not any(os.path.splitext(os.path.basename(x))[0] == b and x.endswith('.md')
                       for x in self.by_base.get(b, [])):
                out.append((d, len([p for p in self.md_files if os.path.dirname(p) == d])))
        return out

    def _links_of(self, path):
        txt = open(path, encoding='utf-8').read()
        txt = unescape_table_pipe(txt)
        out = set()
        for m in LINK_RE.finditer(txt):
            t = m.group(1).split('|')[0].split('#')[0].strip().replace('\\', '')
            if t:
                out.add(norm(os.path.splitext(os.path.basename(t))[0]))
        return out, txt

    def check_indexes(self):
        rows = []
        for suffix, idxname in (('认知库', '认知库.md'), ('精读提炼', '精读提炼.md')):
            for d in {os.path.dirname(p) for p in self.md_files}:
                if os.path.basename(d) != suffix:
                    continue
                files = {norm(os.path.splitext(os.path.basename(p))[0])
                         for p in self.md_files if os.path.dirname(p) == d} - {suffix}
                idx = os.path.join(d, idxname)
                if not os.path.isfile(idx):
                    continue
                linked, txt = self._links_of(idx)
                nums = re.findall(r'`(\d{3})`', txt)
                # 有条目编号的才算"收录条目"；总览表格里的链接不算（避免把章节目录表误当重复收录）
                numbered = re.findall(r'`(\d{3})`\s*\[\[([^\]]+?)\]\]', txt)
                names = [n.split('|')[0] for _, n in numbered]
                counts = Counter(names)
                # "链到不存在"只报真的解析不到的；占位符/示例与跨目录引用都不算问题
                dangling = sorted(t for t in (linked - files)
                                  if not is_placeholder(t) and self.resolve(t)[0] == 'missing')
                sibling = sorted(t for t in (linked - files)
                                 if t not in dangling and t in self.by_base)
                rows.append(dict(kind=suffix, index=rel(idx), dir_files=len(files),
                                 linked=len(linked & files),
                                 not_in_index=sorted(files - linked - {'认知库'}),
                                 dangling=dangling, sibling=sibling,
                                 entries=len(names), uniq=len(counts),
                                 dup=[(k, v) for k, v in counts.items() if v > 1],
                                 codes=len(nums), codes_uniq=len(set(nums))))
        for p in self.md_files:
            if p.endswith('跨书概念索引.md'):
                linked, txt = self._links_of(p)
                txt = strip_code(txt)
                dangling = sorted({t.split('|')[0].split('#')[0].strip()
                                   for t in LINK_RE.findall(txt)
                                   if not is_placeholder(t)
                                   and self.resolve(t)[0] != 'ok'})
                rows.append(dict(kind='跨书概念索引', index=rel(p), linked=len(linked),
                                 dangling=dangling))
        return rows

    def check_orphans(self):
        inbound = Counter()
        for src, raw, is_ph in self.link_uses:
            if is_ph:
                continue
            st, cands = self.resolve(raw)
            if st == 'ok':
                for c in cands:
                    if c.endswith('.md'):
                        inbound[norm(os.path.splitext(os.path.basename(c))[0])] += 1
        return [rel(p) for p in self.md_files
                if inbound[norm(os.path.splitext(os.path.basename(p))[0])] == 0
                and norm(os.path.splitext(os.path.basename(p))[0]) not in META_OK]

    def check_frontmatter(self):
        bad, types = [], Counter()
        for p in self.md_files:
            txt = open(p, encoding='utf-8').read()
            if not txt.startswith('---'):
                bad.append((rel(p), 'no-frontmatter')); continue
            parts = txt.split('---', 2)
            if len(parts) < 3:
                bad.append((rel(p), 'unterminated-frontmatter')); continue
            fm = parts[1]
            for f in ('type', 'created', 'updated'):
                if not re.search(r'^%s\s*:' % f, fm, re.M):
                    bad.append((rel(p), 'missing:' + f))
            m = re.search(r'^type\s*:\s*(.+)$', fm, re.M)
            types[m.group(1).strip() if m else '(无)'] += 1
        return bad, types

    def check_tags(self):
        spec = next((p for p in self.md_files if p.endswith('标签体系.md')), None)
        registered = set()
        if spec:
            registered = set(re.findall(r'`#([^`]+)`', open(spec, encoding='utf-8').read()))
        counter = Counter()
        tag_like = re.compile(r'^(知识|状态|复盘|分析|策略|周期|类型|市场|来源|主题|行业|个股|基金|题材)/')
        for p in self.md_files:
            txt = open(p, encoding='utf-8').read()
            parts = txt.split('---', 2)
            fm = parts[1] if txt.startswith('---') and len(parts) >= 3 else ''
            for tm in re.finditer(r'^\s*-\s*([^\s#]+)\s*$', fm, re.M):
                counter[tm.group(1)] += 1
            for tm in re.finditer(r'\[([^\]]+)\]', fm):
                for x in tm.group(1).split(','):
                    counter[x.strip()] += 1
        unreg = {t: c for t, c in counter.items() if tag_like.match(t) and t not in registered}
        return unreg, len(registered)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default=VAULT)
    a = ap.parse_args()
    au = Audit(a.base)

    print('扫描:', rel(au.base) or '.', '｜ 文件 %d，其中 .md %d ｜ 链接 %d 处'
          % (len(au.all_files), len(au.md_files), len(au.link_uses)))

    broken, ambiguous, placeholders = au.check_links()
    bylink = defaultdict(list)
    for src, raw in broken:
        bylink[raw].append(rel(src))
    print('\n==== 1. 坏链 ====')
    for raw, srcs in sorted(bylink.items(), key=lambda x: -len(x[1])):
        print('  [[%s]] ← %d 处: %s' % (raw, len(srcs), ', '.join(sorted(set(srcs)))))
    print('  合计 %d 个目标 / %d 处' % (len(bylink), len(broken)))

    print('\n==== 1b. 占位符 / 示例（不算问题，仅列出）====')
    ph = defaultdict(int)
    for src, raw in placeholders:
        ph[raw] += 1
    for raw, n in sorted(ph.items(), key=lambda x: -x[1]):
        print('  [[%s]] × %d' % (raw, n))
    print('  合计 %d 个 / %d 处' % (len(ph), len(placeholders)))

    byamb = defaultdict(lambda: defaultdict(list))
    for src, raw, cands in ambiguous:
        byamb[raw][tuple(cands)].append(rel(src))
    print('\n==== 2. 歧义链 ====')
    for raw, groups in sorted(byamb.items()):
        for cands, srcs in groups.items():
            print('  [[%s]] ← %d 处 ｜ 候选 %d 个: %s'
                  % (raw, len(srcs), len(cands), [rel(c) for c in cands]))
    print('  合计 %d 个目标 / %d 处' % (len(byamb), len(ambiguous)))

    print('\n==== 3. 目录缺同名索引 ====')
    for d, n in au.check_dir_index():
        print('  %s/ (%d 篇)' % (rel(d), n))

    print('\n==== 4. 索引页与实际文件不符 ====')
    for r in au.check_indexes():
        print('  [%s] %s' % (r['kind'], r['index']))
        for k in ('dir_files', 'linked', 'entries', 'uniq', 'codes', 'codes_uniq'):
            if k in r:
                print('      %-10s %s' % (k, r[k]))
        if r.get('not_in_index'):
            print('      未收录 %d: %s' % (len(r['not_in_index']), r['not_in_index'][:15]))
        if r.get('dangling'):
            print('      链到不存在 %d: %s' % (len(r['dangling']), r['dangling'][:15]))
        if r.get('sibling'):
            print('      ⚠ 子页放在别处（结构不齐，非死链）%d: %s'
                  % (len(r['sibling']), r['sibling'][:15]))
        if r.get('dup'):
            print('      重复收录 %d 个: %s' % (len(r['dup']), r['dup'][:10]))

    orph = au.check_orphans()
    print('\n==== 5. 孤儿笔记 ====')
    for p in orph:
        print('  %s' % p)
    print('  合计 %d 篇' % len(orph))

    bad, types = au.check_frontmatter()
    print('\n==== 6. frontmatter ====')
    for p, why in bad:
        print('  %-56s %s' % (p, why))
    print('  合计 %d 处问题' % len(bad))
    print('  type 分布:', dict(types.most_common()))

    unreg, nreg = au.check_tags()
    print('\n==== 7. 未登记标签（词表已登记 %d 个）====' % nreg)
    for t, c in sorted(unreg.items(), key=lambda x: -x[1]):
        print('  #%-30s %d 次' % (t, c))
    print('  合计 %d 个' % len(unreg))


if __name__ == '__main__':
    main()
