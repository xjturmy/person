# 数据层 — DuckDB 集群

路径：`data/*.duckdb`

> **现状（2026-06-28）**：设计上 8 个库，`data/` 目前实存 **7 个**。
> **`peers.duckdb` 缺失** —— 代码仍引用（peers 雷达、行业横评、graham peer_radar 等），需跑
> `python .tools/db/fetch_peers.py` 重建。其余 7 库（preson / gold / decisions / market / etf / macro / turnover）齐全。

## 数据库一览

| DB | 核心表 | 写入方 | 读取方 |
|----|--------|--------|--------|
| `preson.duckdb` | valuation / profitability / growth / safety / cashflow / prices / companies / macro | `db/ingest.py` 全量重建；`fetch_akshare` 增量价 | masters / valuation / screening / industry / MCP |
| `gold.duckdb` | gold_paradigm_history / gold_overheat_history / gold_etf_metrics / gold_metrics | `gold/paradigm.py --write`；`gold/overheat.py` | 🥇 黄金 Tab |
| `decisions.duckdb` | decisions | 决策中心 UI、`decisions/db.py` | 决策中心 / 公司 block_d |
| `peers.duckdb` ⚠️缺失 | peers / self_metrics | `db/fetch_peers.py`（重建） | peers 引擎 / 同行雷达 |
| `market.duckdb` | L1 全 A 快照 | `db/fetch_market_spot.py` | 选股 Tab |
| `etf.duckdb` | ETF 行情 + 份额 | `db/fetch_etf*.py` | ETF 对标叠加图 |
| `macro.duckdb` | 宏观指标 | `db/fetch_macro.py` | 市场温度计 |
| `turnover.duckdb` | 周转/应收/存货 | `db/fetch_turnover.py`（派生） | Lynch 财务护栏 |

## preson.duckdb 表结构（主库）

由 `db/ingest.py` 定义，从 `02_companies/*/历史数据/*.csv` melt 后写入：

| 源 CSV | 表名 | 主键 |
|--------|------|------|
| 估值.csv | valuation | (ticker, date, metric) |
| 盈利.csv | profitability | (ticker, date, metric) |
| 成长.csv | growth | (ticker, date, metric) |
| 现金流.csv | cashflow | (ticker, date, metric) |
| 安全性.csv | safety | (ticker, date, metric) |
| — | prices | (ticker, date) |
| companies.csv | companies | ticker |

长表模式：`(ticker, date, metric, value)`，便于分位查询与跨指标 pivot。

## decisions.duckdb 设计要点

- **独立文件**：与 `preson.duckdb` 解耦，避免 MCP/Dashboard 只读锁与写入冲突
- **capture-on-write**：扁平快照字段 + `snapshot_json` 完整 JSON
- **关键字段**：rationale / thesis_5y / risks + snapshot_pe / pe_pct / fscore 等

实现：`.tools/decisions/db.py`

## 读写约定

| 角色 | 连接模式 | 说明 |
|------|----------|------|
| Dashboard | read-only | `_duckdb_conn(read_only=True)` |
| MCP Server | read-only | 4 类错误码 + freshness 4 档 |
| 抓数/ingest | 独占写 | 完成后释放；WAL 模式 |
| decisions CRUD | 读写 | 独立库，不影响主库 |

## 缓存失效

Dashboard 使用 `@st.cache_data`，cache key 含 `_db_mtime()`：

- DuckDB 文件 mtime 变化 → 缓存自动失效
- 配合周日 `db/update.py` cron 增量更新

## ingest 流程

```
.config/companies.csv
        ↓
02_companies/{folder}/01_基本面数据/历史数据/*.csv
        ↓
db/ingest.py  (--only 可选过滤)
        ↓
data/preson.duckdb  (DROP + CREATE + INSERT)
```
