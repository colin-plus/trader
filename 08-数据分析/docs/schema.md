# 数据模型规范（Schema 权威文档）

> 观澜（TideScope）数据层设计文档。数据库实现见 `scripts/apply_schema.py`（幂等重建）。
> 变更表结构时：**先改本文档 → 再改 apply_schema.py → 执行迁移**，保持文档与实现同步。

## 总体设计

```
investable_asset（标的主数据）
  ├── watchlist        关注标的（用户关系）
  ├── position         持仓快照（我的数据，抄券商）
  ├── transaction      交易记录（我的数据，抄券商）
  ├── daily_kline      日线行情（1 标的 : N 日）
  ├── volume_profile   分价分布（1 标的 : N 日 : N 价格档）
  ├── daily_capital_flow 资金流向·日（1 标的 : N 日）
  ├── finance          财务数据（1 标的 : N 报告期 × kind）
  ├── margin_factor    估值因子（静态·财报期）
  ├── margin_daily     估值日快照（动态·每日）
  ├── margin_evaluation 安全边际评估（事件·人工）
  └── margin_macro     宏观基准（全市场共用）
meta                    库级元信息（更新时间等）
```

**Performance（收益统计）**：领域概念，**不建表**——由 position + transaction + daily_kline（最新收盘价）实时计算（app/performance.py），API `/api/performance/*`。口径：最终对账以券商 APP 为准，本层为辅助分析（持仓市值/浮盈/已实现盈亏/交易统计）。

**安全边际（Margin of Safety）**：四张 `margin_` 前缀表构成评估体系——`margin_factor`（因子，财报驱动，静态）→ `margin_daily`（估值快照，价格驱动，每日 cron 计算落库）→ `margin_evaluation`（评估事件，人工决策一次一条）→ `margin_macro`（宏观基准，全市场共用）。计算流：因子 + 行情 + 宏观 → cron 算 margin_daily → 评估时读取落 margin_evaluation。

### 工程约定（非教条，务实原则）

| 约定 | 规则 | 理由 |
|---|---|---|
| 主键 | 自然键：`code`（A股代码全局唯一）；数据表用复合主键 | 免代理键 JOIN，防重复 |
| 外键 | 所有数据表 `code REFERENCES investable_asset(code)`，`ON DELETE NO ACTION` | 防止孤儿数据；删除标的需显式处理 |
| 日期 | `DATE` 类型，禁用字符串；API 层转 `YYYY-MM-DD` | 时间运算（区间/排序）可靠 |
| 价格 | `DOUBLE`（行情价/资金额）；展示层格式化 | 金融浮点精度够用（展示），不做金额运算精度敏感 |
| 数量 | 成交量/手数用 `INTEGER`（整数手），禁 DOUBLE | 手数本质是整数，避免浮点累积误差 |
| 枚举 | `CHECK` 约束（type/kind），不在应用层散落魔法值 | 非法值在入库时被拒 |
| 可空 | 核心业务字段 `NOT NULL`（code/name/date/price）；可选字段可空 | 数据质量兜底 |
| 注释 | 每表/每字段 `COMMENT`（duckdb_columns 可查） | 库内自解释，IDE/脚本可读 |
| 审计 | `created_at TIMESTAMP DEFAULT now()` 记录入库时间 | 排查数据来源/时间 |

---

## 表：investable_asset（标的主数据）

**用途**：全库锚点。股票与 ETF 的统一抽象（可投资资产），所有行情/财务表的 code 外键目标。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| code | VARCHAR | PK, NOT NULL | 标的代码（6 位，如 003043 / 510300） |
| name | VARCHAR | NOT NULL | 标的名称（如 华亚智能） |
| type | VARCHAR | NOT NULL, CHECK IN ('stock','etf') | 类型：股票 / ETF |
| exchange | VARCHAR | NULL | 交易所：SH / SZ |
| industry | VARCHAR | NULL | 行业（仅股票，如 半导体） |
| list_date | DATE | NULL | 上市日期 |
| created_at | TIMESTAMP | DEFAULT now() | 记录创建时间 |

**说明**：ETF 属基金大类，当前仅跟踪 ETF 一种，故 type 用 'etf'；未来加 LOF 等可扩枚举。ETF 无 industry，可空。

**数据来源**：全市场股票目录由 `scripts/seed_all_stocks.py` 从本地 market.duckdb（DBX 数据浏览器维护，`~/Github/market/data/market.duckdb`）全量导入——4593 只沪深主板+创业板（无科创板/北交所/B股），幂等可重复运行；行业取一级大类名（约 53% 覆盖，无映射留 NULL）。

---

## 表：watchlist（关注标的）

**用途**：用户关注的标的列表（"关注标的"菜单的数据源）。与 investable_asset 一对一（当前设计一只标的一条关注记录）。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| code | VARCHAR | PK, NOT NULL, FK→investable_asset | 标的主键，天然防重复关注 |
| added_at | DATE | DEFAULT current_date | 加入关注日期 |
| note | VARCHAR | NULL | 关注备注（可选） |
| sort_order | INTEGER | DEFAULT 0, NOT NULL | 列表排序（升序） |
| active | BOOLEAN | DEFAULT TRUE, NOT NULL | 是否启用（可暂时移除不删记录） |

**说明**：用 `active` 软移除而非 DELETE——保留历史关注痕迹；前端只查 `WHERE active`。

---

## 表：position（持仓快照）

**用途**："我的数据"。当前持仓状态（股数/成本），手动维护、抄券商口径。**交易执行权威在券商**，本表只是展示/计算基准。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| code | VARCHAR | PK, NOT NULL, FK→investable_asset | 标的代码 |
| shares | INTEGER | NOT NULL | 持仓股数 |
| cost | DOUBLE | NOT NULL | 成本价（摊薄，券商口径） |
| updated_at | TIMESTAMP | DEFAULT now() | 最近更新 |

**说明**：快照而非推导——券商配股/分红/费用会改变真实成本，推导会失真；手动维护与券商一致。由 transaction 推导只作为核对（不实现）。

---

## 表：transaction（交易记录）

**用途**："我的数据"。每一笔买卖事实（金额/费用抄券商），用于 Performance 计算与交易复盘。与知识库"交易明细表"同构。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK, NOT NULL | 交易序号（手动分配） |
| code | VARCHAR | NOT NULL, FK→investable_asset | 标的代码 |
| trade_date | DATE | NOT NULL | 交易日 |
| direction | VARCHAR | NOT NULL, CHECK IN ('buy','sell') | 买卖方向 |
| price | DOUBLE | NOT NULL | 成交价 |
| shares | INTEGER | NOT NULL | 数量（股） |
| amount | DOUBLE | NOT NULL | 金额（价×量） |
| fee | DOUBLE | DEFAULT 0, NOT NULL | 费用（佣金+过户费） |
| note | VARCHAR | NULL | 备注 |

**说明**：事实表（事件流），用代理键 id（同一天多笔交易）。`amount = price × shares` 由录入方保证（库内不加冗余 CHECK）。数字抄券商，不手算。

---

## Performance（收益统计·概念）

**不建表**，实时计算（`app/performance.py`）：

- 单标的：持仓市值 = shares × 最新收盘价；浮盈 = (最新价 − cost) × shares；已实现 = Σ卖出净收 − Σ卖出股数 × cost
- 汇总：全账户市值/成本/浮盈/已实现，按标的展开
- **口径**：辅助分析（胜率/盈亏分布），最终对账以券商 APP 为准

---

## 表：daily_kline（日线行情）

**用途**：每日 OHLCV（前复权），K线页数据源。来源：腾讯 fqkline。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| code | VARCHAR | PK 复合, NOT NULL, FK→investable_asset | 标的代码 |
| date | DATE | PK 复合, NOT NULL | 交易日 |
| open | DOUBLE | NOT NULL | 开盘价 |
| high | DOUBLE | NOT NULL | 最高价 |
| low | DOUBLE | NOT NULL | 最低价 |
| close | DOUBLE | NOT NULL | 收盘价（前复权口径） |
| volume | INTEGER | NOT NULL | 成交量（手） |

**说明**：复合主键 (code, date) 保证"一只标的一天一行"。OHLC 完整性由采集脚本保证（腾讯源缺失则整行跳过）。复权口径统一 qfq（前复权），API 层不做二次换算。

---

## 表：volume_profile（分价分布）

**用途**：每日每个价格档位的成交量分布（找支撑/阻力位），分价页数据源。来源：东财分时聚合。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| code | VARCHAR | PK 复合, NOT NULL, FK→investable_asset | 标的代码 |
| date | DATE | PK 复合, NOT NULL | 交易日 |
| price | DOUBLE | PK 复合, NOT NULL | 价格档位 |
| vol | INTEGER | NOT NULL | 该价位成交量（手） |
| buy | INTEGER | NOT NULL | 主动买量（手） |
| sell | INTEGER | NOT NULL | 主动卖量（手） |

**说明**：复合主键 (code, date, price) 保证"一标的一天一价一档"。`vol = buy + sell` 的守恒由采集脚本校验（脚本内断言，库内不加冗余 CHECK 以免重建成本）。名称取机构术语 Volume Profile（成交量轮廓），避免与金融统计"价格概率分布"混淆。

---

## 表：daily_capital_flow（资金流向·日）

**用途**：每日主力/散户资金动向，资金流页数据源。来源：东财 fflow。金额单位：亿元。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| code | VARCHAR | PK 复合, NOT NULL, FK→investable_asset | 标的代码 |
| date | DATE | PK 复合, NOT NULL | 交易日 |
| zhuli | DOUBLE | NOT NULL | 主力净流入（亿） |
| zdc | DOUBLE | NOT NULL | 超大单净流入（亿） |
| dd | DOUBLE | NOT NULL | 大单净流入（亿） |
| zd | DOUBLE | NOT NULL | 中单净流入（亿） |
| xd | DOUBLE | NOT NULL | 小单净流入（亿） |
| pct | DOUBLE | NOT NULL | 涨跌幅（%） |
| close | DOUBLE | NOT NULL | 收盘价 |
| chg | DOUBLE | NULL | 主力净流入占比（%） |

**说明**：单位统一亿（东财口径），字段名沿用数据源缩写（zdc=超大单等）——与采集脚本/数据源一致，减少换算错误。复合主键 (code, date) 防同日重复。

---

## 表：finance（财务数据）

**用途**：财务/分红等非行情数据，财务页数据源。来源：东财 F10。**单表 + kind 分类**——新指标加新 kind 不用改表结构（季度快照/利润表/资产负债表/分红统一收纳）。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| code | VARCHAR | PK 复合, NOT NULL, FK→investable_asset | 标的代码 |
| report_date | DATE | PK 复合, NOT NULL | 报告期（分红除权日 / 财报截止日） |
| kind | VARCHAR | PK 复合, NOT NULL, CHECK IN ('dividend','snapshot','income','balance') | 数据类型 |
| payload | JSON | NOT NULL | 该 kind 的具体字段（结构见下） |

**kind 与 payload 约定**：

| kind | report_date 含义 | payload 结构 |
|---|---|---|
| dividend | 除权除息日 | `{"cash_per_share": 每10股派现金(元), "plan": "10派2.5", "record_date": "股权登记日", "ex_date": "除权日", "pay_date": "派息日"}` |
| snapshot | 报告期截止日 | 核心指标快照：`{"revenue": 营收, "net_profit": 净利, "roe": 净资产收益率, "eps": 每股收益, "gross_margin": 毛利率, "debt_ratio": 资产负债率}` |
| income | 报告期截止日 | 利润表明细：`{"revenue": 营收, "operating_profit": 营业利润, "net_profit": 净利, "eps": 每股收益, "growth_yoy": 同比增速, ...}` |
| balance | 报告期截止日 | 资产负债表详情：`{"assets": 总资产, "liabilities": 总负债, "equity": 净资产, "cash": 货币资金, ...}` |

**说明**：JSON payload 的取舍——个人工具灵活性优先（新指标不加列），代价是库内不保证字段完整性，由采集脚本校验，字段约定见上表（文档级强类型）。复合主键 (code, report_date, kind) 防重复。

---

## 表：margin_factor（估值因子）

**用途**：安全边际计算的基础原料——每股收益/净资产/分红/股本，**历史报告期逐期累积**（算 5-10 年 PE/PB 分位的前提）。静态数据，财报驱动，季度更新。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| code | VARCHAR | PK 复合, NOT NULL, FK→investable_asset | 标的代码 |
| report_date | DATE | PK 复合, NOT NULL | 报告期（财报截止日） |
| eps | DOUBLE | NULL | 每股收益（元） |
| bps | DOUBLE | NULL | 每股净资产（元） |
| dps | DOUBLE | NULL | 每股分红（元，滚动 12 个月） |
| total_shares | BIGINT | NULL | 总股本（股） |
| float_shares | BIGINT | NULL | 流通股本（股） |

**说明**：因子 + daily_kline（价格）→ PE/PB/股息率（margin_daily）。因子按报告期入库，同一 code 多行=多期历史；最新因子 = 按 report_date 取最新行。

---

## 表：margin_daily（估值日快照）

**用途**：每日盘后计算的 PE/PB/股息率（动态，价格驱动），供安全边际评估与历史分位查询。来源：cron 用 margin_factor 最新因子 + daily_kline 收盘价计算落库。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| code | VARCHAR | PK 复合, NOT NULL, FK→investable_asset | 标的代码 |
| date | DATE | PK 复合, NOT NULL | 交易日 |
| pe | DOUBLE | NULL | 市盈率 = 收盘价 ÷ 最新 EPS |
| pb | DOUBLE | NULL | 市净率 = 收盘价 ÷ 最新 BPS |
| dividend_yield | DOUBLE | NULL | 股息率（%）= DPS ÷ 收盘价 × 100 |

**说明**：**历史分位不单独存储**——由 margin_daily 的历史行直接算（如近 5 年 PE 分位 = 当前 PE 在历史 PE 序列中的百分位），SQL 实时计算。复合主键 (code, date) 防同日重复。

---

## 表：margin_evaluation（安全边际评估记录）

**用途**：**事件表**——每次人工评估落一条（今年评估 100 次 = 100 条记录），冻结评估时点数据供复盘。与 transaction 同哲学（事实留痕）。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INTEGER | PK, NOT NULL | 评估序号 |
| code | VARCHAR | NOT NULL, FK→investable_asset | 标的代码 |
| eval_date | DATE | NOT NULL | 评估日期 |
| price | DOUBLE | NOT NULL | 评估时价格（快照） |
| pe | DOUBLE | NULL | 评估时 PE（快照） |
| pb | DOUBLE | NULL | 评估时 PB（快照） |
| dividend_yield | DOUBLE | NULL | 评估时股息率（快照） |
| pe_percentile | DOUBLE | NULL | 评估时 PE 历史分位（快照） |
| pb_percentile | DOUBLE | NULL | 评估时 PB 历史分位（快照） |
| margin_level | VARCHAR | NOT NULL, CHECK IN ('充足','一般','不足','无边际') | 安全边际结论 |
| discount | DOUBLE | NULL | 折扣率（%） |
| decision | VARCHAR | NULL | 决策：买入/观察/不买 |
| note | VARCHAR | NULL | 评估理由/备注 |
| created_at | TIMESTAMP | DEFAULT now() | 记录时间 |

**说明**：字段为"评估时点快照"（价格会变，记录冻结当时数据）；100 条记录 = 100 个时点，可复盘"当时数据 vs 后来走势"。

---

## 表：margin_macro（宏观基准）

**用途**：全市场共用的无风险利率基准（10 年期国债收益率），尺子A 的基准线——判断"股息率够不够高"（股息率 ≥ 国债 × 1.5 才有讨论价值）。全市场一条，每周更新即可。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| date | DATE | PK, NOT NULL | 日期 |
| cn10y | DOUBLE | NULL | 10 年期国债收益率（%） |

**说明**：无 code 关联（宏观数据不属任何标的）。未来可扩展其他宏观指标（如 LPR、CPI）加列即可。

---

## 表：meta（元信息）

**用途**：库级键值配置，记录各采集任务最后更新时间等。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| key | VARCHAR | PK, NOT NULL | 配置键（如 updated_at） |
| value | VARCHAR | NULL | 配置值（ISO 时间字符串等） |

**约定**：key 命名 `{data_type}_updated_at` 式（如 `kline_updated_at`、`volume_profile_updated_at`、`fund_flow_updated_at`），采集脚本写入时 `INSERT OR REPLACE`。

---

## 变更流程（工程实践）

1. 修改本文档（表/字段说明先行）
2. 修改 `scripts/apply_schema.py`（DDL 与文档同步）
3. 执行：`.venv/bin/python scripts/apply_schema.py`（幂等：仅差异迁移，数据无损）
4. 修改 API（`app/api/__init__.py`）与前端引用
5. 跑验证：`hermes-verify-*`（临时脚本，针对本次变更）
6. git 提交（代码 + 文档一起）
