# 顶层目录布局

## 目录职责表

| 目录 | 类型 | 用途 |
|------|------|------|
| `.tools/` | 可执行代码 | 抓数、整合、Dashboard、MCP、评分、规则 |
| `.config/` | 配置 | 凭证、持仓、观察池、公司清单、行业主索引 |
| `data/` | 运行时 DB | DuckDB 集群（git 通常忽略大文件） |
| `01_knowledge/` | 静态资料 | 投资方法论、读书笔记、月度复盘 |
| `02_companies/` | 公司档案 | ~100 家 × 5 板块（基本面/财报/行业/券商/决策） |
| `03_macro/` | 宏观资料 | 行业对标、ETF 工具箱；industry 引擎读基准 |
| `docs/` | 设计文档 | 架构、计划、Dashboard 优化、任务拆解 |
| `.archive/` | 归档 | 历史快照、下线脚本 |
| `.temp/` | 临时 | 批处理日志、Streamlit 上下文、验证报告 |

## `.tools/` 子树

```
.tools/
├── dashboard/          # Streamlit 应用（主入口 app.py）
│   ├── tabs/           # 页面级 UI
│   ├── gold/           # 黄金引擎
│   ├── masters/        # 大师方法论引擎
│   ├── valuation/      # 估值引擎
│   ├── industry/       # 行业分位/筛选
│   ├── peers/          # 同行雷达
│   ├── screening/      # 选股筛选
│   ├── holdings/       # 持仓技术/两融/账本
│   ├── ui/             # 通用 UI 组件
│   ├── components/     # 搜索栏等
│   ├── tests/          # Dashboard 单测
│   ├── navigation.py   # 跨 Tab 跳转协议
│   ├── state.py        # 行业焦点 session 封装
│   └── watchlist.py    # 观察池读写
├── db/                 # DuckDB 抓数 + ingest + 周末编排
├── data_consolidator/  # CSV 整合与跨公司分析
├── lixinger-archiver/  # 理杏仁原始抓取
├── portfolio/          # 持仓 loader、再平衡、月报
├── decisions/          # 决策日志 DuckDB CRUD + 快照
├── mcp/                # Claude MCP Server
├── score/              # 多大师评分引擎
└── rules/              # YAML 规则定义
```

## `.config/` 关键文件

| 文件 | 说明 |
|------|------|
| `companies.csv` | 公司清单：folder / stock / name / category |
| `portfolio.yaml` | **v2.8+** 持仓唯一数据源（含 positions 合并字段） |
| `watchlist.yaml` | 观察池结构化条目 |
| `focus_industries.yaml` | 用户关注行业列表 |
| `industry_master.yaml` | 申万 L1/L2 行业主索引 |
| `credentials.md` | 理杏仁 Token（**不入 git**） |

## `02_companies/` 单公司结构

```
{编号}_{公司名}/
├── 01_基本面数据/
│   ├── 摘要.md              ← 整合脚本输出，Claude 常读
│   ├── 历史数据/*.csv       ← 抓数写、ingest 读、整合读
│   └── 01_估值分析/ …       ← 理杏仁原始抓取目录
├── 02_公司财报/             ← PDF，手工归档
├── 03_行业分析/
├── 04_券商分析/
└── 05_投资决策/
```

## 边界原则

1. **运行时 vs 静态**：DuckDB + YAML 参与运行时；`01_knowledge/` 与财报 PDF 以人读为主
2. **写权限**：抓数脚本写 DB/CSV；Dashboard 写 `decisions.duckdb`、`portfolio.yaml`、`watchlist.yaml`
3. **单一可信源**：ticker 规范化见 `tickers.normalize_ticker`；持仓见 `.config/portfolio.yaml`
