---
name: company-financial-report-download
description: 公司财报下载：A股巨潮资讯、港股披露易定期报告 PDF；输出目录为档案库 `02_公司财报/`，含批量脚本与 Q1–Q4 命名约定。Use when 用户需要下载财报、A股/港股定期报告 PDF、年报半年报季报、巨潮/cninfo/披露易/hkexnews、财报批量拉取。
---

> **分享版说明**  
> - **巨潮 POST 表单、静态域名、orgId 清单、披露易检索参数**等，见同目录 **[巨潮与披露易接口摘录.md](./巨潮与披露易接口摘录.md)**。  
> - 请将整个 `company-financial-report-download` 文件夹放入知识库 **`.cursor/skills/company-financial-report-download/`**，在**知识库根目录**执行下文命令；批量下载依赖 `02_公司档案库/_财报批量下载/companies.csv`（需自行准备）。  
> - 文中指向其它 skill 的相对链接在分享包中可能无效，以本目录 `SKILL.md` 与接口摘录为准。

# 公司财报下载（A股巨潮 + 港股披露易）

**数据源**：

- A股：法定披露平台 [巨潮资讯网](http://www.cninfo.com.cn/new/index.jsp)
- 港股：港交所披露易 [HKEXnews](https://www.hkexnews.hk/index_c.htm)

**与公司档案库的路径约定**（与 `00_资料索引.md`、现行目录一致）：

- 财报 PDF 与 `财报下载映射.md` 放在：**`02_公司档案库/{编号}_{公司名}/02_公司财报/`**
- 定量指标（理杏仁等）在同级 **`01_基本面数据/`**，二者不要混放。
- 历史资料中若仍存在 **`90_财报/`** 旧目录，可逐步迁移到 `02_公司财报/`；新下载一律使用 **`02_公司财报/`**。

本技能覆盖**手工下载**与（A股）**接口批量下载**。

## 合规与频率

- 仅用于个人研究、档案整理等合法用途；遵守网站声明与版权要求。
- 批量请求时**限速**（建议每次请求间隔 ≥0.5～1 秒），避免对服务器造成压力；失败时退避重试。

## 方式一：浏览器（适合少量、抽查）

1. 打开 [巨潮首页](http://www.cninfo.com.cn/new/index.jsp)。
2. 用顶部导航进入 **「公告」→ 对应板块（如深市/沪市）**，或通过 **「个股 F10 / 公司公告」** 进入单家公司披露页（也可直接搜索公司名/代码）。
3. 在公告列表中筛选 **「年报」「半年报」「一季报」「三季报」** 等分类（站点可能将分类命名为「年度报告」「半年度报告」等）。
4. 点开目标公告，在详情页下载 **PDF**（正文附件通常为 PDF）。

若找不到 `orgId`，可改用方式二先查列表，再在网页按标题核对。

## 方式二：公开查询接口 + 静态文件下载（适合批量）

巨潮前端使用公告查询接口返回列表，附件路径在返回 JSON 的 `adjunctUrl` 字段；文件托管在静态域名。

### 1）必备参数：`stock` 与 `column`

- **`stock`**：格式为 `{证券代码},{orgId}`，例如 `600519,gssh0600519`（**英文逗号**）。
- **`orgId`**：机构编码，**沪市/深市 A 股均可在同一份股票清单中查到**（见下）。
- **`column`**：市场板块，与页面 URL 一致，常见取值：
  - 深市：`szse`
  - 沪市：`sse`
  - 北交所等以网站当前页面为准（接口行为若变更，以浏览器开发者工具中实际请求为准）。

### 2）查询公告列表（POST）

- **URL**：`http://www.cninfo.com.cn/new/hisAnnouncement/query`
- **请求头**：建议包含 `X-Requested-With: XMLHttpRequest`；`Content-Type` 使用 `application/x-www-form-urlencoded`（与浏览器一致即可）。
- **常用表单字段**（名称需与站点一致，缺省可留空）：

| 字段 | 说明 |
|------|------|
| `pageNum` | 页码，从 1 开始 |
| `pageSize` | 每页条数，如 30 |
| `column` | 见上，`szse` / `sse` 等 |
| `tabName` | 全文查询一般为 `fulltext` |
| `plate` | 常为空 |
| `stock` | `代码,orgId` |
| `searchkey` | 标题关键词，可空 |
| `secid` | 可空 |
| `category` | 公告分类 key，财报类见下表 |
| `trade` | 可空 |
| `seDate` | 公告日期范围 `YYYY-MM-DD~YYYY-MM-DD` |
| `sortName`、`sortType` | 可空 |
| `isHLtitle` | 如 `true` |

**定期报告类 `category`（深沪常用，后缀 `_szsh` 表示深沪合并分类）**：

| category | 用途 |
|----------|------|
| `category_ndbg_szsh` | 年度报告 |
| `category_bndbg_szsh` | 半年度报告 |
| `category_yjdbg_szsh` | 一季度报告 |
| `category_sjdbg_szsh` | 三季度报告 |

更全的分类 key 以站点前端为准，可查阅（若链接失效则在站内搜索同路径）：  
`http://www.cninfo.com.cn/new/js/app/disclosure/notice/history-notice.js`

**响应**：JSON 中 `announcements` 数组含 `announcementTitle`、`announcementTime`（毫秒时间戳）、`adjunctUrl`、`adjunctType` 等。

### 3）下载附件 URL

- 若 `adjunctUrl` 为非空相对路径，则完整下载地址为：  
  **`http://static.cninfo.com.cn/` + `adjunctUrl`**
- 使用 GET 下载二进制流保存为 `.PDF`（或响应实际类型）。

### 4）解析 `orgId`（A 股清单）

- **URL**：`http://www.cninfo.com.cn/new/data/szse_stock.json`
- 解析 JSON 中 `stockList`：`code` 为证券代码，`orgId` 为机构 id（沪市/深市股票均可能出现在该列表中，按 `code` 匹配即可）。

代码建议左补零为 6 位再匹配（如 `519` → `600519` 视具体情况；A 股一般为 6 位数字字符串）。

### 5）一行 curl 示例（仅作联调）

查询沪市某公司年报分类（请替换 `stock` 与日期）：

```bash
curl -sS -X POST "http://www.cninfo.com.cn/new/hisAnnouncement/query" \
  -H "Content-Type: application/x-www-form-urlencoded; charset=UTF-8" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d "pageNum=1&pageSize=5&column=sse&tabName=fulltext&plate=&stock=600519,gssh0600519&searchkey=&secid=&category=category_ndbg_szsh&trade=&seDate=2024-01-01~2025-12-31&sortName=&sortType=&isHLtitle=true"
```

## 方式三：项目内脚本（推荐重复执行）

本技能目录下提供 `scripts/download_cninfo_reports.py`：根据**股票代码**自动查 `orgId`、分页拉取公告并下载 PDF 到指定目录。

```bash
python3 ".cursor/skills/company-financial-report-download/scripts/download_cninfo_reports.py" \
  --code 600519 \
  --category category_ndbg_szsh \
  --start-date 2024-01-01 \
  --end-date 2025-12-31 \
  --out-dir "02_公司档案库/XX_公司名/02_公司财报"
```

依赖：Python 3 标准库即可（`urllib`）。若运行环境无网络，无法拉取清单与文件。

## 港股：披露易（HKEXnews）财报下载

适用：港股上市公司（年报 `Annual Report`、中期报告 `Interim Report`、年度/中期业绩公告 `Results Announcement` 等）。

### 方式一：浏览器手工下载（推荐）

1. 打开 [披露易首页](https://www.hkexnews.hk/index_c.htm)。
2. 进入“上市公司公告”检索页（Title Search）。
3. 输入公司名或股份代号（如 `02097`），筛选公告范围后搜索。
4. 在结果中优先定位：
   - `Annual Report xxxx`
   - `Interim Report xxxx`
   - `ANNUAL RESULTS ANNOUNCEMENT ...`
   - `INTERIM RESULTS ANNOUNCEMENT ...`
5. 点击对应 PDF 下载，保存到 `02_公司档案库/XX_公司名/02_公司财报/`。

### 方式二：可复用检索链接（高效）

披露易支持通过查询参数直达公司公告结果页；核心参数：

- `lang`: `EN` 或 `ZH`
- `market`: 主板通常为 `SEHK`
- `stockId`: 披露易内部公司ID（比仅用代码更稳定）
- `category=0`: 标题检索默认分类

示例（蜜雪集团）：

```text
https://www1.hkexnews.hk/search/titlesearch.xhtml?lang=EN&market=SEHK&stockId=1000249228&category=0
```

说明：

- 英文页通常更容易直接看到完整标题与财报英文名（`Annual Report` / `Interim Report`）。
- 中文页可用 `lang=ZH`，用于核对公司中文简称与中文公告标题。
- 如需其他公司，先在网页检索获取其 `stockId`，再保存为长期可复用链接。

### 港股文件命名与映射建议（与档案库对齐）

- 标准命名建议：
  - `公司名_YYYY年年度报告.pdf`
  - `公司名_YYYY年中期报告.pdf`
  - `公司名_YYYY年年度业绩公告.pdf`
  - `公司名_YYYY年中期业绩公告.pdf`
- 建议维护 `02_公司财报/财报下载映射.md`，至少记录：
  - 报告键（如 `2024_AR`、`2025_IR`、`2025_ARA`、`2025_IRA`）
  - 标准文件名
  - 公告ID（如 `2025042301969`）
  - 原始文件名
  - 公告标题
  - 下载 URL

### 港股常见注意点

- 同一期可能存在多语言或多版本（如 `_c.pdf`、英文版、修订版），应统一保留一份“标准命名主文件”，其余在映射中备注。
- `Results Announcement` 与 `Report` 都有价值：前者更早披露关键财务数据，后者信息更完整。
- 若检索结果很多，先按“报告关键词 + 年份”筛选，再下载，避免月报/通函干扰。

## 与公司档案库的配合（统一为 Q1–Q4 口径）

- 下载的 PDF 放入该公司目录下的 **`02_公司财报/`**（与个人知识库「公司档案库」目录约定一致即可）。
- 财报在档案库内一律按季度归档，统一使用 `Q1/Q2/Q3/Q4`，**不使用 `H1` 与 `ANNUAL`**。
- 脚本保存标准化命名：`公司名_年份Qx财报.pdf`。示例：`新华保险_2017年Q1财报.pdf`、`新华保险_2017年Q4财报.pdf`。
- 同目录自动维护 `财报下载映射.md`，记录：`报告键(年份+类型)`、标准文件名、公告ID、公告标题、原始文件名（`标题_announcementId.pdf`）和下载 URL。
- 口径映射规则（用于巨潮分类与档案命名对齐）：
  - `category_yjdbg_szsh`（一季报）→ `Q1`
  - `category_bndbg_szsh`（半年度）→ `Q2`
  - `category_sjdbg_szsh`（三季报）→ `Q3`
  - `category_ndbg_szsh`（年度）→ `Q4`
- 清理规则：若目录存在原始命名（如 `xxxx年第一/第三季度报告正文_*.pdf`）或历史命名（`H1`/`年报`），保留标准命名文件并删除重复文件。

### 档案库批量：最近 N 年定期报告（推荐）

面向 `02_公司档案库/` 下已建档公司，一键拉取**最近 10 年**（可调）内的定期报告 PDF，并写入各公司 **`02_公司财报/`**。

**默认包含四类**（与 A 股常规披露一致；巨潮无单独「二季报」分类，但档案库中映射为 `Q2`）：

| 档案库季度 | `category` | 公告类型 |
|------|------------|------|
| `Q1` | `category_yjdbg_szsh` | 一季度报告 |
| `Q2` | `category_bndbg_szsh` | 半年度报告 |
| `Q3` | `category_sjdbg_szsh` | 三季度报告 |
| `Q4` | `category_ndbg_szsh` | 年度报告 |

若**只要年报**，可执行时加：`--category category_ndbg_szsh`（会覆盖默认四类）。

1. **映射表**（可编辑）：`02_公司档案库/_财报批量下载/companies.csv`  
   - 列：`folder`（与档案库子文件夹名一致，如 `06_贵州茅台`）、`stock`（6 位 A 股代码）、`skip`（非空则跳过，如仅港股/无 A 股：`non-a-share`）。  
   - 仓库中另有 **`companies.md`** 时，可与 CSV 保持同一公司列表（CSV 供脚本读取；MD 便于人读备注）。
   - 新增公司时：在档案库建 `XX_公司名/` 与 **`02_公司财报/`**，再在映射表追加一行。

2. **执行**（在项目根目录 `理财资料/` 下，需联网）：

```bash
python3 ".cursor/skills/company-financial-report-download/scripts/batch_download_archive_financials.py"
```

常用参数：

| 参数 | 说明 |
|------|------|
| `--years 10` | 回溯年数，默认 10 |
| `--end-date YYYY-MM-DD` | 区间结束日，默认今天 |
| `--categories` | 逗号分隔分类，**默认四类**（档案命名映射为 `Q1/Q2/Q3/Q4`） |
| `--category category_ndbg_szsh` | **仅**下载单一分类（指定时忽略 `--categories`） |
| `--only-folder 06_贵州茅台` | 只更新一家公司 |
| `--dry-run` | 只列 URL，不写入文件 |
| `--exclude-in-title 摘要,英文版,English` | 标题含任一子串则跳过（默认即此，减少重复附件） |
| `--exclude-in-title ""` | 关闭标题过滤，下载当前分类下全部 PDF |

**增量更新（默认行为）**

- 主判定依据是 `02_公司财报/财报下载映射.md` 中的 `报告键`（如 `2017_Q1`、`2024_Q4`）：若该键已有映射且标准化文件存在，则跳过下载。
- 为兼容历史文件，脚本也会扫描 `*_announcementId.pdf` 旧命名；若命中会自动重命名为标准化文件名并写入映射。
- 同一 `报告键` 若接口返回多个候选（如全文/正文/更新后），脚本只保留一个标准化文件，并把原始文件名记录到映射。

因此反复执行批量或单公司脚本，只会**补齐缺失报告期/新披露**，不再堆积重复命名文件。

## 故障排查

| 现象 | 处理 |
|------|------|
| 列表为空 | 检查 `column` 与 `stock` 是否匹配、`seDate` 是否覆盖披露日、`category` 是否正确 |
| 下载 403/空内容 | 降低频率；检查是否需浏览器同款 User-Agent；确认 `adjunctUrl` 非空 |
| 找不到 orgId | 重新拉取 `szse_stock.json`；确认代码 6 位与板块是否正确 |

接口与页面结构可能随站点升级而变化；以浏览器开发者工具 **Network** 中实际请求为准更新参数。
