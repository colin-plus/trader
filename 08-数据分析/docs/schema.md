# 数据模型规范（Schema 权威文档）

> 观澜（TideScope）数据层设计文档。数据库实现见 `scripts/apply_schema.py`（幂等重建）。
> 变更表结构时：**先改本文档 → 再改 apply_schema.py → 执行迁移**，保持文档与实现同步。

## 总体设计

```
investable_asset（标的主数据）
  ├── watchlist        关注标的（用户关系）
  ├── daily_kline      日线行情（1 标的 : N 日）
  ├── volume_profile   分价分布（1 标的 : N 日 : N 价格档）
  ├── fund_flow        资金流向（1 标的 : N 日）
  └── finance          财务数据（1 标的 : N 报告期 × kind）
meta                    库级元信息（更新时间等）
```

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

## 表：fund_flow（资金流向）

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

**用途**：财务/分红等非行情数据，财务页数据源。来源：东财 F10。**宽表 + kind 分类**——新指标加新 kind 不用改表结构。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| code | VARCHAR | PK 复合, NOT NULL, FK→investable_asset | 标的代码 |
| report_date | DATE | PK 复合, NOT NULL | 报告期（分红除权日 / 财报截止日） |
| kind | VARCHAR | PK 复合, NOT NULL, CHECK IN ('dividend','income','balance') | 数据类型 |
| payload | JSON | NOT NULL | 该 kind 的具体字段（结构见下） |

**kind 与 payload 约定**：

| kind | report_date 含义 | payload 结构 |
|---|---|---|
| dividend | 除权除息日 | `{"cash_per_share": 每10股派现金(元), "plan": "10派2.5", "record_date": "股权登记日", "ex_date": "除权日", "pay_date": "派息日"}` |
| income | 报告期截止日 | `{"revenue": 营收, "net_profit": 净利, "roe": 净资产收益率, "eps": 每股收益, ...}` |
| balance | 报告期截止日 | `{"assets": 总资产, "liabilities": 总负债, "equity": 净资产, ...}` |

**说明**：JSON payload 的取舍——个人工具灵活性优先（新指标不加列），代价是库内不保证字段完整性，由采集脚本校验。复合主键 (code, report_date, kind) 防重复。

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
