# 架构决策记录（ADR）

本目录记录重大架构决策，便于后续修改时理解「为什么这样设计」。

## 何时写 ADR

- 新增 DuckDB 或改变表结构
- 变更配置 schema（portfolio / watchlist）
- 拆分/合并 Tab 或引擎模块
- 引入新数据源或废弃旧数据源
- 改变读写约定或缓存策略

## 命名

```
NNNN-简短英文标题.md
```

例：`0001-portfolio-config-migration.md`

## 流程

1. 复制 `0000-template.md`
2. 填写上下文、决策、后果
3. 在 PR/提交说明中引用 ADR 编号
4. 若决策被推翻，不删除旧 ADR — 标记 Status: Superseded by NNNN

## 索引

| ADR | 标题 | 状态 |
|-----|------|------|
| [0001](./0001-portfolio-config-migration.md) | 持仓配置迁移至 .config/portfolio.yaml | Accepted |
| [0002](./0002-decision-center-modularization.md) | 决策中心子模块拆分 | Accepted |
| [0003](./0003-dashboard-investment-flow.md) | Dashboard 投资流程流水线重构 | Proposed |
