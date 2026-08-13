---
type: 索引
created: 2026-08-11
updated: 2026-08-13
tags:
  - 重要
---

# Dashboard（数据库视图）

> 用 Bases（Databases 核心插件）搭的数据视图总览。数据来源是各目录笔记的 frontmatter 字段，字段规范见 [[frontmatter 规范]]。
> 语法要点（官方：obsidian.md/zh/help/bases）：数据库默认包含**全库文件**，靠 `filters` 筛选范围；`formulas` 定义公式列；`properties` 配列显示名；`views` 定义视图（type/name/filters/order）。
> 下方是 5 个常用视图，用 ```base 代码块声明（YAML 格式）。如果视图没有正常渲染（显示为代码块或报错），用命令面板 → **Create new base** 按各视图下方"重建步骤"重新创建。

## 个股观察清单

来源：02-市场研究/个股档案（type=档案 且非跟踪日志）；列：标的/代码/板块/更新；排序：updated 降序

```base
formulas:
  ticker: ticker
  board: board
properties:
  formula.ticker:
    displayName: 代码
  formula.board:
    displayName: 板块
views:
  - type: table
    name: 个股观察清单
    filters:
      and:
        - type == "档案"
        - file.name != "跟踪日志.md"
        - file.folder.startsWith("02-市场研究/个股档案")
    groupBy:
      property: file.folder
      direction: ASC
    order:
      - file.folder
      - file.name
      - updated
    sort: []

```

**重建步骤**：Cmd+P → Create new base → 筛选：type 等于 档案、文件名不等于 跟踪日志 → 加列 ticker/board → 按 updated 降序。

## 交易计划视图

来源：03-复盘与计划/交易计划（type=交易计划）；列：标的/代码/状态/创建；排序：created 降序

```base
formulas:
  ticker: ticker
  status: status
properties:
  formula.ticker:
    displayName: 代码
  formula.status:
    displayName: 状态
views:
  - type: table
    name: 交易计划
    filters:
      and:
        - type == "交易计划"
        - file.name != "交易计划模板.md"
        - file.folder.startsWith("03-复盘与计划/交易计划")
    groupBy:
      property: status
      direction: ASC
    order:
      - file.name
      - status
      - created
      - updated
    sort:
      - property: created
        direction: DESC

```

**重建步骤**：Cmd+P → Create new base → 筛选：type 等于 交易计划 → 加列 ticker/status → 按 created 降序。一眼看到哪些计划在跑、什么状态。

## 复盘列表

来源：03-复盘与计划/复盘笔记（type=复盘）；排序：period 降序

```base
views:
  - type: table
    name: 复盘列表
    filters:
      and:
        - type == "复盘"
        - file.name != "复盘笔记模板.md"
        - file.folder.startsWith("03-复盘与计划/复盘笔记")
    order:
      - file.basename
      - period
      - file.ctime
      - file.mtime
    sort:
      - property: period
        direction: DESC

```

**重建步骤**：Cmd+P → Create new base → 筛选：type 等于 复盘 → 按 period 降序。

## 读书清单

来源：06-阅读笔记（file.inFolder）；列：书/状态；按 read_status 分组（表格或看板）

```base
formulas:
  read_status: read_status
properties:
  formula.read_status:
    displayName: 状态
views:
  - type: table
    name: 读书清单
    filters:
      and:
        - file.inFolder("06-阅读笔记")
        - type == "学习笔记"
        - file.folder.startsWith("06-阅读笔记")
    order:
      - file.name
      - type
      - tags

```

**重建步骤**：Cmd+P → Create new base → 筛选：文件夹包含 06-阅读笔记、type 等于 学习笔记 → 加列 read_status → 视图格式切换"看板"（按 read_status 分组）。

## 认知清单看板

来源：01-底层知识/认知清单（file.inFolder）；列：认知/类别；按「类别」分组（看板）

```base
formulas:
  类别: 类别
properties:
  formula.类别:
    displayName: 类别
views:
  - type: table
    name: 认知清单
    filters:
      and:
        - file.inFolder("01-底层知识/认知清单")
        - type == "学习笔记"
    groupBy:
      property: formula.类别
      direction: ASC
    order:
      - file.name
      - created
      - updated
      - tags
    sort:
      - property: created
        direction: DESC
      - property: formula.类别
        direction: ASC

```

**重建步骤**：Cmd+P → Create new base → 筛选：文件夹包含 01-底层知识/认知清单 → 加列 类别 → 视图格式切换"看板"（按 类别 分组）。

## 相关

- 查询说明 → [[查询]]
- 字段规范 → [[frontmatter 规范]]
- 标签词表 → [[标签体系]]
- 官方语法 → obsidian.md/zh/help/bases（Bases 语法 / 创建 Base / 视图 / 公式 / 函数）
