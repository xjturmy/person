# ADR-0003: Dashboard 投资流程流水线重构

- **Status**: Accepted（部分实施 — 2026-06-28 进度：P0 市场&行业 + P1 选股已落地，`funnel/` 模块已建；P2 公司研究 / P3 决策中心 / P4 黄金 待实施）
- **Date**: 2026-06-18（决策）/ 2026-06-28（实施进度更新）
- **Deciders**: 用户拍板（架构文档先行）

## Context

v2.7–v2.8 Dashboard 以 5 个顶级 Tab 并列呈现功能，子页面之间**决策顺序**不清晰，且缺少统一的「确定落盘」检查点。用户要求：

1. 每个顶级导航下设 **3～4 个小单元**
2. **最后一个单元必须是「确定」**，基于本导航前序分析/筛选结果落盘
3. 行业、选股、公司研究、决策中心、黄金全覆盖

## Decision

采用「投资流水线 + 子单元规范」：**5 个顶级 Tab 各 4 个 sub-tab，末格必为确定**：

| 顶级 Tab | sub-tab | 末格写入 |
|----------|---------|----------|
| 🌡️ 市场 & 行业 | 市场研判 · 行业分析 · 行业预选 · **行业确定** | `focus_industries.yaml` |
| 🔍 选股 | 初步筛选 · 林奇选股 · 格雷厄姆选股 · **选股确定** | `watchlist.yaml` |
| 🏢 公司研究 | 公司研判 · 林奇分析 · 格雷厄姆分析 · **持仓确定** | `portfolio.yaml` + `decisions.duckdb` |
| 💼 决策中心 | 持仓检视 · 行动建议 · 决策录入 · **决策确定** | `portfolio.yaml` + `decisions.duckdb` |
| 🥇 黄金 | 范式研判 · 过热回溯 · ETF与杠杆 · **黄金确定** | `portfolio` 黄金配置段 |

前序小单元只读或 session 草稿；**仅末格写持久化**。

### 数据漏斗与删除策略（补充）

跨导航通过 **持久化链** 层次递进缩小范围：

```
focus_industries.yaml → (推导股票池) → watchlist.yaml → portfolio.yaml → decisions.duckdb
```

- L1 行业确定 **不存股票**；股票池由 `companies.csv` + `industry_master` + `industry_screener` 运行时展开
- 删行业时采用 **warn_only**：仅警告 watchlist 孤立股，**不自动级联删除**

详见 [11-dashboard-data-funnel.md](../11-dashboard-data-funnel.md) · [12-dashboard-v2.9-design-scheme.md](../12-dashboard-v2.9-design-scheme.md)。

## Consequences

### Positive

- 决策路径与知识库「宏观 → 行业 → 选股 → 公司 → 持仓」一致
- 每步有可确认检查点，减少跳步建仓
- 复用现有引擎（lynch/graham/screener/watchlist/loader），以 Tab 编排为主

### Negative / Trade-offs

- sub-tab 数量增加，需用 `navigation.goto` 串联避免用户迷航
- `industry_focus.py` / `screener.py` 需拆包，短期并行维护成本
- 5 个导航结构统一，用户形成「分析→确定」肌肉记忆
- 黄金/决策中心纳入同一规范，不再例外

## Alternatives Considered

| 方案 | 优点 | 缺点 | 为何未选 |
|------|------|------|----------|
| 新增顶级 Tab「投资流程」 | 流程感最强 | 6 个顶级 Tab，与 v2.7 简化导航冲突 | 破坏现有 5 Tab 结构 |
| 仅用决策中心承载确认 | 改动小 | 研究与持仓脱节 | 不符合「研究完再定仓」 |
| 保持单页 screener | 无拆包 | 林奇/格雷厄姆无法深展 | 不满足用户需求 |

## References

- [12-dashboard-v2.9-design-scheme.md](../12-dashboard-v2.9-design-scheme.md)
- [11-dashboard-data-funnel.md](../11-dashboard-data-funnel.md)
- [10-dashboard-investment-flow-plan.md](../10-dashboard-investment-flow-plan.md)
- `.tools/dashboard/tabs/industry/`（P0 落地；旧 `industry_focus.py` 降级 legacy）
- `.tools/dashboard/tabs/screener/`（P1 落地；旧入口 `screener_legacy.py`）
- `.tools/dashboard/funnel/`（漏斗模块 layers/orphans/session）
- `.tools/dashboard/app.py`
