# 配置、状态与导航

## 配置文件

### portfolio.yaml（v2.8+ 唯一持仓源）

路径：`.config/portfolio.yaml`  
API：`.tools/portfolio/loader.py`

```python
from portfolio.loader import load_portfolio
p = load_portfolio()
p.holdings          # list[Holding]
p.active()          # status=active
p.weight_of("600519")
```

**迁移说明**：旧路径 `.tools/portfolio/portfolio.yaml` 已 deprecated；`positions[]` 字段已 merge 进 `holdings[]`。

`Holding` 关键字段：
- 交易：ticker / shares / cost_basis / status (active|watch|exited)
- 配置：target_weight / max_weight / price_band
- 逻辑：thesis / school / rationale / criteria_met / review_triggers

写操作：`upsert_holdings()` — 决策中心智能录入、再平衡应用

### watchlist.yaml

路径：`.config/watchlist.yaml`  
API：`.tools/dashboard/watchlist.py`

```python
WatchlistEntry(ticker, name, added_at, preset, score, rating, status, notes)
```

- 替代旧 `.temp/watchlist.md`
- 原子写 + `.bak` 备份
- `status`: pending | closed

### 行业焦点

| 文件 | API |
|------|-----|
| `.config/focus_industries.yaml` | `state.py`: add_focus / remove_focus |
| `.config/industry_master.yaml` | `state.py`: industry_master() / l2_under_l1() |

`state.py` 还管理 `st.session_state.sel_l1 / sel_l2`（跨 Tab 行业选中）。

### companies.csv

```csv
folder,stock,name,category
01_新华保险,601336,新华保险,保险
```

- 抓数、ingest、搜索索引、决策中心 universe 均依赖此文件
- ticker 与 folder 映射的唯一清单

## 导航协议（navigation.py）

```python
from navigation import goto, consume_intent, peek_intent
from navigation import PAGE_COMPANY, PAGE_DC  # 等

goto(PAGE_COMPANY, company="06_贵州茅台", sub_tab="林奇")
```

流程：
1. 调用方 `goto()` → 写入 `st.session_state["nav_intent"]` → `st.rerun()`
2. `app.py` 路由层 `peek_intent()` 覆盖 page/company（selectbox 渲染前）
3. 目标 Tab 入口 `consume_intent()` 清空并应用 sub_tab/focus/prefill

**约束**：`PAGE_*` 常量值必须与 `app.py` 中 emoji+中文标签完全一致。

## Session State 约定

| Key | 用途 |
|-----|------|
| `nav` | 当前顶级页面 |
| `company` | 侧边栏选中公司 folder |
| `nav_intent` | 跨页跳转意图（临时） |
| `sel_l1` / `sel_l2` | 行业分析选中 |
| `_last_sidebar_company` | 检测 sidebar 公司变更 |
| `lynch_company` / `graham_company` / … | 子 Tab 公司同步 |

## 决策日志

路径：`data/decisions.duckdb`  
模块：`.tools/decisions/db.py` + `snapshot.py`

写入时机：决策中心录入 → `insert()` + 自动 snapshot  
读取：决策列表、公司 block_d 时间线、peers timeline

## 临时上下文

| 文件 | 写入方 | 用途 |
|------|--------|------|
| `.temp/current_context.md` | `write_context()` | Claude 锚定当前公司 |
| `.temp/dashboard_inbox.md` | 外部/脚本 | 侧边栏收件箱 |
| `.temp/validate_report.md` | `db/validate.py` | 数据质量报告 |
