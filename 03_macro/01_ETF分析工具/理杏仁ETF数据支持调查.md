# 理杏仁 ETF 数据支持调查报告

> 调查时间：2026-04-23  
> 调查人员：Claude Code  
> 调查范围：理杏仁开放平台 API 对 ETF 数据的支持情况

---

## 📋 调查摘要

### 关键发现

| 功能 | 支持 | API | 备注 |
|------|------|-----|------|
| **ETF基本信息** | ❌ | 基金概况 | 不提供 |
| **ETF成分股列表** | ❌ | 基金成分股 | 不提供 |
| **指数成分股** | ✅ | index/constituents | **推荐方案** |
| **成分股财务数据** | ✅ | company/fundamental/non_financial | 已可用 |

### 结论

✅ **可以获取 ETF 相关数据**，但需要通过**间接方式**：
1. 利用 ETF 跟踪指数的特性
2. 通过 **指数代码** 获取成分股
3. 通过 **股票代码** 获取财务指标

---

## 🔍 详细调查结果

### 1. ❌ 基金概况 API

**URL**: `https://open.lixinger.com/api/cn/fund/profile`

**预期用途**: 获取 ETF 的基本信息（名称、代码、规模、管理公司等）

**调查结果**: **不支持**
- API 端点不存在
- 理杏仁开放平台不提供此接口

**推荐替代方案**: 维护本地 JSON 配置文件存储 ETF 基本信息

---

### 2. ❌ 基金成分股 API

**URL**: `https://open.lixinger.com/api/cn/fund/constituents`

**预期用途**: 获取 ETF 的成分股及权重

**调查结果**: **不支持**
- API 端点返回 "api is not found"
- 理杏仁不提供专门的基金成分股接口

**推荐替代方案**: 通过 ETF 跟踪的**指数 API** 获取成分股

---

### 3. ✅ 指数成分股 API

**URL**: `https://open.lixinger.com/api/cn/index/constituents`

**功能**: 获取指数的所有成分股及权重

**调查结果**: **完全支持** ✅

#### 参数示例

```json
{
  "token": "YOUR_TOKEN",
  "code": "399006"
}
```

#### 返回数据示例

```json
{
  "code": 1,
  "data": [
    {
      "code": "300750",
      "name": "宁德时代",
      "weight": 10.25,
      ...其他字段...
    },
    ...更多成分股...
  ]
}
```

#### 返回字段说明

| 字段 | 说明 | 示例 |
|------|------|------|
| code | 股票代码 | 300750 |
| name | 股票名称 | 宁德时代 |
| weight | 权重（%） | 10.25 |
| ... | 其他字段 | ... |

**应用场景**: 
- ETF 159915（创业板）跟踪指数 399006（创业板指数）
- 通过指数 API 获取创业板所有成分股

---

### 4. ✅ 公司基本面 API

**URL**: `https://open.lixinger.com/api/cn/company/fundamental/non_financial`

**功能**: 获取股票的财务指标（PE、PB、ROE 等）

**调查结果**: **完全支持** ✅

#### 参数示例

```json
{
  "token": "YOUR_TOKEN",
  "stockCodes": ["300750", "300760"],
  "startDate": "2026-04-20",
  "endDate": "2026-04-23",
  "metricsList": ["sp", "pe_ttm", "pb", "ps_ttm", "dyr"]
}
```

#### 返回字段

| 字段 | 说明 |
|------|------|
| pe_ttm | 市盈率（TTM） |
| pb | 市净率 |
| ps_ttm | 市销率（TTM） |
| dyr | 股息率 |
| sp | 股价 |

---

## 🎯 推荐的 ETF 数据获取方案

### 总体流程

```
维护 ETF 配置信息
         ↓
根据 ETF 跟踪的指数代码
         ↓
使用指数成分股 API 获取成分股
         ↓
使用公司基本面 API 获取成分股财务数据
         ↓
汇总生成 ETF 分析报告
```

### 具体步骤

#### 步骤 1: 维护 ETF 配置文件

**位置**: `03_macro/01_ETF分析工具/投资主题/{主题}/etf_config.json`

**文件内容**:
```json
{
  "theme": "新能源",
  "etfs": [
    {
      "code": "516030",
      "name": "华夏新能源汽车ETF",
      "index_code": "399417",
      "index_name": "新能源汽车指数",
      "manager": "华夏基金",
      "inception_date": "2021-12-01"
    },
    {
      "code": "515790",
      "name": "华夏科创板50ETF",
      "index_code": "000688",
      "index_name": "科创板50指数",
      "manager": "华夏基金",
      "inception_date": "2020-07-22"
    }
  ]
}
```

#### 步骤 2: 通过指数 API 获取成分股

**脚本**: `.tools/fetch_etf_constituents.py`

```python
# 伪代码
for etf in etf_config["etfs"]:
    index_code = etf["index_code"]
    constituents = api_call(
        "index/constituents",
        token=token,
        code=index_code
    )
    # 保存为 constituents.csv
```

**输出**: `constituents.csv`
```
代码,名称,权重
300750,宁德时代,10.25
300014,亿纬锂能,8.50
...
```

#### 步骤 3: 获取成分股财务数据

**脚本**: `.tools/fetch_etf_constituents_fundamentals.py`

```python
# 伪代码
stock_codes = [c["代码"] for c in constituents]
fundamentals = api_call(
    "company/fundamental/non_financial",
    token=token,
    stockCodes=stock_codes,
    metricsList=["pe_ttm", "pb", "dyr", "roe"]
)
# 保存为 fundamentals.csv
```

**输出**: `fundamentals.csv`
```
代码,名称,PE,PB,股息率,ROE
300750,宁德时代,25.3,4.2,0.5%,15%
300014,亿纬锂能,18.5,3.1,2.1%,12%
...
```

---

## 📂 推荐的文件结构

```
03_macro/01_ETF分析工具/
├── 投资主题/
│   ├── 新能源/
│   │   ├── 说明.md                    ← 现有
│   │   ├── etf_config.json            ← 新增：ETF配置
│   │   ├── constituents.csv           ← 新增：成分股列表
│   │   └── fundamentals.csv           ← 新增：成分股财务数据
│   │
│   ├── 机器人/
│   │   ├── 说明.md
│   │   ├── etf_config.json
│   │   ├── constituents.csv
│   │   └── fundamentals.csv
│   │
│   ├── 消费/
│   │   └── ...
│   │
│   └── 芯片半导体/
│       └── ...
│
├── 模板/
│   ├── ETF分析模板.md
│   └── etf_config_template.json       ← 新增：配置模板
│
└── 说明.md
```

---

## 🛠️ 数据更新流程

### 更新频率建议

| 数据 | 频率 | 方式 |
|------|------|------|
| ETF 配置 | 按需 | 手工维护 |
| 成分股列表 | 季度 | 脚本自动更新 |
| 财务数据 | 月度 | 脚本自动更新 |

### 自动更新脚本

创建 `.tools/update_etf_data.py`:

```bash
# 用法
python3 .tools/update_etf_data.py \
  --theme 新能源 \
  --token YOUR_TOKEN \
  --output-dir 03_macro/01_ETF分析工具/投资主题/
```

---

## 💡 注意事项

### 1. 指数与 ETF 的对应关系

- 每个 ETF 都跟踪一个或多个指数
- 有的 ETF 跟踪主要指数（如沪深300），有的跟踪小众指数（如新能源汽车）
- 必须**准确维护** ETF 与指数的映射关系

**常见映射**:
```
159915 → 399006 (创业板指数)
510310 → 000300 (沪深300指数)
515790 → 000688 (科创板50指数)
516030 → 399417 (新能源汽车指数)
```

### 2. 成分股变化

- 指数成分股会定期调整（通常按照既定规则）
- 需要**定期更新**成分股列表
- 可在下载时加上日期戳，便于追踪变化

### 3. 权重变化

- 指数内成分股的权重会动态变化
- 权重数据可用于分析基金的风险集中度
- 可追踪权重变化识别行业轮动机会

---

## 📊 数据获取脚本示例

### 快速获取指数成分股

```bash
# 示例：获取创业板指数成分股
curl -X POST https://open.lixinger.com/api/cn/index/constituents \
  -H "Content-Type: application/json" \
  -d '{
    "token": "YOUR_TOKEN",
    "code": "399006"
  }'
```

### 快速获取成分股财务数据

```bash
# 示例：获取多个股票的PE、PB数据
curl -X POST https://open.lixinger.com/api/cn/company/fundamental/non_financial \
  -H "Content-Type: application/json" \
  -d '{
    "token": "YOUR_TOKEN",
    "stockCodes": ["300750", "300014", "300122"],
    "endDate": "2026-04-23",
    "metricsList": ["pe_ttm", "pb", "dyr"]
  }'
```

---

## 🔗 相关资源

- **理杏仁开放平台**: https://www.lixinger.com/open/
- **指数成分股API文档**: https://www.lixinger.com/open/api/doc?api-key=cn/index/constituents
- **公司基本面API文档**: https://www.lixinger.com/open/api/doc?api-key=cn/company/fundamental/non_financial

---

## 📝 后续工作建议

- [ ] 创建 `etf_config.json` 模板
- [ ] 开发 `update_etf_data.py` 脚本
- [ ] 为各主题补充 ETF 配置信息
- [ ] 建立定期更新机制
- [ ] 在 ETF 分析报告中集成成分股数据

---

**最后更新**: 2026-04-23  
**状态**: ✅ 调查完成，方案可行
