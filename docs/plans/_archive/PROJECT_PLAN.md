# 📊 preson 项目计划 v2.0

> 状态:历史路线图(2026-05-02 起草的 v1.0→v2.0 蓝图),已归档于 docs/plans/。MVP 四维度均已交付并被 v2.3~v2.9 多轮迭代超越,本文保留作初版决策脉络存档。当前进展见 [PROGRESS.md](PROGRESS.md)。
>
> 个人 A 股基本面投研智能体 — 4 维度 12 任务路线图
>
> **项目期限**：2026-04-23 ~ 2026-12-31（9 个月）
> **当前版本**：v2.0（2026-05-02 改版,从"档案库"升级为"投研智能体"）
> **配套文档**：[PROGRESS.md](PROGRESS.md) 实时进展 | [.claude/memory/project_agent_blueprint.md](.claude/memory/project_agent_blueprint.md) 蓝图记忆

---

## 🎯 项目愿景

打造**专属的、可进化的 A 股基本面投研智能体**:

1. **聚焦** — 只做 A 股基本面,不碰全球市场/加密
2. **专属** — 博采众长形成自己的投资体系,拒绝照搬大师模板
3. **闭环** — 数据 → 工具 → Dashboard → 持仓建议 → 复盘迭代

## 🏗️ 整体架构

```
┌─────────────────────────────────────────────────────┐
│  维度 4:体系层  持仓 + 评分规则 + 月度复盘          │
├─────────────────────────────────────────────────────┤
│  维度 3:交互层  Streamlit Dashboard + 嵌入 Claude   │
├─────────────────────────────────────────────────────┤
│  维度 2:能力层  MCP 工具(query / compare / snapshot)│
├─────────────────────────────────────────────────────┤
│  维度 1:数据层  DuckDB ← 理杏仁 + AkShare           │
└─────────────────────────────────────────────────────┘
```

## 🛤️ 关键路径(MVP 4 步)

跑通这 4 步,蓝图最小可用版本就成型:

```
ingest.py 入库 ──→ query_metric MCP ──→ Streamlit 骨架 ──→ portfolio.yaml
   (维度1🥇)        (维度2🥇)            (维度3🥇)         (维度4🥇)
```

---

## 📐 维度 1:数据层(Data Foundation)

> **目标**:本地 DuckDB 成为唯一数据出口,替代散落 CSV

### 🥇 1.1 schema 设计 + `ingest.py` 入库 `[CRITICAL]` ✅ 完成 (W1)

- 6 张表:`companies`(主表)+ `valuation` / `profitability` / `growth` / `cashflow` / `safety`
- 长表结构:`(ticker, date, metric, value)`
- 全量重建模式(简单可靠)
- DuckDB 文件位置:`data/preson.duckdb`(纳入 `.gitignore`)
- **验收**:`SELECT pe_ttm FROM valuation WHERE ticker='600519' ORDER BY date DESC LIMIT 10;` 能跑通
- **预计**:W1(2026-05-03 ~ 05-09)

### 🥈 1.2 数据校验工具 `validate.py` `[HIGH]` ✅ 完成 (W1, 提前 1 周)

- 检测缺失日期、异常值、重复行
- 输出报告替代 PROGRESS.md 手工跟踪
- 用于驱动 13 家公司数据补齐(副线异步进行)
- **验收**:跑一次能列出每家公司每张表的缺口
- **预计**:W2(2026-05-10 ~ 05-16)

### 🥉 1.3 AkShare 接入 + 增量更新管道 `[HIGH]` ✅ 完成 (W1, 提前 4 周)

- 新增 `prices`(日行情)、`industry_pe`(行业分位)表
- 改造 [.tools/lixinger-archiver/](.tools/lixinger-archiver/) 抓取后自动入库
- `/schedule` 挂周末 cron,每周自动增量
- **验收**:周一打开数据库已更新到上周五
- **预计**:W5(2026-05-31 ~ 06-06)

---

## 🛠️ 维度 2:能力层(Claude 能力扩展)

> **目标**:Claude 不再 grep CSV,改成调 MCP 工具/写 SQL

### 🥇 2.1 MCP server + `query_metric` 工具 `[CRITICAL]`

- Python `mcp` SDK,stdio 模式
- 工具签名:`query_metric(ticker, metric, period="1y")`
- 在 [.claude/settings.json](.claude/settings.json) 注册 mcpServers
- **验收**:对话里说"看下茅台 PE 分位",Claude 直接调工具不读文件
- **预计**:W3(2026-05-17 ~ 05-23)

### 🥈 2.2 `compare_peers` 横向对比工具 `[HIGH]`

- 签名:`compare_peers(tickers, metric, period)`
- 解决最高频需求"X 比 Y 便宜吗"
- **验收**:一句话出 15 家公司任意指标横向对比表
- **预计**:W4(2026-05-24 ~ 05-30)

### 🥉 2.3 `latest_snapshot` 一键摘要工具 `[HIGH]`

- 签名:`latest_snapshot(ticker)` → 返回估值/盈利/成长/现金流/安全性五维快照
- **直接替代手维护的 `摘要.md`**,根除"格式不统一"痛点
- **验收**:CLAUDE.md 删掉"常读 摘要.md"的指引,改为调工具
- **预计**:W4(2026-05-24 ~ 05-30)

---

## 🎨 维度 3:交互层(Dashboard)

> **目标**:浏览器里"看图 + 问 Claude"一体化

### 🥇 3.1 Streamlit 骨架 + DuckDB 直连 `[HIGH]`

- 三个 tab:**首页全景** / **公司详情** / **横向对比**
- 直连 DuckDB(`duckdb.connect('data/preson.duckdb')`)
- 关键图表:估值时间线、PE 分位带、横向对比表
- **验收**:`streamlit run app.py` 能在浏览器打开看到 3 个 tab
- **预计**:W6(2026-06-07 ~ 06-13)

### 🥈 3.2 嵌入 Web 终端跑 Claude Code `[HIGH]`

- 用 `streamlit-terminal` 或 ttyd + iframe 嵌 Web 终端
- 终端内 `claude` 启动,继承全部 MCP 工具/CLAUDE.md/Skills
- **验收**:Streamlit 右栏能直接和 Claude 对话,行为与 CLI 一致
- **预计**:W6 后半

### 🥉 3.3 当前页面上下文自动注入 Claude `[MEDIUM]`

- 选中股票 → 写入临时文件 `.temp/current_context.md`
- Claude 启动时通过 CLAUDE.md hook 自动加载
- **验收**:点茅台 → 在终端问"现在贵不贵",Claude 知道在问茅台
- **预计**:W7(2026-06-14 ~ 06-20)

---

## 🧠 维度 4:体系层(投资进化)

> **目标**:从"博采众长"沉淀出自己的规则

### 🥇 4.1 `.config/portfolio.yaml` 持仓文件 `[HIGH]`

- 字段:`ticker / shares / avg_cost / target_price / thesis / opened_at`
- 加入 `.gitignore`(隐私优先)
- 写一个 MCP 工具 `read_portfolio()`
- **验收**:Claude 能读到当前持仓,基于持仓回答"该减仓吗"
- **预计**:W7(2026-06-14 ~ 06-20)

### 🥈 4.2 大师框架 YAML 化 + 评分引擎 `[MEDIUM]`

- 提炼 [01_knowledge/03_投资策略与选股/](01_knowledge/03_投资策略与选股/) 成 `rules/value.yaml` / `rules/growth.yaml`
- 示例规则:`{condition: "ROE>15% 连续 5 年", score: +2}`
- `score.py` 读规则 + 查 DuckDB → 给每家公司打分
- **验收**:跑一次能输出 15 家公司价值/成长双维度评分
- **预计**:W8(2026-06-21 ~ 06-27)

### 🥉 4.3 月度复盘 prompt 模板 `[MEDIUM]`

- `.claude/prompts/monthly_review.md` 固化"持仓体检"对话
- 内容:持仓估值变化 + 评分变化 + 行业对比 + 操作建议
- 用 `/schedule` 挂月度自动触发
- **验收**:每月 1 号自动跑一次,产出复盘文档
- **预计**:W9(2026-06-28 ~ 07-04)

---

## 📅 6 周路线图(W1 ~ W6 = MVP)

| 周 | 主线(蓝图) | 副线(数据补齐异步) | 里程碑 |
|----|------|------|--------|
| **W1**(5/3-5/9) | 1.1 schema + ingest.py | 修复 batch_update_fs_modules.py 容错 | 数据库可查 |
| **W2**(5/10-5/16) | 1.2 validate.py + 全量入库 | 重抓 13 家剩余财务数据 | 数据库覆盖 ≥ 12 家 |
| **W3**(5/17-5/23) | 2.1 query_metric MCP | 数据补齐收尾 | Claude 会查库 |
| **W4**(5/24-5/30) | 2.2 compare_peers + 2.3 latest_snapshot | — | 三个 MCP 工具齐活 |
| **W5**(5/31-6/6) | 1.3 AkShare 接入 + 周末 cron | — | 自动增量更新 |
| **W6**(6/7-6/13) | 3.1 Streamlit 骨架 + 3.2 嵌入终端 | — | **MVP 上线** 🎉 |

**MVP 完成后(W7+)**:进入维度 4 体系层,边用边迭代。

---

## ✅ MVP 验收标准(2026-06-13 检查)

- [ ] DuckDB 包含 ≥ 12 家公司 10 年完整数据
- [ ] 3 个 MCP 工具在 Claude Code 中可用(query / compare / snapshot)
- [ ] AkShare 行情数据每周自动入库
- [ ] Streamlit Dashboard 三个 tab 可用
- [ ] 浏览器内嵌终端能正常跑 Claude Code

## ✅ 全项目验收标准(2026-12-31)

- [ ] 维度 1-4 全部 12 个任务完成
- [ ] 持仓文件接入,Claude 能给个性化建议
- [ ] 评分引擎对 15 家公司每月跑一次
- [ ] 月度复盘自动产出
- [ ] 至少 3 份基于本系统的投资决策记录(用真实数据驱动)

---

## 🚨 风险与降预期

### 已主动降预期的 3 件事
1. **多智能体协同** → 砍掉,单 Claude + MCP 足够
2. **PDF 研报 RAG** → 推迟到 Phase 3 后(不在本计划内),短期 Tushare 摘要够用
3. **复盘教练自动盈亏归因** → 需 6 个月以上交易记录沉淀,先搭数据结构

### 技术风险
| 风险 | 缓解方案 |
|------|--------|
| 理杏仁 API 不稳定 | validate.py 暴露缺口 + 重试机制 |
| ttyd 嵌入失败 | 降级:VS Code Claude 插件 + 单独跑 Streamlit |
| AkShare 接口变化 | 包一层适配器,接口变化只改一处 |

### 资源依赖

- 理杏仁账号 + Token(已有)
- Tushare Pro(已有)
- Python 3.9+ + DuckDB(待装)
- 本地存储 ≥ 5 GB

---

## 🔧 待用户决定

| 决定 | 选项 | 推荐 | 状态 |
|------|------|------|------|
| DuckDB 文件位置 | `data/` / `.tools/db/` / 项目根 | `data/preson.duckdb` | ✅ 已落地(1.1) |
| 是否纳入 git | 入库 / .gitignore | `.gitignore` | ✅ 已落地(1.1) |
| ingest 模式 | 全量重建 / 增量合并 | 全量重建(首版) | ✅ 已落地(1.1) |
| MCP 协议 | stdio / SSE | stdio | ✅ 已落地(2.1) |

---

## 🔄 版本日志

| 版本 | 日期 | 变更 |
|------|------|------|
| v2.1 | 2026-05-02 | 维度 1 全栈交付(1.1 + 1.2 + 1.3),W1 一次性吃下原 W1+W2+W5;待决项 D1~D4 全部落地 |
| v2.0 | 2026-05-02 | 重构为 4 维度 12 任务,聚焦投研智能体蓝图;旧 v1.0 的"瀑布式"计划被"迭代式"替代 |
| v1.0 | 2026-05-02 | 初版三阶段计划(已废弃,内容并入维度 1 副线"数据补齐") |

---

**下一步**:从维度 1🥇 开始 — 进 plan mode 设计 schema → 写 ingest.py → 用 3 家完整公司验证。
