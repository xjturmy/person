# 抓数层

## 数据源与入口

| 数据源 | 入口脚本 | 频率 |
|--------|----------|------|
| 理杏仁（估值/财务） | `lixinger-archiver/run_full_pipeline.py` | 周末 + 按需 |
| 理杏仁（估值宽表） | `lixinger-archiver/batch_update_recent_wide.py` | 快速日更 |
| 理杏仁（财务模块） | `lixinger-archiver/batch_update_fs_modules.py` | 季度 |
| AkShare（日 K + 行业 PE） | `db/fetch_akshare.py` | 每日 |
| 黄金多源 | `db/fetch_gold_prices.py` 等 6 个 | 每日 |
| 同行对标 | `db/fetch_peers.py` | 周末 |
| L1 全 A 市场 | `db/fetch_market_spot.py` | 每日（~13min，可 skip） |
| 宏观 | `db/fetch_macro.py` | 按需 |
| ETF | `db/fetch_etf.py` / `fetch_gold_etf*.py` | 按需 |
| 周转率派生 | `db/fetch_turnover.py` | 季度 |

## 周末编排入口

```bash
python .tools/db/update.py
```

管道顺序（`db/update.py`）：

1. `fetch_akshare` — 日 K 增量
2. `ingest.py` — 全量重建 preson.duckdb
3. `validate.py` — 数据质量检查
4. `fetch_peers` — 同行池刷新（失败仅 warning）
5. 黄金模块（prices / real_rate / ETF / ratios）— 可 `--skip-gold`
6. `fetch_market_spot` — 可 `--skip-market-spot`
7. gold paradigm / overheat 快照

退出码：`0`=OK，`1`=validate critical，`2`=akshare/ingest 失败

## 理杏仁管道

```
.config/companies.csv + credentials.md (token)
        ↓
run_full_pipeline.py
        ↓
02_companies/{公司}/01_基本面数据/01_估值分析/ … 05_安全性分析/
        ↓
(可选) data_consolidator/consolidate.py → 历史数据/*.csv + 摘要.md
        ↓
db/ingest.py → preson.duckdb
```

## Token 获取

- 从 `.config/credentials.md` 自动解析（`lixinger_resolve_token.py`）
- 不出 git、不在日志打印

## 与整合层的关系

理杏仁脚本写入 **原始分目录**（`01_估值分析/` 等）；  
`consolidate.py` 合并为 **历史数据/*.csv**；  
`ingest.py` 再导入 DuckDB。

一键编排：`.tools/data_consolidator/update_pipeline.py`
