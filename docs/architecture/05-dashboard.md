# Dashboard 层

入口：`.tools/dashboard/app.py`  
启动：`streamlit run .tools/dashboard/app.py`

## 架构分层（Dashboard 内部）

```
app.py                    # 路由 + 侧边栏 + 全局状态
    ├── dashboard_helpers.py   # 数据访问 + 渲染 helper（从 app 抽出）
    ├── navigation.py          # 跨 Tab 跳转
    ├── state.py               # 行业焦点 session
    ├── watchlist.py           # 观察池
    └── tabs/                  # 页面
            ├── market/        # 市场周期
            ├── industry/      # v2.9：analysis / preselect / confirm（旧 industry_focus.py 降级 legacy）
            ├── screener/      # v2.9：prelim / lynch_pick / graham_pick / confirm（旧入口 screener_legacy.py）
            ├── company/       # 公司研究（已拆包，仍 v2.8 4-tab 结构）
            ├── decision_center.py + decision/
            ├── gold_analysis.py + gold_analysis/   # 仍 v2.8 多 sub-tab，待 P4 收敛
            └── lynch_analysis/ 等大师 Tab
    └── funnel/                # v2.9 漏斗：layers / orphans / session
```

## 五大顶级页面（v2.9 子单元，每导航 3～4 格、**末格=确定**）

| 常量 | 标签 | 子单元 | 落地状态 |
|------|------|--------|----------|
| `PAGE_MARKET_HUB` | 🌡️ 市场 & 行业 | 市场研判 · 行业分析 · 行业预选 · **行业确定** | ✅ 已落地（`tabs/industry/`） |
| `PAGE_SCREENER` | 🔍 选股 | 初步筛选 · 林奇选股 · 格雷厄姆选股 · **选股确定** | ✅ 已落地（`tabs/screener/`） |
| `PAGE_COMPANY` | 🏢 公司研究 | 概览 · 林奇 · 格雷厄姆 · 芒格 | ⏳ 仍 v2.8 4-tab；目标改为 公司研判·林奇·格雷厄姆·**持仓确定**（P2） |
| `PAGE_GOLD` | 🥇 黄金 | 多个 sub-tab（范式/指标/过热/回溯/ETF/杠杆/持仓建议） | ⏳ 仍 v2.8；目标收敛为 4 格末格 **黄金确定**（P4） |
| `PAGE_DC` | 💼 决策中心 | 持仓总览 · 持仓跟踪 · 决策日志 · 月报历史 | ⏳ 仍 v2.8 4 段；目标改为 持仓检视·行动建议·决策录入·**决策确定**（P3） |

> **v2.9 子单元规范**：详见 [12-dashboard-v2.9-design-scheme.md](./12-dashboard-v2.9-design-scheme.md) · [11-dashboard-data-funnel.md](./11-dashboard-data-funnel.md)。  
> 原则：先分析 → 再选择 → **末格确定落盘**；跨导航 **层次递进漏斗**（全市场 → 行业 → 股票 → 持仓）。  
> **进度**：市场&行业、选股两导航（P0+P1）已落地 4-subtab + `funnel/`；公司研究、决策中心、黄金（P2–P4）仍为 v2.8 结构。

## 数据漏斗（v2.9 摘要）

跨导航共享通过 **持久化 YAML 链** + **会话草稿** + **`navigation.goto`** 实现：

```
focus_industries.yaml → (推导股票池) → watchlist.yaml → portfolio.yaml → decisions.duckdb
```

- L1 行业确定不存股票；股票池由 `companies.csv` + `industry_master` + `industry_screener` 运行时展开
- 每层确定页支持 **本层删除**；删行业时 **仅警告** watchlist 孤立股，不自动级联删

详见 [11-dashboard-data-funnel.md](./11-dashboard-data-funnel.md)。

路由：`st.sidebar` radio → `if page == PAGE_*` 分发（**不用**顶层 `st.tabs()`）

## 公司研究 Tab（`tabs/company/`）

拆包结构（原单文件 `tabs/company.py`）：

| 模块 | 职责 |
|------|------|
| `hero.py` | SWS Hero + 持仓卡 + 健康度 + 五维 + Piotroski |
| `block_a.py` | 看结论：雪花图 + 同行业建议 |
| `block_b.py` | 大师评分矩阵 + 投票 + 同行雷达 |
| `block_c.py` | 数据深挖：6 维 sub-tab + K 线 + ETF |
| `block_d.py` | 决策档案：时间线 + 研报/财报 |
| `_helpers.py` | 共享 helper |

`render(app_globals)` 将 `app.py` 的 `globals()` 注入各子模块（兼容原单文件模式）。

## 决策中心（v2.8 重构）

主文件：`tabs/decision_center.py`

子模块（`tabs/decision/`）：

| 模块 | 职责 |
|------|------|
| `holdings_table.py` | 持仓全景表格 |
| `holding_actions.py` | 单持仓抽屉（4 sub-tab） |
| `holding_tracker.py` | 单股决策卡片视图（持仓跟踪 sub-tab） |
| `holding_guide.py` | 持仓操作指引 |
| `action_inbox.py` | 行动收件箱 |

数据依赖：
- `portfolio/loader.py` → `HoldingsSnapshot`
- `decisions/db.py` → 决策日志 CRUD
- `holdings/trade_ledger.py` → 交易级账本
- `holdings/technicals.py` → MA/RSI/MACD
- `holdings/margin.py` → 两融

## 侧边栏全局状态

| 组件 | key / 机制 | 说明 |
|------|------------|------|
| 页面选择 | `nav` (radio) | 5 大 Tab |
| 当前公司 | `company` (selectbox) | 全局公司上下文 |
| 公司搜索 | `company_search_query` | 代码/拼音/行业 |
| 子 Tab 同步 | `lynch_company` 等 | sidebar 变更时强制写入 |
| 跨页跳转 | `nav_intent` | `navigation.goto()` |

上下文写出：`.temp/current_context.md`（供 Claude 终端会话锚定公司）

## 数据访问

`dashboard_helpers.py` 统一：
- `_duckdb_conn()` — read-only 连接 preson.duckdb
- `load_metric()` / `load_prices()` — 指标与价格
- `_db_mtime()` — 缓存 key
- MCP 桥接：`mcp_percentile()` / `mcp_freshness()`
- 评分：`company_score()` / `master_score()`

失败回退：DuckDB 不可用时读 `02_companies/*/历史数据/*.csv`

## 引擎子包（业务逻辑）

详见 [07-engines-reference.md](./07-engines-reference.md)。

引擎与 Tab 的关系：**Tab 负责编排与展示，引擎负责计算，不直接操作 Streamlit**（少数历史模块例外）。

## 修改指南

| 要改… | 先读… | 注意 |
|-------|-------|------|
| 新 Tab | `app.py` 路由 + `navigation.py` 常量 | PAGE_* 两处必须一致 |
| 公司页区块 | `tabs/company/block_*.py` | 通过 `app_globals` 注入 |
| 决策中心 | `decision_center.py` + `decision/` | 持仓写 `.config/portfolio.yaml` |
| 跨页链接 | `navigation.goto(page, company=, sub_tab=)` | 目标页 `consume_intent()` |
| 缓存 | `@st.cache_data` + `_db_mtime` | 写 DB 后需清缓存或等 mtime 变 |
