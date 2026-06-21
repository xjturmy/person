---
name: lixinger-wide-archiver
description: 通过理杏仁开放API拉取估值宽表与 02–05 财务指标，写入 `02_公司档案库/{编号}_{公司}/01_基本面数据/` 下各子目录，并生成/回写 `01_基本面数据/00_最近一月数据` 切片（CSV+MD）。适用于理杏仁、宽表、分位点、公司档案库更新、最近一月数据等场景。
---

> **分享版说明**  
> - **理杏仁开放 API** 的 URL、请求字段、`metricsList` 指标名与响应约定，见同目录 **[理杏仁开放API接口摘录.md](./理杏仁开放API接口摘录.md)**（便于转发给朋友时单独阅读）。  
> - 请将整个 `lixinger-wide-archiver` 文件夹放入知识库 **`.cursor/skills/lixinger-wide-archiver/`**，在**知识库根目录**（含 `02_公司档案库/`）执行下文命令；若路径不同，请自行替换命令中的前缀。  
> - **勿**在文档或命令中泄露真实 Token；建议使用环境变量 `LIXINGER_TOKEN`。

# 理杏仁数据归档（公司档案库 · `01_基本面数据`）

## 公司档案库目录结构（与脚本一致）

知识库根目录下的公司文件夹形如：`02_公司档案库/{两位编号}_{公司名}/`。**理杏仁相关脚本只读写的数据**集中在 `01_基本面数据/` 内；与同级的定性/财报等目录互不覆盖。

```
{编号}_{公司名}/
├── 01_基本面数据/                    ← 本 skill 脚本写入范围
│   ├── 00_最近一月数据/              ← 切片回写（`extract_recent_data.py` + 可选手工 cp）
│   ├── 01_估值分析/                  ← 宽表 CSV/MD（PE/PB/PS/股息率等）
│   ├── 02_盈利分析/
│   ├── 03_成长性分析/
│   ├── 04_现金流分析/
│   ├── 05_安全性分析/
│   └── 06_行业对比/                  ← 若有行业对比 CSV，`extract_recent_data.py` 会一并参与切片
├── 02_公司财报/                      ← 不由理杏仁脚本写入
├── 03_行业分析/                      ← 可由其它流程写入；非本 skill
├── 04_券商分析/
├── 05_投资决策/
└── …（各公司可能还有基础资料、策略文档等 .md，与理杏仁数据无关）
```

说明：历史资料或旧索引中可能出现「`01_估值分析` 等公司根目录平铺」的旧结构；**当前批量脚本与 `extract_recent_data.py` 均以 `01_基本面数据/` 为父目录**。新公司或整理时请采用上表结构，避免路径不一致。

## 目标

- 为指定公司生成 `01_基本面数据/01_估值分析/` 下的宽表 CSV（PB/PE/PS/股息率等，含 `y10` 分位点统计字段）
- 批量生成 `01_基本面数据/` 下 `02_盈利分析`～`05_安全性分析` 的财报 CSV
- **每次上述脚本或 `extract_recent_data.py` 写入 CSV 后，自动生成同名 Markdown**（`.csv` → 同目录同名 `.md`，管道表格；数值列去掉前导 `=` 以方便阅读）
- 运行 `extract_recent_data.py` 生成 `最近一个月数据提取/{编号}_{公司名}/`
- 将该输出覆盖回写到 `02_公司档案库/{编号}_{公司名}/01_基本面数据/00_最近一月数据/`（CSV 与 MD 一并覆盖；`extract_recent_data.py` 内置回写时会同步处理）

实现：`scripts/lixinger_csv_to_md.py` 中的 `write_md_sidecar`；使用 `--clean-existing` 时会同时删除与旧 CSV 对应的 `.md`。

## 前置条件

- 已有理杏仁 Token（来自 `https://www.lixinger.com/open/api/token`）
- 本项目推荐使用本地 venv：`.venv_lixinger/`（已安装 `requests`）

## Token 安全建议（强烈推荐）

- 不要把真实 token 明文写进任何文档（包括本文件），避免复制传播导致泄露。
- 推荐做法：把 token 放到环境变量 `LIXINGER_TOKEN`（仅保存在你自己的机器/会话里）。

示例（zsh）：

```bash
export LIXINGER_TOKEN="<YOUR_TOKEN>"
```

## 标准输出（01 估值宽表）

宽表表头示例（PB）：

- `日期`
- `理杏仁前复权(元)` / `前复权(元)` / `后复权(元)` / `股价(元)`
- `市值(元)` / `流通市值(元)` / `自由流通市值(元)`
- `行业中位数`（开放API暂无直接字段，当前留空）
- `PB`、`PB 分位点`、`PB 80%分位点值`、`PB 50%分位点值`、`PB 20%分位点值`

## 标准输出（02-05 财务模块）

- 表头统一：`日期,财报类型,货币,<指标列>[,累积同比]`
- 时间顺序：按 `日期` 降序（最新在上）
- 数值格式：数值前加 `=`（如 `=0.1477` / `=803964958000`）
- 文件命名：`{公司名}_{指标名}_合并报表_{时间戳}.csv`

## 公司档案库 CSV 约定（与脚本输出一致）

执行本 skill 中的脚本时，生成的估值宽表已遵守：

- **长表**：首列为 `日期`（`YYYY-MM-DD`），**不得**用「报告期横铺列」的宽表形式存放时间维度。
- **时间顺序**：同一文件内按 `日期` **降序**（**最新在上**），便于与「最近一月」阅读和抽查一致。
- **数值格式**：沿用理杏仁导出习惯，数值前加 `=`（如 `=6.1234`），便于在表格软件中当作公式/数值识别。
- **脚注**：若需保留「数据来源于：理杏仁…」类说明，放在 CSV **数据行之后**（单独一行），勿插在表头与数据之间。

说明：若从网页手工下载或其它脚本得到的表仍是「日期在表头行」，需要先转置为上述长表再入库；批量整理可一次性跑项目内既有规范化流程（保持与全库 CSV 一致）。

## API 与脚本能力边界

- **01 估值接口**：`batch_update_recent_wide.py` / `generate_wide_valuation.py` 使用  
  `https://open.lixinger.com/api/cn/company/fundamental/non_financial`（**非金融**公司日频基本面）。
- **02-05 财务接口**：`batch_update_fs_modules.py` 使用  
  `https://open.lixinger.com/api/cn/company/fs/{category}`，`category` 支持 `non_financial/bank/security/insurance/other_financial`。
- **方式 A 批量脚本**当前固定输出 **6 类**估值 CSV：`PE-TTM`、`Deduction of PE-TTM`、`PB`、`PB without goodwill`、`PS-TTM`、`Dividend Yield Ratio`。**不包含** PEG、PEV、资产/负债结构等；若需要，须用其它接口/脚本或单独调用 `generate_wide_valuation.py` 扩展 `metricsList` 后再实现写入（维护时注意与现有文件名规范一致）。
- **`generate_wide_valuation.py`**：适合单公司、较长历史窗口；**无**方式 A 中的批量分位点快照优化，Token 消耗相对更高，适合补全或一次性回填。
- **`batch_update_fs_modules.py`**：默认写入 14 个财务指标文件（02-05）；支持公司级 `category` 字段。

## 工作流（按顺序执行）

### 方式A（推荐，省token）：批量生成“最近N天宽表” + 批量分位点统计

适用：需要更新很多家公司，且主要用于近月跟踪。

1) 准备公司清单 `companies.csv`（UTF-8）：

```csv
folder,stock,name
09_三花智控,002050,三花智控
07_美的集团,000333,美的集团
```

可选加一列 `category`（用于 02-05 财务接口）：

```csv
folder,stock,name,category
10_比亚迪,002594,比亚迪,non_financial
01_新华保险,601336,新华保险,insurance
```

2) 执行批量脚本（一次批量获取统计快照，再逐家公司拉最近N天日频）：

```bash
source ".venv_lixinger/bin/activate"
python3 ".cursor/skills/lixinger-wide-archiver/scripts/batch_update_recent_wide.py" \
  --companies-csv "companies.csv" \
  --days 90 \
  --stats-window y10 \
  --clean-existing
```

说明：

- 如果你已经设置了环境变量 `LIXINGER_TOKEN`，则可以**不传** `--token` 参数。
- 若你不想设置环境变量，也可以继续用 `--token "<YOUR_TOKEN>"` 显式传入（但不推荐长期这样做）。

### 方式B：生成估值宽表到公司档案库（全历史）

在项目根目录执行，`--out-dir` 必须指向该公司 **`01_基本面数据/01_估值分析`**：

```bash
source ".venv_lixinger/bin/activate"
# 推荐同样使用环境变量 LIXINGER_TOKEN，省略 --token
python3 ".cursor/skills/lixinger-wide-archiver/scripts/generate_wide_valuation.py" \
  --stock "<A股代码，如 002050>" \
  --name "<公司名，如 三花智控>" \
  --out-dir "02_公司档案库/<编号_公司名>/01_基本面数据/01_估值分析" \
  --years 10
```

### 方式C：批量更新 02-05 财务模块（盈利/成长/现金流/安全性）

适用：需要更新 `01_基本面数据/` 下的 `02_盈利分析`、`03_成长性分析`、`04_现金流分析`、`05_安全性分析`。

接口（非金融公司）：`https://open.lixinger.com/api/cn/company/fs/non_financial`  
脚本会按公司分类自动拼接 `/fs/{category}`，默认 `category=non_financial`。

公司清单（可选 category）：

```csv
folder,stock,name,category
10_比亚迪,002594,比亚迪,non_financial
```

执行：

```bash
source ".venv_lixinger/bin/activate"
python3 ".cursor/skills/lixinger-wide-archiver/scripts/batch_update_fs_modules.py" \
  --companies-csv "companies.csv" \
  --years 10 \
  --clean-existing
```

### 方式D：完整链路（01-05 更新 + 最近一月提取 + 回写）

适用：一次性完成某家公司 `01_基本面数据` 下各模块（估值与 02–05 财务），并刷新 `00_最近一月数据`（含 CSV/MD）。

推荐使用一键脚本（避免手工拼接多条命令）：

```bash
source ".venv_lixinger/bin/activate"
python3 ".cursor/skills/lixinger-wide-archiver/scripts/run_full_pipeline.py" \
  --companies-csv "companies_byd.csv" \
  --days 90 \
  --stats-window y10 \
  --years 10 \
  --clean-existing
```

可选参数：

- `--token "<YOUR_TOKEN>"`：显式传 token（默认可省略，自动解析）
- `--skip-valuation` / `--skip-fs` / `--skip-extract` / `--skip-sync`：跳过某些步骤

如需手工分步执行，仍可使用下面命令：

```bash
source ".venv_lixinger/bin/activate"
python3 ".cursor/skills/lixinger-wide-archiver/scripts/batch_update_recent_wide.py" \
  --companies-csv "companies_byd.csv" \
  --days 90 \
  --stats-window y10 \
  --clean-existing

python3 ".cursor/skills/lixinger-wide-archiver/scripts/batch_update_fs_modules.py" \
  --companies-csv "companies_byd.csv" \
  --years 10 \
  --clean-existing

python3 extract_recent_data.py
rm -f "02_公司档案库/10_比亚迪/01_基本面数据/00_最近一月数据/比亚迪_"*.csv
rm -f "02_公司档案库/10_比亚迪/01_基本面数据/00_最近一月数据/比亚迪_"*.md
cp -f "最近一个月数据提取/10_比亚迪/比亚迪_"*.csv \
  "02_公司档案库/10_比亚迪/01_基本面数据/00_最近一月数据/"
cp -f "最近一个月数据提取/10_比亚迪/比亚迪_"*.md \
  "02_公司档案库/10_比亚迪/01_基本面数据/00_最近一月数据/"
```

## 02-05 指标映射（当前脚本内置）

以下目录名均相对于 `01_基本面数据/`（脚本输出路径为 `02_公司档案库/<编号_公司名>/01_基本面数据/<下表目录>/`）。

- `02_盈利分析`：`q.m.roe.ttm`、`q.m.roa.ttm`、`q.m.gp_m.ttm`、`q.m.np_s_r.ttm`
- `03_成长性分析`：`q.ps.oi.t(+t_y2y)`、`q.ps.npatoshopc.t(+t_y2y)`、`q.ps.beps.t(+t_y2y)`
- `04_现金流分析`：`q.cfs.ncffoa.t(+t_y2y)`、`q.m.fcf.ttm`、`q.m.ncffoa_np_r.ttm`
- `05_安全性分析`：`q.m.tl_ta_r.t`、`q.m.lwi_ta_r.t`、`q.m.c_r.t`、`q.m.q_r.t`

### 2) 清理并生成“最近一个月数据提取”

在项目根目录（本知识库根目录，即含 `extract_recent_data.py` 与 `02_公司档案库/` 的目录）执行：

```bash
# 先清理该公司旧切片（避免历史遗留文件混入）
rm -f "最近一个月数据提取/<编号_公司名>/<公司名>_"*.csv
rm -f "最近一个月数据提取/<编号_公司名>/<公司名>_"*.md

# 生成切片（脚本扫描各公司 01_基本面数据 下 01–06 模块的 CSV）
python3 extract_recent_data.py
```

注意：`extract_recent_data.py` 当前将知识库根路径写死在脚本内；若迁移目录，需同步修改脚本中的 `root`/`base_path`，或后续改为「基于脚本位置推断根目录 / 环境变量」以提高可移植性。

### 3) 回写到公司档案库 `01_基本面数据/00_最近一月数据/`

```bash
rm -f "02_公司档案库/<编号_公司名>/01_基本面数据/00_最近一月数据/<公司名>_"*.csv
rm -f "02_公司档案库/<编号_公司名>/01_基本面数据/00_最近一月数据/<公司名>_"*.md
cp -f "最近一个月数据提取/<编号_公司名>/<公司名>_"*.csv \
  "02_公司档案库/<编号_公司名>/01_基本面数据/00_最近一月数据/"
cp -f "最近一个月数据提取/<编号_公司名>/<公司名>_"*.md \
  "02_公司档案库/<编号_公司名>/01_基本面数据/00_最近一月数据/"
```

## 常见问题

- **为什么“行业中位数”为空**：开放API文档未提供该字段，网页端宽表可能来自另一路导出。当前优先保证“宽表+分位点统计”可用。
- **如何避免旧文件混入**：生成切片前先清理 `最近一个月数据提取/<编号_公司名>/` 下旧 CSV/MD；回写前清理公司目录 `01_基本面数据/00_最近一月数据/` 下旧 CSV/MD。

## 故障排查

- **`API返回错误` / `code` 非 1**：核对 token 是否有效、是否过期；请求体字段是否与开放文档一致（如 `stockCodes`、日期区间）。
- **HTTP 429 / 频繁重试**：理杏仁限流；方式 A 已内置退避重试，仍失败时可加大请求间隔、减少 `--days` 或分批跑 `companies.csv`。
- **返回空 `data`**：检查股票代码是否为该接口支持的 A 股、日期区间内是否有交易日；非金融接口不适用于金融类标的时需换接口。
- **切片结果不对 / 为空**：确认已在「知识库根目录」执行 `extract_recent_data.py`，且该公司 `01_基本面数据/01_估值分析/`（及参与切片的 02–06 模块）下已有带 `日期` 列的新 CSV；若移动过仓库路径，先修正脚本内 `root`。

## 维护者可选改进（尚未实现，按需采纳）

1. **`generate_wide_valuation.py`**：为 `fetch_dataset` 增加与 `batch_update_recent_wide.py` 中 `post_api` 类似的 **429 退避重试**，降低长区间全量拉取失败率。
2. **`extract_recent_data.py`**：将硬编码的 `root = Path("/Users/...")` 改为 `Path(__file__).resolve().parents[n]` 或环境变量（如 `LICAI_KB_ROOT`），避免换机失效。
3. **扩展批量输出**：若需把 PEG、PEV 等纳入自动化，在弄清对应 `metricsList` 字段名与文件名规范后，在 `batch_update_recent_wide.py` 的 `mapping` 中追加一项并回归测试。
4. **`companies.csv` 位置**：建议在知识库根目录固定一份示例（如 `companies.example.csv`），并在 skill 中引用，减少路径歧义。

## 下次你应该怎么说（对话指令范例）

你可以直接对我说其中之一：

- “用理杏仁 token 更新 `companies.csv` 里的所有公司：拉最近90天宽表（y10分位点）到 `01_基本面数据/01_估值分析`，02–05 财务进对应子目录，然后刷新并回写 `01_基本面数据/00_最近一月数据`。”
- “用环境变量 `LIXINGER_TOKEN` 执行方式A，`--days 90`、`--clean-existing`，再跑方式 C，最后跑 `extract_recent_data.py`。”

