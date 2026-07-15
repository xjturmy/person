# Project Layout

> 目标:根目录只保留入口文件;资料、数据、脚本、导出物各归其位。

## 根目录

根目录只放这些长期入口:

| 路径 | 用途 |
|---|---|
| `README.md` | 项目使用说明 |
| `AGENTS.md` | Codex 会话规则 |
| `CHANGELOG.md` / `VERSION` | 版本记录 |
| `restart_dashboard.sh` | 前端重启入口 |
| `refresh_holding_focus_data.sh` | 持仓数据刷新入口 |
| `01_knowledge/` | 投资体系、持仓复盘、决策记录 |
| `02_companies/` | 公司档案库 |
| `03_macro/` | 宏观、行业、ETF 数据 |
| `data/` | DuckDB 等结构化数据 |
| `docs/` | 架构、Dashboard、流程文档 |
| `.tools/` | 抓数、分析、Dashboard 支撑脚本 |
| `.config/` | 本地配置和投资组合配置 |
| `.temp/` | 临时日志和中间结果 |
| `.archive/` / `.backup/` | 历史归档和旧迁移备份 |

## 日常文件归属

| 文件类型 | 放置位置 |
|---|---|
| 持仓截图、条件单截图 | `01_knowledge/05_实战案例与持仓/持仓统计与复盘/{日期}_*/assets/` |
| 本周操作建议 | `01_knowledge/05_实战案例与持仓/持仓统计与复盘/` |
| 条件单识别与建议 | `01_knowledge/05_实战案例与持仓/持仓统计与复盘/{日期}_持仓与条件单复盘/` |
| 公司研究资料 | `02_companies/{编号}_{公司}/` |
| 外部目标价模板 | `.config/external_price_refs.csv` |
| Dashboard 风格/设计记录 | `docs/dashboard/` |
## 整理规则

1. 根目录不放截图、zip、临时导出目录。
2. 可复盘的材料进入 `01_knowledge/05_实战案例与持仓/持仓统计与复盘/`。
3. 可重建的中间产物进入 `.temp/`,不进入正式文档。
4. 公司级资料进入对应 `02_companies/{公司}/`。
5. 影响 Dashboard 或抓数流程的脚本进入 `.tools/`,并在 `docs/` 补充说明。
