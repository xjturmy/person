---
name: 02_percentile · 行业估值分位引擎
covers: E1
priority: Wave 1(0 强依赖,数据降级)
estimate: ~2h
agent: agent-percentile
---

# 任务包 02 · 行业估值分位引擎(E1)

> 写 `.tools/dashboard/industry_percentile_engine.py`,产出 `IndustryPercentile` 数据 — 给定行业名,返回 PE/PB 中位数 + 10 年分位 + 成份股数 + 数据源。

---

## 📦 交付物

### 主模块 `.tools/dashboard/industry_percentile_engine.py`(~150-250 行)

```python
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MARKET_DB = PROJECT_ROOT / "data" / "market.duckdb"
PEERS_DB = PROJECT_ROOT / "data" / "peers.duckdb"
PRESON_DB = PROJECT_ROOT / "data" / "preson.duckdb"  # valuation 表

@dataclass
class IndustryPercentile:
    industry: str
    pe_median: float | None
    pe_percentile_10y: float | None
    pb_median: float | None
    pb_percentile_10y: float | None
    member_count: int
    as_of: date
    data_source: str  # "market.duckdb" / "peers.duckdb" / "self_only"
    notes: str = ""


def compute(industry: str) -> IndustryPercentile:
    """三级数据降级:
    1. market.duckdb(全市场快照,~5400 行)→ 行业内全部成份股 PE/PB 中位数 + 10y 分位
    2. peers.duckdb(同行池 ~80 家)→ 行业内 peers + self 成份 PE/PB 中位数,无 10y 分位
    3. preson.duckdb valuation(自选 15 家)→ 仅自选成份,只算当前 PE/PB 中位
    """
    ...
```

#### 实现要点

**Path 1 · market.duckdb**(若文件存在 + market_spot 表非空):
- `SELECT pe_dynamic, pb FROM market_spot WHERE industry=? AND snapshot_date=(SELECT max(snapshot_date) FROM market_spot)`
- median 用 `numpy.median` 或 SQL `quantile_cont(0.5)`
- 10y 分位:**当前 step-A market_spot 是单日快照表,无历史时序**,所以 10y 分位用如下两种方案之一:
  - **方案 A(推荐)**:从 [.tools/db/](../../.tools/db/) 现有 valuation 时序(`preson.duckdb` 的 `valuation` 表)按 ticker 找到行业内自选公司 PE 历史,聚合中位数后算分位
  - **方案 B(简化)**:暂返回 None,在 `notes` 字段标 "10y 分位待 step-A 累积月度时序后接入"
- `data_source = "market.duckdb"`

**Path 2 · peers.duckdb**(若 Path 1 失败):
- `SELECT pe_ttm, pb FROM peers WHERE industry=?`(确认 peers.duckdb 里有 industry 字段;若没有,通过 ticker join companies.csv 的 industry_l2)
- 同样算中位数;10y 分位走 Path 1 方案 A(用 valuation 时序)
- `data_source = "peers.duckdb"`

**Path 3 · 自选回退**:
- 读 `companies.csv` 拿到该行业的 self ticker 列表
- 从 `preson.duckdb.valuation` 拉每只最近 PE/PB → 算中位
- 10y 分位 = None
- `data_source = "self_only"` + `notes = "仅基于 N 家自选成份,行业代表性有限"`

**所有失败**:返回 `IndustryPercentile(industry, None, None, None, None, 0, today, "no_data", "无可用数据源")`

#### 必备功能

- 模块自动检测 market.duckdb 是否存在 + 表是否填充(`SELECT count(*) FROM market_spot WHERE snapshot_date >= today - 30d`)
- 所有 SQL 用 read-only 连接(`duckdb.connect(path, read_only=True)`),用完关闭(避开 WAL 锁)
- 函数对外只暴露 `compute(industry: str) -> IndustryPercentile`,内部辅助函数下划线开头

#### 缓存

不在引擎层缓存,留给 UI 层(F1/G1)用 `@st.cache_data(ttl=1800)` 包一层。

---

### 测试 `.tools/dashboard/test_industry_percentile_engine.py`(8-12 项)

```python
from tools.dashboard.industry_percentile_engine import IndustryPercentile, compute

def test_compute_baijiu_returns_dataclass():
    r = compute("白酒")
    assert isinstance(r, IndustryPercentile)
    assert r.industry == "白酒"
    assert r.member_count >= 1  # 至少茅台 + 五粮液
    assert r.data_source in ("market.duckdb", "peers.duckdb", "self_only", "no_data")

def test_compute_unknown_industry_returns_no_data():
    r = compute("不存在的行业XYZ")
    assert r.member_count == 0 or r.data_source == "no_data"

def test_compute_bank_returns_self_or_peers():
    r = compute("股份制银行")
    # 至少招行 1 家
    if r.data_source != "no_data":
        assert r.pe_median is None or r.pe_median > 0

# ... 6-8 项扩展(test_data_source_priority / test_pb_median / test_member_count_realistic / test_as_of_recent 等)
```

至少 8 项测试通过。

---

## 🛑 文件边界

- `.tools/dashboard/industry_percentile_engine.py`(新建)
- `.tools/dashboard/test_industry_percentile_engine.py`(新建)

**不动**:任何 yaml / 任何其他 .py / app.py / 数据库文件

---

## ✅ 完成判定

```bash
cd /Users/gongyong/Desktop/Keyi/preson && source .venv/bin/activate

# 离线冒烟
python3 -c "
import sys; sys.path.insert(0, '.')
from tools.dashboard.industry_percentile_engine import compute
for ind in ['白酒','股份制银行','保险','化学制药','电池','通信设备','白色家电','饮料乳品']:
    r = compute(ind)
    print(f'{ind}: {r.member_count} 家 / PE 中位 {r.pe_median} / 来源 {r.data_source}')
"

# 测试
pytest .tools/dashboard/test_industry_percentile_engine.py -v
```

8/8 行业不报错(member_count 可能为 0,但 dataclass 完整返回);测试至少 8/8 通过。

---

## 📚 参考

- [README.md 接口契约 E](README.md)
- 已有 industry_percentile.py(纯估值分位,**不是行业级**;参考代码风格)
- preson.duckdb valuation 表(549k 行 PE/PB 时序,13 家自选 10 年)
- peers.duckdb(同行池;字段需先 DESCRIBE 确认)
- market.duckdb(step-A 已建库,可能为空,代码必须降级运行)

---

## ⚠️ 已知坑

- **不要假设 market.duckdb 已抓数**;代码必须能在数据库为空时降级
- **行业字段名不一致**:companies.csv 用 `industry_l2`,peers.duckdb 字段未知(先 DESCRIBE),market.duckdb 用 `industry`(EM 行业字符串,非 SW L2)
- 当 market.duckdb 用 EM 行业时,需要做 SW L2 ↔ EM 行业映射;若映射成本高,Path 1 直接降级到 Path 2
- 10y 分位若没数据,字段填 None 不要瞎算
- DuckDB read-only 连接用完 close,避免 WAL 锁
- 测试文件用 `pytest`,断言要松(数据状态多变)
