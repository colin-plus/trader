# 观澜（TideScope）

> 透过数据，观市场之澜。—— 个人交易数据抓取、分析、展示平台

股票数据仓库 + 可视化仪表盘。独立于知识库文档体系的数据层项目。

## 架构

```
采集层（cron/脚本）→ 存储层（duckdb）→ 展示层（FastAPI + Vite + ECharts）
```

- **存储**：duckdb 单文件数据库（`data/trader.duckdb`，gitignore 不入库）
- **后端**：FastAPI（`app/`），提供 /api/kline /api/fenjia /api/fflow 等接口
- **前端**：Vite + Vue3 + Arco Design Vue + ECharts + Lucide（`web/`），前后端分离开发
- **采集**：`scripts/`，从东财/腾讯拉数据落 duckdb（沿用 cron 采集管道）

## 目录结构

```
08-数据分析/
├── app/          FastAPI 后端源码
│   ├── main.py   启动入口
│   ├── db.py     duckdb 连接/查询封装
│   └── api/      路由
├── web/          前端源码（Vue3 + Arco + ECharts）
├── scripts/      数据采集/导入脚本
├── data/         duckdb 数据库文件（gitignore）
└── .gitignore    数据库/venv/构建产物不入 git
```

## 快速开始

```bash
# 后端
cd 08-数据分析
.venv/bin/uvicorn app.main:app --reload --port 8000

# 前端（另开终端）
cd web
npm install
npm run dev        # http://localhost:5174，代理 /api 到 8000
```

## 数据表

| 表 | 内容 | 来源 |
|---|---|---|
| investable_asset | 标的主数据（股票/ETF：代码/名称/类型/交易所/行业） | 手动维护 |
| watchlist | 关注标的（加入时间/备注/排序/启用） | 手动维护 |
| daily_kline | 日线行情（开高低收/量） | 腾讯 fqkline |
| price_distribution | 分价分布（日期+价格+手数+BS） | 东财分时聚合 |
| fund_flow | 资金流向（主力/超大单/大单/中单/小单） | 东财 fflow |
| finance | 财务数据（kind: dividend/income/balance + JSON payload） | 东财 F10 |
| meta | 元信息（更新时间等） | 采集脚本 |

## 数据模型约定

- **主键策略**：自然键——`code` 直接做主键（A股代码全局唯一）
- **数据表复合主键**：daily_kline/fund_flow `(code, date)`；price_distribution `(code, date, price)`
- **外键**：所有数据表 `code REFERENCES investable_asset(code)`
- **读写分离（单写者模型）**：后端 FastAPI 只读连接；写操作由采集脚本独占执行（避免争写锁）
