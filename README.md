# preson — 个人理财资料档案库

> 个股分析 · 行业研究 · 投资决策跟踪 · Streamlit Dashboard  
> **换机后先看本文**，5 分钟恢复开发环境；细节见 [docs/README.md](./docs/README.md)

**最后更新**：2026-06-28 · **当前版本**：Dashboard v2.9 · **公司库**：100 家

---

## ⚡ 换机 5 分钟上手

```bash
# 1. 克隆（私有仓库，需先配置 GitHub 访问）
git clone <your-repo-url> preson && cd preson

# 2. 还原 DuckDB 大文件（Git 中以分片存储，clone 后必须跑）
python3 .tools/github_upload/merge_assets.py --restore-all

# 3. Python 环境
python3 -m venv .venv
source .venv/bin/activate
pip install -r .tools/dashboard/requirements.txt
# 抓数脚本额外依赖（按需）
pip install akshare requests pyyaml openpyxl

# 4. 凭证（不会进 Git，需手动恢复）
#    复制旧机的 .config/credentials.md 到新项目
#    或在其中写入：开放API Token: <理杏仁 Token>

# 5. 持仓/观察池（隐私文件，不会进 Git）
#    复制旧机 .config/portfolio.yaml 和 .config/watchlist.yaml
#    或从 Dashboard「决策中心 → 持仓确定」重新配置

# 6. 启动 Dashboard
./restart_dashboard.sh          # 默认 http://localhost:8501
# 或
.venv/bin/streamlit run .tools/dashboard/app.py
```

**换机检查清单**

| 步骤 | 必须？ | 说明 |
|------|:------:|------|
| `merge_assets.py --restore-all` | ✅ | 还原 `data/*.duckdb`，否则 Dashboard 走 CSV 兜底 |
| `.config/credentials.md` | ✅ | 理杏仁 Token，抓数/API 必需 |
| `.config/portfolio.yaml` | 推荐 | 真实持仓，决策中心依赖 |
| `.config/watchlist.yaml` | 推荐 | 观察池，公司研究导航依赖 |
| `.venv` 重建 | ✅ | 虚拟环境不纳入 Git |
| `python3 .tools/db/ingest.py` | 备选 | 若 blob 还原失败，可从 CSV 重建 DuckDB |

---

## 📊 当前开发状态（2026-06）

### 已完成

| 模块 | 状态 | 说明 |
|------|:----:|------|
| 数据层 | ✅ | 8 个 DuckDB 库（当前 data/ 实存 7 个，peers 待还原）· 100 家公司 · 573k+ 行主库 |
| 抓数/整合 | ✅ | 理杏仁 pipeline + `data_consolidator` 端到端 |
| Dashboard v2.9 | ✅ | 投资漏斗五导航 · 四子 Tab · 配置迁移 |
| 大师评分 | ✅ | 林奇 / 巴菲特 / 格雷厄姆 / 芒格 / 黄金范式 |
| 行业分析 | ✅ | 分位引擎 · 周期判定 · ETF 推荐 · 行业聚焦 Tab |
| 同行对标 | ✅ | peers 引擎 + 决策中心 vs 同行 |
| MCP 工具 | ✅ | `query_metric` 等 4 工具，Claude 只读查询 |
| Git 大文件 | ✅ | `.github_blob_store` 分片上传/还原 |

### 进行中 / 待办

| 项 | 优先级 | 说明 |
|----|:------:|------|
| `peers.duckdb` 待还原 | 🔴 | data/ 现有 7 库，同行对标库未还原；跑 `.tools/db/fetch_peers.py` 重建 |
| 进展看板同步 | 🟡 | [docs/plans/PROGRESS.md](./docs/plans/PROGRESS.md) 部分条目滞后于代码 |
| 金融业字典 | 🔴 P3 | NPL/CET1/EV·NBV 等需外部数据源 |
| 月报 PDF 输出 | 🟡 | 数据层 OK，PDF/邮件待做 |
| v2.6 康波 Tab | ⏳ | 计划见 [PROJECT_PLAN_v2.6.md](./docs/plans/PROJECT_PLAN_v2.6.md) |

### 最近 Git 里程碑

```
e6e6692  完成数据库数据的补充
6ad2fc8  完成初步的数据抓取
ff248ab  安全瘦身 — untrack .backup/ 与备份残留，补 .gitignore
cb77b67  完成所有信息的基本的备份
00bd34d  develop: 11 个分片合并为单一工作树（blob store plan B）
```

---

## 🏗 架构一图

```
数据源(理杏仁 · AkShare · 本地 CSV)
        ↓
抓数层  .tools/lixinger-archiver/  ·  .tools/db/fetch_*.py
        ↓
数据层  data/*.duckdb  (preson · gold · peers · market · etf · macro · decisions · turnover)
        ↓
整合层  .tools/data_consolidator/  →  02_companies/历史 CSV + 摘要.md
        ↓
展示层  .tools/dashboard/app.py  (Streamlit · 五导航 · 大师引擎)
        ↓
配置层  .config/  (portfolio · watchlist · 行业焦点 · 凭证)
```

详细设计 → [docs/architecture/00-overview.md](./docs/architecture/00-overview.md)

---

## 📁 目录地图

```
preson/
├── README.md              ← 你在这里（换机入口）
├── CLAUDE.md              ← AI 助手工作区规则
├── ARCHITECTURE.md        ← 架构快捷跳转
├── restart_dashboard.sh   ← 一键重启 Dashboard
│
├── .config/               ← 配置（部分敏感，不进 Git）
│   ├── companies.csv      ← 100 家公司清单
│   ├── portfolio.yaml     ← 真实持仓（本地）
│   ├── watchlist.yaml     ← 观察池（本地）
│   └── credentials.md     ← 理杏仁 Token（本地）
│
├── .tools/                ← 全部可执行脚本
│   ├── dashboard/         ← Streamlit 主程序
│   ├── db/                ← DuckDB 抓数/更新/ingest
│   ├── data_consolidator/ ← CSV 整合 + 跨公司对比
│   ├── lixinger-archiver/ ← 理杏仁批量抓数
│   ├── score/             ← 多大师评分引擎
│   ├── mcp/               ← Claude MCP Server
│   └── github_upload/     ← 大文件分片/还原
│
├── data/                  ← DuckDB 数据库（本地/blob 还原）
├── 01_knowledge/          ← 投资方法论与读书笔记
├── 02_companies/          ← 100 家公司档案（CSV + 财报 PDF + 决策）
├── 03_macro/              ← 宏观与 ETF 工具
├── docs/                  ← 项目文档（计划/架构/任务）
├── .github_blob_store/    ← DuckDB 分片（Git 跟踪）
└── .temp/                 ← 临时输出（不进 Git）
```

---

## 🚀 日常操作速查

### Dashboard

```bash
./restart_dashboard.sh              # 重启（杀旧进程 + 后台启动）
tail -f .temp/dashboard.log         # 看日志
```

Dashboard 五导航：**🌡️ 市场&行业** · **🔍 选股** · **🏢 公司研究** · **💼 决策中心** · **🥇 黄金**

### 数据更新

```bash
source .venv/bin/activate

# 推荐：抓数 + 整合一条龙
python3 .tools/data_consolidator/update_pipeline.py

# 仅抓数（不整合）
python3 .tools/lixinger-archiver/run_full_pipeline.py \
  --companies-csv .config/companies.csv --days 90 --years 10

# DuckDB 增量更新（周末 cron 同款）
python3 .tools/db/update.py

# 从 CSV 重建 DuckDB
python3 .tools/db/ingest.py

# 跨公司对比报告
python3 .tools/data_consolidator/cross_analysis.py
```

### 测试

```bash
cd .tools/dashboard && python -m pytest tests/ -q
```

---

## 📚 文档索引

| 文档 | 用途 |
|------|------|
| **[docs/README.md](./docs/README.md)** | 文档总入口 |
| [docs/plans/PROGRESS.md](./docs/plans/PROGRESS.md) | 进展看板（任务/阻塞/版本日志） |
| [docs/plans/PROJECT_PLAN_v2.7_持仓档案.md](./docs/plans/PROJECT_PLAN_v2.7_持仓档案.md) | 最新版本计划 |
| [docs/architecture/](./docs/architecture/README.md) | 五层架构 · ADR 决策记录 |
| [docs/architecture/12-dashboard-v2.9-design-scheme.md](./docs/architecture/12-dashboard-v2.9-design-scheme.md) | Dashboard v2.9 设计 |
| [.tools/dashboard/README.md](./.tools/dashboard/README.md) | Dashboard 启动/故障排查 |
| [CLAUDE.md](./CLAUDE.md) | AI 会话配置与脚本约定 |

---

## ⚙️ 配置说明

### 理杏仁 Token

1. 登录 [理杏仁](https://www.lixinger.com) → API 配置 → 复制 Token  
2. 写入 `.config/credentials.md`（格式见文件内注释）  
3. 或通过环境变量：`export LIXINGER_TOKEN="..."`

### 公司清单

编辑 `.config/companies.csv` 增删公司，然后在 `02_companies/` 建对应目录，跑更新脚本即可。

当前 **100 家**（核心持仓 16 家 + 候选池扩展），详见 CSV 的 `folder,stock,name,category,industry` 列。

### 不进 Git 的本地文件

| 文件 | 原因 |
|------|------|
| `.config/credentials.md` | 凭证 |
| `.config/portfolio.yaml` | 真实持仓 |
| `.config/watchlist.yaml` | 观察池 |
| `data/*.duckdb` | 体积大，走 blob store 分片 |
| `.venv/` | 虚拟环境 |
| `.temp/` | 临时文件 |

---

## 🐛 常见问题

| 现象 | 处理 |
|------|------|
| Dashboard 显示「CSV 兜底模式」 | 跑 `merge_assets.py --restore-all` 或 `ingest.py` |
| 同行对标无数据 / 报 `peers.duckdb` 缺失 | 跑 `python3 .tools/db/fetch_peers.py` 重建该库 |
| `ModuleNotFoundError` | `source .venv/bin/activate` + 装 requirements |
| Token 过期 | 理杏仁官网重新获取，更新 `credentials.md` |
| 端口 8501 被占 | `./restart_dashboard.sh` 会自动清理 |
| clone 后无 DuckDB | 正常，跑 blob 还原脚本 |
| 持仓/观察池为空 | 复制旧机 yaml 或在 Dashboard 重新配置 |

---

## 🔗 外部依赖

| 服务 | 用途 |
|------|------|
| [理杏仁](https://www.lixinger.com) | 估值/财务主数据源 |
| [Tushare Pro](https://tushare.pro) | 券商研报 |
| [AkShare](https://akshare.akfamily.xyz) | 宏观/黄金/全 A 快照 |

---

**维护**：renmingyang@proton.me
