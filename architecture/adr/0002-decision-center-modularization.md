# ADR-0002: 决策中心子模块拆分

- **Status**: Accepted
- **Date**: 2026-06-16
- **Deciders**: v2.8 决策中心优化（M4）

## Context

`tabs/decision_center.py` 单文件超过 700 行，混合持仓表格、单持仓抽屉、行动收件箱、智能录入、月报等职责，难以独立测试和迭代。

## Decision

1. 保留 `decision_center.py` 为编排入口（`render()`）
2. 拆出 `tabs/decision/` 子包：
   - `holdings_table.py` — 持仓全景
   - `holding_actions.py` — 单持仓 4 sub-tab 抽屉
   - `action_inbox.py` — 行动收件箱
3. 持仓数据仍经 `portfolio/loader` + `holdings_view.build_snapshot`
4. 技术/两融逻辑留在 `dashboard/holdings/`，Tab 只调用

## Consequences

### Positive

- 单文件职责清晰，可针对性改 UI 而不动录入逻辑
- 与 `tabs/company/` 拆包模式一致
- 便于对 `holdings_table` 等写针对性单测

### Negative / Trade-offs

- `decision_center.py` 仍有较多 `sys.path` 注入
- 跨子模块状态仍依赖 `st.session_state`，需文档约定 key

## Alternatives Considered

| 方案 | 优点 | 缺点 | 为何未选 |
|------|------|------|----------|
| 保持单文件 | 无重构成本 | 维护困难 | 文件已过大 |
| 完全独立 Tab 页 | 更解耦 | 破坏「决策中心」一站式体验 | 不符合产品定位 |

## References

- `.tools/dashboard/tabs/decision_center.py`
- `.tools/dashboard/tabs/decision/`
- `architecture/05-dashboard.md`
