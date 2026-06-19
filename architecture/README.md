# preson 架构设计

> 个人投研工作台 — 数据抓取 + 整合 + Streamlit Dashboard + 决策日志
>
> **版本基准**：v2.8（2026-06-18）  
> **用途**：后续所有功能修改、重构、新模块开发，均以此文件夹为设计基准。

---

## 如何使用本文件夹

1. **改功能前**：先读对应层的文档，确认模块边界与数据流
2. **跨层改动**：从 `00-overview.md` 出发，检查上下游影响
3. **重大决策**：在 `adr/` 下新增 ADR（Architecture Decision Record）
4. **文档同步**：代码变更涉及架构时，同步更新对应 `.md`

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [00-overview.md](./00-overview.md) | 一图看懂：五层架构 + 数据流向 |
| [01-directory-layout.md](./01-directory-layout.md) | 顶层目录约定与职责边界 |
| [02-data-layer.md](./02-data-layer.md) | DuckDB 集群：表结构、读写方、约定 |
| [03-fetch-layer.md](./03-fetch-layer.md) | 抓数层：数据源、脚本、编排 |
| [04-consolidation-layer.md](./04-consolidation-layer.md) | 整合层：CSV → 摘要/历史数据 |
| [05-dashboard.md](./05-dashboard.md) | Dashboard：Tab 路由、引擎、子模块 |
| [10-dashboard-investment-flow-plan.md](./10-dashboard-investment-flow-plan.md) | v2.9 子单元规范（末格确定） |
| [11-dashboard-data-funnel.md](./11-dashboard-data-funnel.md) | **v2.9 数据漏斗**：跨导航共享、层次递进、组内删除 |
| [12-dashboard-v2.9-design-scheme.md](./12-dashboard-v2.9-design-scheme.md) | **v2.9 完整设计方案**（五导航详表 + 实施分期） |
| [06-config-and-state.md](./06-config-and-state.md) | 配置、持仓、观察池、导航、session |
| [07-engines-reference.md](./07-engines-reference.md) | 引擎模块速查（gold/masters/valuation…） |
| [08-conventions.md](./08-conventions.md) | 关键约定：读写锁、ticker、缓存、港股 |
| [09-testing.md](./09-testing.md) | 测试布局与运行方式 |
| [adr/](./adr/) | 架构决策记录（ADR） |

---

## 架构分层（速记）

```
数据源 → 抓数层 → 数据层(DuckDB) → 整合层 → Dashboard → 用户
                ↘ 02_companies CSV ↗              ↘ MCP/Claude
```

**静态资料**（`01_knowledge/`、`02_companies/` 财报/研报）不参与运行时，但 Dashboard 会读取部分 Markdown。

---

## 维护记录

| 日期 | 变更 |
|------|------|
| 2026-06-18 | v2.9 数据漏斗文档（11/12）：跨导航共享、层次递进、warn_only 删除 |
| 2026-06-18 | v2.9 子单元规范：5 导航各 3～4 格，末格必为确定 |
| 2026-06-18 | 迁入 `docs/` 目录；v2.8 决策中心拆分、portfolio 迁移、navigation/watchlist |
