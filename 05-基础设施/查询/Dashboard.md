---
type: 索引
created: 2026-08-11
updated: 2026-08-13
tags:
  - 重要
---

# Dashboard（数据库视图）

> 用 Databases（核心插件）搭的数据视图总览。数据来源是各目录笔记的 frontmatter 字段，字段规范见 [[frontmatter 规范]]。
> 视图可嵌入任意笔记：下方三个是常用视图。如果某个视图没有正常渲染（显示为代码块或报错），用 Cmd+P → **Create new database view** 按"重建步骤"重新创建。

## 个股观察清单

来源：02-市场研究/个股档案（+基金档案）；筛选：状态 = 观察中

```database
{
  "name": "个股观察清单",
  "source": {
    "type": "folder",
    "path": "02-市场研究/个股档案"
  },
  "filters": [],
  "columns": [
    { "key": "file.name", "name": "标的", "type": "TEXT" },
    { "key": "ticker", "name": "代码", "type": "TEXT" },
    { "key": "board", "name": "板块", "type": "TEXT" },
    { "key": "updated", "name": "更新", "type": "DATE" }
  ]
}
```

**重建步骤**：Cmd+P → Create new database view → 来源选"文件夹：02-市场研究/个股档案" → 加列：file.name/ticker/board/updated → 加筛选：状态 等于 观察中 → 按 updated 降序。

## 复盘列表

来源：03-复盘与计划/复盘笔记；排序：period 降序

```database
{
  "name": "复盘列表",
  "source": {
    "type": "folder",
    "path": "03-复盘与计划/复盘笔记"
  },
  "filters": [],
  "columns": [
    { "key": "file.name", "name": "复盘", "type": "TEXT" },
    { "key": "period", "name": "区间", "type": "DATE" },
    { "key": "updated", "name": "更新", "type": "DATE" }
  ]
}
```

**重建步骤**：Cmd+P → Create new database view → 来源"文件夹：03-复盘与计划/复盘笔记" → 加列：file.name/period/updated → 按 period 降序。

## 读书清单

来源：06-阅读笔记；按 read_status 分组

```database
{
  "name": "读书清单",
  "source": {
    "type": "folder",
    "path": "06-阅读笔记"
  },
  "filters": [],
  "columns": [
    { "key": "file.name", "name": "书", "type": "TEXT" },
    { "key": "read_status", "name": "状态", "type": "TEXT" },
    { "key": "updated", "name": "更新", "type": "DATE" }
  ]
}
```

**重建步骤**：Cmd+P → Create new database view → 来源"文件夹：06-阅读笔记" → 加列：file.name/read_status/updated → 视图格式切换"表格"或"看板"（按 read_status 分组）。

## 相关

- 查询说明 → [[查询]]
- 字段规范 → [[frontmatter 规范]]
- 标签词表 → [[标签体系]]
