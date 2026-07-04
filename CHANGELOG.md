# 更新日志 · preson

> 全系统唯一权威版本号见根目录 [`VERSION`](./VERSION)。
> 本文件与 [`docs/plans/PROGRESS.md`](./docs/plans/PROGRESS.md) 是 1.0 之后仅有的两个**活文档**，其余文档一律「带日期 + 冻结」。
> 格式参考 [Keep a Changelog](https://keepachangelog.com/)。

---

## [1.1] - 2026-07-04

个人投资判断工作台阶段版本。系统方向从“继续增加展示与页面”收敛为“帮助个人判断方法是否用对、当前价格是否合理、操作是否克制、后续是否可复盘”。

### 本次重点

- **个人投资判断方向校准**：新增 `docs/dashboard/PERSONAL_INVESTMENT_README.md`，明确后续优化优先级：少做花哨展示，多做结论、约束、操作校验与复盘。
- **林奇投资法最终判断**：将林奇价格区间放到最后综合判断中，按林奇六类公司分别给出 PEG / 股息率 / PB / PE 等方法内价格锚，避免被其它估值方法污染。
- **公司研究与金融公司分析增强**：补入保险公司相关指标、页面入口与展示能力，增强金融行业个股判断的适配度。
- **格雷厄姆 / 芒格 / 同行对标体验修正**：围绕个人判断场景改进页面输出、同业雷达与方法页结论。
- **数据与抓取**：新增保险指标抓取与入库相关脚本/数据，补充新华保险、中国平安、中国太保、中国人寿、中国人保等保险历史数据。

### 当前校准

- 当前版本号已由 `VERSION` 更新为 `1.1`。
- 1.1 之后，新增功能应优先满足：方法判断更准确、买卖动作更克制、复盘证据更清楚。

---

## [1.0] - 2026-06-28

首个正式基线。系统版本统一为 **preson 1.0**，Dashboard v2.x 内部计数归零，折叠为下方「Pre-1.0 开发迭代史」。

### 当前已交付能力

- **数据层**：8 个 DuckDB 库（`preson` 主库 573k+ 行 / `gold` / `market` / `etf` / `macro` / `turnover` / `decisions` / `analytics` 预计算库），覆盖 100 家公司。
  - ⚠️ 设计中的 `peers.duckdb`（同行对标库）当前缺失，待 `.tools/db/fetch_peers.py` 重建（列入 1.1 健康度里程碑）。
- **抓数 / 整合**：理杏仁 pipeline + `data_consolidator` 端到端，产出 `02_companies/` 历史 CSV + 摘要。
- **Dashboard**：Streamlit 五导航（🌡️ 市场&行业 · 🔍 选股 · 🏢 公司研究 · 💼 决策中心 · 🥇 黄金）。
- **大师评分**：林奇 / 巴菲特 / 格雷厄姆 / 芒格 / 黄金范式 五套引擎。
- **行业分析**：分位引擎 · 周期判定 · ETF 推荐 · 行业聚焦 Tab。
- **同行对标**：peers 引擎 + 决策中心 vs 同行（依赖 peers.duckdb 还原后满血）。
- **MCP 工具**：`query_metric` 等 4 个只读查询工具，供 Claude 会话调用。
- **Git 大文件**：`.github_blob_store` 分片上传 / 还原。
- **性能**：全市场重计算搬到离线预计算库 `analytics.duckdb`，页面切换降至百毫秒级（2026-06-28）。

### 本次收敛动作（版本统一 + 资料整理）

- 新增 `VERSION`（值 `1.0`）作为全系统唯一版本真源。
- 新增本 `CHANGELOG.md`，收编 v2.x 迭代史。
- 校准 README / CLAUDE / architecture 的「当前版本」锚点为 preson 1.0。
- 历史 `docs/plans/` 与 `docs/tasks/` 已交付文档物理归档到各自 `_archive/`。
- 新增 1.0 开发验证脚手架：`.streamlit/config.toml`（热重载）+ 子单元隔离台 `dev_harness.py` + manifest。

---

## Pre-1.0 开发迭代史

> 以下为 1.0 之前的 Dashboard 迭代时间线（浓缩）。详细计划文档见 `docs/plans/_archive/` 与 `docs/tasks/_archive/`。

- **v2.9** — 投资漏斗五导航 + 四子 Tab + 配置迁移；全市场预计算加速。
- **v2.7** — 持仓档案基础版：`portfolio.yaml` + 公平价 5 档 Graham + 公司详情持仓卡。
- **v2.6** — 黄金模块深化（β 引擎 / 过热历史 / 回测按日对照）；康波 Tab 计划立项（未交付）。
- **v2.5** — 行业分析与聚焦：分位引擎 / 周期判定 / ETF 推荐 / 行业聚焦 Tab。
- **v2.4** — 全局搜索栏 + 市场快照 + 行业聚焦 + 黄金过热走廊 + 芒格 Tab。
- **v2.3** — 黄金投资法四阶段（方法论 / 数据层 / Dashboard Tab / 范式引擎）。
- **v2.0–v2.2** — Dashboard 雏形：Streamlit 多 Tab + DuckDB 数据源 + 大师评分体系起步。
- **v1.x（档案库时代）** — 纯数据档案库：理杏仁抓数 + 公司档案库 + 知识库。

---

## 后续里程碑（规划）

- **1.1 健康度** — 重建 `peers.duckdb`、删 legacy 代码、`02_companies/` 目录标准化。
- 详见 [`docs/plans/PROJECT_PLAN_v1.0.md`](./docs/plans/PROJECT_PLAN_v1.0.md) 附录「1.0 之后的迭代建议」。
