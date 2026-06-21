# 引擎模块速查

Dashboard 业务逻辑分布在 `dashboard/` 子包与 `.tools/` 平级模块。  
原则：**引擎无 UI 依赖**（计算/查询），Tab 负责 `st.*` 渲染。

## gold/ — 黄金引擎

| 模块 | 职责 |
|------|------|
| `paradigm.py` | 范式投票（多指标 YAML 规则） |
| `overheat.py` | 短期过热扫描 + `--backfill` |
| `backtest.py` | 历史回看 |
| `beta.py` | 黄金股弹性 |
| `data.py` | gold.duckdb 访问层 |

规则：`.tools/rules/gold_paradigm.yaml` / `gold_overheat.yaml`

## masters/ — 大师方法论

| 子包 | 职责 |
|------|------|
| `graham/` | steps + peer_radar + schloss + extras + router |
| `lynch/` | classifier + scorer + extras |
| `buffett/` | v2 分类自适应评分 + `dim_formulas.yaml` |
| `philosophy.py` | 投资哲学展示 |

规则：`.tools/rules/graham*.yaml` / `lynch.yaml` / `buffett.yaml`

UI Tab：`tabs/lynch_analysis/`（step1–6 分步）

## valuation/ — 估值

| 模块 | 职责 |
|------|------|
| `fair_price.py` | Graham 5 档公允价 |
| `price_range.py` | 三模型加权价格走廊 |
| `peg_curve.py` | PEG 曲线 |
| `derived_metrics.py` | 派生指标 |

## industry/ — 行业

| 模块 | 职责 |
|------|------|
| `percentile_engine.py` | 行业分位计算 |
| `percentile.py` | 分位展示 helper |
| `screener.py` | 行业筛选 |
| `compare_view.py` | 行业横评 B2/B3 |
| `gm_static.py` | 毛利率静态基准 |

读取：`03_macro/` 行业对标 + `industry_master.yaml`

## peers/ — 同行

| 模块 | 职责 |
|------|------|
| `radar.py` | 同行雷达图 |
| `timeline.py` | 决策时间线 |
| `advisor.py` | 同行建议 |

数据：`peers.duckdb` via `fetch_peers.py`

## screening/ — 选股

| 模块 | 职责 |
|------|------|
| `screener.py` | 多维筛选 |
| `etf_recommender.py` | ETF 推荐 |

数据：`market.duckdb` + `preson.duckdb`

## holdings/ — 持仓扩展

| 模块 | 职责 |
|------|------|
| `trade_ledger.py` | 决策 → 交易级账本 |
| `technicals.py` | MA / RSI / MACD |
| `margin.py` | 两融数据 |

## portfolio/ — 持仓服务（`.tools/portfolio/`）

| 模块 | 职责 |
|------|------|
| `loader.py` | YAML → HoldingsSnapshot |
| `holdings_view.py` | 快照构建 + 权重/deviation |
| `rebalance_planner.py` | 再平衡提案 |
| `parse_holdings.py` / `parse_screenshot.py` | 智能录入 |
| `spot_price.py` | 现价查询 |
| `report.py` / `send_monthly_email.py` | 月报 |

## score/ — 评分引擎（`.tools/score/`）

| 模块 | 职责 |
|------|------|
| `engine.py` | 单大师评分 |
| `multi_master.py` | 多大师矩阵 |

Dashboard 通过 `dashboard_helpers.company_score()` 桥接。

## mcp/ — Claude 工具（`.tools/mcp/`）

| 工具 | 说明 |
|------|------|
| `query_metric` | 单指标时间序列 |
| `valuation_percentile` | 分位排名 |
| `compare_peers` | 跨公司对比 |
| `latest_snapshot` | 最新快照 |

映射：`metric_map.yaml` / `ticker_map.yaml`

## rules/ — 规则库

YAML 驱动的可配置规则，引擎运行时加载。  
修改规则 **不需要** 改 Python（除非新增规则类型）。

## 依赖关系简图

```
rules/*.yaml
     ↓
masters/ · gold/ · valuation/ · score/
     ↓
dashboard_helpers.py  ←→  preson.duckdb / peers.duckdb / gold.duckdb
     ↓
tabs/*  (Streamlit UI)
```
