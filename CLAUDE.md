# preson 项目空间

> 理财资料档案库 + 投研 Dashboard：个股分析、行业研究、投资决策跟踪
>
> 位于 `/Users/gongyong/Desktop/Keyi/preson/`
> 
> **最后更新**：2026-06-28 · **公司库** 100 家 · **当前版本** preson v1.0（Streamlit 五导航 Dashboard，版本史见 [CHANGELOG.md](./CHANGELOG.md)）
>
> 📌 项目已从"纯数据档案库"演进为"投研智能体 + Dashboard"。换机上手与日常命令见根目录 [README.md](./README.md)，架构设计见 [docs/architecture/](./docs/architecture/README.md)。本文件聚焦 **AI 会话工作区规则**与**抓数脚本约定**。

---

## 📂 项目结构

```
preson/
├── .tools/                          ← 工具脚本（可执行）
│   ├── lixinger-archiver/          ├─ 理杏仁数据抓取工具集
│   ├── extract_recent_data.py      ├─ 最近一月数据切片脚本
│   ├── batch_broker_analysis.py    ├─ 批量券商分析脚本
│   ├── fetch_tushare_broker_analysis.py
│   ├── build_short_term_analysis.py
│   └── update_archive.sh
│
├── .config/                         ← 配置与敏感文件
│   ├── companies.csv               ├─ 公司清单
│   ├── credentials.md              ├─ 凭证（理杏仁账号）
│   └── .lixinger_token             ├─ Token 文件
│
├── 01_knowledge/                    ← 知识库（投资决策体系）
│   ├── 01_宏观周期与资产配置/      ├─ 大周期判断+资产配置比例
│   ├── 02_权益类动态调整/          ├─ 市场信号+权益占比调整
│   ├── 03_投资策略与选股/          ├─ 价值/成长策略+选股选ETF框架
│   │   ├── 01_价值投资法/          ├─ 格雷厄姆深度价值投资法
│   │   ├── 02_彼得林奇投资法/          ├─ 彼得林奇成长投资法
│   │   ├── 03_多元思维.md          ├─ 芒格多元思维模型
│   │   ├── 04_选股框架.md          ├─ 个股筛选与评估流程
│   │   └── 05_选ETF框架.md         ├─ ETF选择与配置逻辑
│   ├── 04_知识体系/                ├─ 推荐书籍 + 阅读分析 + 读书笔记
│   └── 05_实战案例与持仓/          ├─ 投资决策记录与复盘
│       ├── 活跃持仓/               ├─ 当前持仓的分析与追踪
│       ├── 已平仓案例/             ├─ 历史持仓的学习与复盘
│       └── 持仓统计与复盘/         ├─ 总体配置统计与年度复盘
│
├── 02_companies/                    ← 公司档案库（实时数据）
│   ├── 01_新华保险/
│   ├── 02_三美股份/
│   ├── ... (核心 16 家 + 候选池，共 100 家)
│   │   ├── 01_基本面数据/          ├─ 整合后的基本面数据
│   │   │   ├── 摘要.md             ├─ ⭐核心：Claude 常读此文件
│   │   │   ├── 历史数据/           ├─ CSV格式，供脚本/分析使用
│   │   │   │   ├── 估值.csv        │  - PE/PB/PS/股息率等时间线
│   │   │   │   ├── 盈利.csv        │  - ROE/ROA/毛利率等
│   │   │   │   ├── 成长.csv        │  - 收入/利润增长
│   │   │   │   ├── 现金流.csv      │  - 经营/自由现金流
│   │   │   │   ├── 安全性.csv      │  - 负债率/流动比率
│   │   │   │   └── 年报快照.csv    │  - 最新年报单点数据
│   │   │   └── 行业对比/           ├─ 与同行公司对比的数据
│   │   ├── 02_公司财报/            ├─ 季度/年度财报 PDF
│   │   ├── 03_行业分析/            ├─ 行业与对标分析
│   │   ├── 04_券商分析/            ├─ 研报与观点摘要
│   │   └── 05_投资决策/            ├─ 策略与决策记录
│   └── _财报批量下载/              ├─ 批量财报下载辅助
│
├── 03_macro/                        ← 宏观与行业数据
│   ├── ETF工具箱/
│   ├── 行业分析/
│   ├── 行业分析路径/
│   └── 制图_*.csv
│
├── .archive/                        ← 归档与历史
│   └── financials_batch/           ├─ 历史财报下载记录
│
├── .temp/                           ← 临时文件（不纳入版本控制）
│   └── recent_month_extract/       ├─ 脚本临时输出
│
├── CLAUDE.md                        ← 项目配置（本文件）
├── README.md                        ├─ 项目说明
└── .gitignore                       ├─ Git 忽略规则
```

---

## ⚠️ 工作边界

本会话的所有文件操作（Read/Edit/Write/Bash/Grep）**仅限于** `/Users/gongyong/Desktop/Keyi/preson/` 子树内。

- **不访问**其他子目录（office/ / test/ 等）或项目外的路径
- **敏感文件**：`.config/credentials.md` 包含凭据，未经允许不读取、不展示、不外传
- 若任务看似需要跨越 preson/ 边界，**先停下来与用户确认** 再动作

---

## 🚀 快速开始

### 1. 🎯 推荐：一键更新 + 整合（最常用）

```bash
cd /Users/gongyong/Desktop/Keyi/preson
source .venv/bin/activate

# 抓取 10 年历史 + 自动整合到新结构
python3 .tools/data_consolidator/update_pipeline.py
```

**效果**：
- 抓取最新数据到各公司目录
- 自动整合到 `历史数据/*.csv` + `摘要.md`
- 一键完成

### 2. 跨公司对比分析

```bash
# 生成全部公司全景对比（估值/盈利/规模/安全性）
python3 .tools/data_consolidator/cross_analysis.py
```

**输出**：`02_companies/_汇总/`
- `全景.md` - 一屏看全所有公司，含排行榜
- `估值对比.csv` / `盈利对比.csv` / 等

### 3. 仅重新整合（不抓取新数据）

```bash
# 从已有的原始文件重新整合
python3 .tools/data_consolidator/consolidate.py
python3 .tools/data_consolidator/consolidate.py --only=新华保险  # 只处理一家
```

### 4. 传统抓取脚本（仅网络抓取，不整合）

```bash
# 完整抓取管道
python3 .tools/lixinger-archiver/run_full_pipeline.py \
  --companies-csv .config/companies.csv \
  --days 365 --years 10 \
  --clean-existing

# 单独抓取估值
python3 .tools/lixinger-archiver/batch_update_recent_wide.py \
  --companies-csv .config/companies.csv \
  --base-dir 02_companies \
  --days 365

# 单独抓取财务
python3 .tools/lixinger-archiver/batch_update_fs_modules.py \
  --companies-csv .config/companies.csv \
  --base-dir 02_companies \
  --years 10
```

### 5. 提取最近一个月数据

```bash
python3 .tools/extract_recent_data.py
```

### 5. 批量券商分析

```bash
python3 .tools/batch_broker_analysis.py
```

---

## 📊 数据约定

### 公司档案库结构

每个公司目录采用统一的5层结构：
```
{编号}_{公司名}/
├── 01_基本面数据/          ← 从理杏仁抓取的定量数据
│   ├── 00_最近一月数据/    ← 最近30天的切片（每月更新）
│   ├── 01_估值分析/        ← PE/PB/PS/PEG/股息率等
│   ├── 02_盈利分析/        ← ROE/ROA/毛利率等
│   ├── 03_成长性分析/      ← 收入/利润增长率
│   ├── 04_现金流分析/      ← 经营/自由现金流
│   └── 05_安全性分析/      ← 负债率/流动比率等
├── 02_公司财报/            ← 季度/年度 PDF 文件
├── 03_行业分析/            ← 行业对标、市场地位分析
├── 04_券商分析/            ← 券商研报、评级、目标价
└── 05_投资决策/            ← 投资策略、决策记录
```

### 公司清单

当前管理 **100 家公司**（核心持仓 16 家 + 候选池扩展），权威清单见 `.config/companies.csv`（列：`folder,stock,name,category,industry`）。

核心持仓 16 家：
```
01_新华保险    05_中国中车    09_三花智控    13_伊利股份
02_三美股份    06_贵州茅台    10_比亚迪      14_中际旭创
03_蜜雪集团    07_美的集团    11_五粮液      15_恒瑞医药
              08_立讯精密    12_招商银行    16_宁德时代
```

**注意**：无编号 04（历史占位，不单独建文件夹）；其余 84 家为候选池，不一定建完整 5 层目录。

### 数据来源

| 类别 | 来源 | 脚本 | 频率 |
|------|------|------|------|
| 估值/财务指标 | 理杏仁（lixinger.com）| `batch_update_recent_wide.py` | 按需 |
| 财务模块（02-05）| 理杏仁 API | `batch_update_fs_modules.py` | 按需 |
| 最近一月切片 | 本地 01_基本面数据 | `extract_recent_data.py` | 月度 |
| 券商研报 | Tushare Pro | `fetch_tushare_broker_analysis.py` | 按需 |
| 财报 PDF | 各公司官方披露 | 手工归档 | 按发布 |

---

## 🔧 会话默认行为

1. **首次进入**：先读本文件，确认目录结构
2. **运行脚本前**：激活虚拟环境 `.venv/`
3. **Token 获取**：从 `.config/credentials.md` 自动解析
4. **临时输出**：脚本临时文件输出到 `.temp/recent_month_extract/`
5. **非 Git 仓库**：不执行任何 git 操作
6. **Dashboard 上下文**：若 `.temp/current_context.md` 存在，**首条用户消息前**先读它 — 这是 Streamlit Dashboard 写入的"用户当前正在看哪家公司"的元信息。用户在终端里说"现在贵不贵 / 这家怎么样"等省略主语的问句时，按此上下文锚定具体公司。

---

## 🚫 禁止动作（需先确认）

除非用户明确授权，否则：

- 删除或移动公司档案库中的历史数据文件
- 修改 `.config/` 中的凭证
- 访问 `.config/credentials.md` 的内容（读取并显示）
- 执行联网写入（推送、上传）
- 修改脚本核心逻辑（会影响数据格式）

---

## 📝 更新记录

- **2026-06-28**：系统版本统一为 **preson v1.0**
  - 建立单一版本真源根目录 `VERSION`（值 `1.0`）+ `CHANGELOG.md`（收编 v2.x 迭代史）
  - 校准 README/CLAUDE/architecture 的「当前版本」锚点；Dashboard v2.x 内部计数归零
  - 历史 `docs/plans/`、`docs/tasks/` 已交付文档归档到各自 `_archive/`
  - 新增 1.0 开发验证脚手架：`.streamlit/config.toml`（热重载）+ 子单元隔离台 `dev_harness.py`

- **2026-06-28**：文档校准
  - 公司库 15 → **100 家**（核心 16 + 候选池），清单以 `.config/companies.csv` 为准
  - 项目已演进为五导航 Streamlit Dashboard，详见根 README 与 docs/
  - ⚠️ `data/` 现有 8 个 DuckDB（含 analytics 预计算库），**peers.duckdb 仍缺失**，需跑 `.tools/db/fetch_peers.py` 重建

- **2026-04-23**：完整迁移项目结构
  - 创建 `.tools/` 集中管理脚本
  - 创建 `.config/` 管理配置
  - 重命名知识库为 `01_knowledge/`
  - 重命名公司档案库为 `02_companies/`
  - 重命名宏观数据为 `03_macro/`
  - 创建 `.archive/` 存储历史文件
  - 更新所有脚本的路径引用
  
- **2026-04-23**：理杏仁数据补齐完成
  - ✅ 估值分析（01_估值分析）：15 家公司全部更新
  - ⚠️ 财务模块（02-05）：前 2 家成功，后续因服务器错误中断

- **2026-04-22**：公司列表补全为 15 家

---

📧 **联系**：renmingyang@proton.me
