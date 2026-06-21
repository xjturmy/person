# ADR-0001: 持仓配置迁移至 .config/portfolio.yaml

- **Status**: Accepted
- **Date**: 2026-06-15
- **Deciders**: v2.8 持仓档案重构

## Context

持仓数据原先存放在 `.tools/portfolio/portfolio.yaml`，与代码目录混在一起；v2.7 引入 `positions[]` 段后，持仓逻辑与交易逻辑字段分散在两处，决策中心写入路径不统一。

## Decision

1. 将唯一持仓数据源迁至 `.config/portfolio.yaml`
2. 将 `positions[]` 字段 merge 进 `holdings[]`（school / rationale / criteria_met 等）
3. `portfolio/loader.py` 的 `DEFAULT_YAML` 指向新路径
4. 旧文件 rename 为 `portfolio.yaml.deprecated`，提供 `migrate_to_config.py` 一次性迁移

## Consequences

### Positive

- 配置与代码分离，符合 `.config/` 约定
- 决策中心、公司 Tab、再平衡 planner 统一读 `load_portfolio()`
- 原子写 + `.bak` 备份模式可复用到 watchlist

### Negative / Trade-offs

- 需一次性迁移；历史 `.tools/portfolio/portfolio.yaml` 引用需全局搜索更新
- YAML schema 变大，loader 需维护更多可选字段

## Alternatives Considered

| 方案 | 优点 | 缺点 | 为何未选 |
|------|------|------|----------|
| 继续放 .tools/portfolio/ | 无迁移成本 | 配置代码混杂 | 不符合项目分层 |
| 改用 DuckDB 存持仓 | 查询方便 | Dashboard 需写主库，与 read-only 冲突 | 过度设计 |

## References

- `.tools/portfolio/loader.py`
- `architecture/06-config-and-state.md`
