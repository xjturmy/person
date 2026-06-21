# 理杏仁开放 API 接口摘录（与仓库脚本一致）

> **声明**：以下内容根据当前知识库内脚本整理，**不构成官方文档**。正式字段、权限与计费以理杏仁官网 **开放 API 文档** 为准：  
> **<https://www.lixinger.com/open/api/>**  
> Token 申请：**<https://www.lixinger.com/open/api/token>**（路径以官网为准）

---

## 1. 通用约定

| 项目 | 说明 |
|------|------|
| Base URL | `https://open.lixinger.com` |
| 请求方式 | `POST`，请求体为 **JSON**（`Content-Type: application/json`） |
| 鉴权 | 请求 JSON 内字段 **`token`**（字符串） |
| 成功响应 | 常见结构：`{"code": 1, "data": [...]}`（脚本以 `code == 1` 为成功） |
| 失败 | `code` 非 `1` 或 HTTP 4xx/5xx；**HTTP 429** 表示限流，需退避重试 |
| 股票代码 | A 股一般为 **6 位**字符串，如 `"002050"`、`"600519"` |

---

## 2. 非金融公司 · 日频基本面

**URL（固定）**

```text
https://open.lixinger.com/api/cn/company/fundamental/non_financial
```

**适用**：非金融类 A 股公司日频行情/市值/估值指标（脚本中的「估值宽表」）。金融类标的需换用官网其它接口（本仓库脚本未覆盖）。

### 2.1 请求体字段（脚本实际使用）

| 字段 | 类型 | 说明 |
|------|------|------|
| `token` | string | 开放 API Token |
| `stockCodes` | string[] | 股票代码数组，如 `["002050"]`；批量统计快照时可多个 |
| `startDate` | string | 区间起始 `YYYY-MM-DD`（拉日频序列时） |
| `endDate` | string | 区间结束 `YYYY-MM-DD` |
| `date` | string | 单日 `YYYY-MM-DD`（**仅统计快照**请求时使用，与 `startDate`/`endDate` 二选一场景以脚本为准） |
| `metricsList` | string[] | 指标名列表，见下文 |

### 2.2 日频序列常用 `metricsList`（`batch_update_recent_wide.py` · `fetch_recent_series`）

```text
sp, mc, cmc, ecmc, pe_ttm, d_pe_ttm, pb, pb_wo_gw, ps_ttm, dyr
```

含义概览（以官网为准）：

- `sp`：股价相关  
- `mc` / `cmc` / `ecmc`：市值 / 流通市值 / 自由流通市值  
- `pe_ttm`、`d_pe_ttm`：PE-TTM、扣非 PE-TTM  
- `pb`、`pb_wo_gw`：PB、剔除商誉 PB  
- `ps_ttm`：PS-TTM  
- `dyr`：股息率  

### 2.3 分位点统计字段（`stats-window`：如 `y10`）

在单日/批量快照中，除上述基础指标外，脚本会请求 **分位点相关 metrics**，命名模式为：

```text
{指标名}.{统计窗口}.cvpos
{指标名}.{统计窗口}.q8v
{指标名}.{统计窗口}.q5v
{指标名}.{统计窗口}.q2v
```

- **统计窗口**脚本可选：`fs`、`y20`、`y10`、`y5`、`y3`、`y1`（与 CLI `--stats-window` 一致）  
- 指标名示例：`pe_ttm`、`pb`、`ps_ttm` 等  
- **含义概览**（与宽表列名对应）：`cvpos`≈分位点；`q8v`/`q5v`/`q2v`≈80%/50%/20% 分位点数值（具体定义以官网为准）

`fetch_stats_snapshot` 中还会在 `metricsList` 里加入 `sp`、`mc` 等与快照行展示相关的字段，以接口返回为准。

### 2.4 `generate_wide_valuation.py` 中较长 `metricsList` 示例

全历史拉取时会包含上述日频指标及 `pe_ttm.y10.*`、`pb.y10.*` 等 **y10 统计字段**（见脚本内 `metrics` 列表）。扩展时请对照官网 **metrics 名称**，避免拼写错误。

---

## 3. 财务报表接口（按行业分类）

**URL 模式**

```text
https://open.lixinger.com/api/cn/company/fs/{category}
```

**`{category}` 取值（脚本支持）**

| category | 说明 |
|----------|------|
| `non_financial` | 非金融（默认） |
| `bank` | 银行 |
| `security` | 证券 |
| `insurance` | 保险 |
| `other_financial` | 其它金融 |

### 3.1 请求体字段（`batch_update_fs_modules.py`）

| 字段 | 说明 |
|------|------|
| `token` | Token |
| `stockCodes` | 如 `["600519"]` |
| `startDate` / `endDate` | `YYYY-MM-DD` |
| `metricsList` | 财报指标名数组（脚本按模块合并请求） |

### 3.2 当前脚本内置指标（`metricsList` 中出现的 id）

**02 盈利**：`q.m.roe.ttm`、`q.m.roa.ttm`、`q.m.gp_m.ttm`、`q.m.np_s_r.ttm`  

**03 成长**：`q.ps.oi.t`、`q.ps.oi.t_y2y`、`q.ps.npatoshopc.t`、`q.ps.npatoshopc.t_y2y`、`q.ps.beps.t`、`q.ps.beps.t_y2y`  

**04 现金流**：`q.cfs.ncffoa.t`、`q.cfs.ncffoa.t_y2y`、`q.m.fcf.ttm`、`q.m.ncffoa_np_r.ttm`  

**05 安全**：`q.m.tl_ta_r.t`、`q.m.lwi_ta_r.t`、`q.m.c_r.t`、`q.m.q_r.t`  

部分金融类 `category` 下个别指标会被脚本排除（接口不支持），见 `batch_update_fs_modules.py` 中 `CATEGORY_EXCLUDED_METRICS`。

---

## 4. 响应与数据行（脚本侧）

- 成功时 `data` 一般为 **对象数组**，元素含 `date`、`stockCode` 及嵌套指标字段（与 `metricsList` 及官网字段定义一致）。  
- 脚本将嵌套字段展平或按 `metric_key` 取数后写入 CSV；详情见各 `*.py` 内 `nested_get` / 字典访问。

---

## 5. 限流与重试（脚本行为）

- **HTTP 429**：指数退避等待后重试。  
- 其它网络错误：同样退避；具体次数与超时见各脚本。

---

## 6. 安全提示

- **不要将 Token 提交到 Git、不要发给他人、不要写入本摘录以外的公开文档。**  
- 推荐使用环境变量：`export LIXINGER_TOKEN="..."`  

---

*本摘录随仓库脚本更新；若与官网冲突，以理杏仁官方为准。*
