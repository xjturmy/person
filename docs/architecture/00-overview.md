# 总体架构

## 一图看懂

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  数据源                                                                       │
│   理杏仁 API   ·   AKShare   ·   本地 CSV   ·   黄金多源(沪金/SPDR/伦敦)     │
└──────────┬───────────────┬─────────────────┬──────────────────┬───────────────┘
           ↓               ↓                 ↓                  ↓
   ┌──────────────────────────────────────────────────────────────────────┐
   │  抓数层  .tools/lixinger-archiver/  ·  .tools/db/fetch_*.py            │
   │   run_full_pipeline / batch_update_* / fetch_akshare / fetch_gold_*   │
   └──────────────────────────────────────┬───────────────────────────────┘
                                          ↓
   ┌──────────────────────────────────────────────────────────────────────┐
   │  数据层  data/*.duckdb  (设计 8 库，现实存 7 — peers 缺失待重建)      │
   │   preson(主财报) · gold · decisions · market · etf · macro · turnover │
   │   · [peers — 待 fetch_peers.py 重建]                                  │
   └──────────────────────────────────────┬───────────────────────────────┘
                                          ↓
   ┌──────────────────────────────────────────────────────────────────────┐
   │  整合层  .tools/data_consolidator/                                    │
   │   consolidate → 02_companies 历史 CSV + 摘要.md                       │
   │   update_pipeline(端到端) · cross_analysis(跨公司对比)                │
   └──────────────────────────────────────┬───────────────────────────────┘
                                          ↓
   ┌──────────────────────────────────────────────────────────────────────┐
   │  Dashboard  .tools/dashboard/app.py                                   │
   │   5 大 Tab · 引擎子包 · 配置读写 · 决策日志                           │
   └────────────┬─────────────────────────────────────────────────────────┘
                ↓
   🌡️ 市场&行业  ·  🔍 选股  ·  🏢 公司研究  ·  💼 决策中心  ·  🥇 黄金
```

## 五层职责

| 层 | 路径 | 职责 | 运行频率 |
|----|------|------|----------|
| 抓数层 | `.tools/lixinger-archiver/` `.tools/db/` | 从外部 API 拉取原始数据 | 日/周/按需 |
| 数据层 | `data/*.duckdb` | 结构化存储，供 Dashboard/MCP 只读查询 | 随抓数更新 |
| 整合层 | `.tools/data_consolidator/` | 公司目录 CSV/摘要生成与跨公司对比 | 抓数后 |
| 展示层 | `.tools/dashboard/` | Streamlit UI + 业务引擎 | 交互式 |
| 配置层 | `.config/` | 持仓、观察池、行业焦点、凭证 | 用户编辑 |

## 旁路系统

| 系统 | 路径 | 说明 |
|------|------|------|
| MCP Server | `.tools/mcp/` | 暴露 `query_metric` 等工具给 Claude，只读 `preson.duckdb` |
| 评分引擎 | `.tools/score/` | 多大师评分，Dashboard 通过 `dashboard_helpers` 调用 |
| 规则库 | `.tools/rules/` | YAML 规则（Graham/Lynch/Buffett/黄金范式等） |
| 知识库 | `01_knowledge/` | 静态方法论与复盘，不参与运行时 |
| 公司档案 | `02_companies/` | 财报 PDF + 基本面 CSV + 决策 Markdown |

## 核心数据流（持仓与决策）

```
.config/portfolio.yaml ──┐
.config/watchlist.yaml ──┼─→ portfolio/loader.py ─→ HoldingsSnapshot ─→ 决策中心 / 公司 Tab
                         │
data/decisions.duckdb ───┴─→ decisions/db.py ────→ 决策日志 + 历史抽屉 + 智能录入
```

## Dashboard 导航模型（v2.7+）

- 左侧 **radio** 5 页，不用顶层 `st.tabs()`
- 跨页跳转：`navigation.goto()` → `st.session_state["nav_intent"]` → 路由层 `peek_intent()`
- 侧边栏 **当前公司** 全局选中，子 Tab 通过 session key 同步

详见 [05-dashboard.md](./05-dashboard.md)、[06-config-and-state.md](./06-config-and-state.md)。
