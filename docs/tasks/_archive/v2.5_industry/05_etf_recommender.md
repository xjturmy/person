---
name: 05_etf_recommender · ETF 推荐引擎
covers: E3
priority: Wave 2(依赖 01 industry_master.yaml + industry_etf_mapping.yaml + etf.duckdb)
estimate: ~2h
agent: agent-etf-rec
---

# 任务包 05 · ETF 推荐引擎(E3)

> 给定行业 → 读 industry_master.etf_codes + industry_etf_mapping.yaml → etf.duckdb 校验流动性/1y 涨跌 → Top 3 ETF + 选择建议(主题 vs 龙头 vs 红利)。

---

## 📦 交付物

### 主模块 `.tools/dashboard/etf_recommender.py`(~150-200 行)

```python
from dataclasses import dataclass
from pathlib import Path
import yaml, duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDUSTRY_MASTER = PROJECT_ROOT / ".config" / "industry_master.yaml"
ETF_MAPPING = PROJECT_ROOT / ".tools" / "rules" / "industry_etf_mapping.yaml"
ETF_DB = PROJECT_ROOT / "data" / "etf.duckdb"


@dataclass
class ETFCandidate:
    code: str
    name: str
    theme: str             # 主题 / 龙头 / 红利(从 mapping yaml)
    fund_type: str | None  # etf_meta.etf_type
    last_close: float | None
    return_1y: float | None        # 1 年涨幅(0.18 = 18%)
    avg_turnover_60d: float | None # 60 日均换手(流动性代理 — 越大越好)
    liquidity_score: float         # 0-100 综合流动性(基于 turnover 60d 在所有 35 ETF 内的分位)
    rationale: str                 # 一句推荐理由
    layer: str | None = None       # defensive / offensive(从 mapping yaml)
    target_pct: tuple | None = None  # 配置区间 [%min, %max]


def recommend(industry: str, top_n: int = 3) -> list[ETFCandidate]:
    """主入口:
    1. 读 industry_master.yaml.industries[name == industry].etf_codes
    2. 同时读 industry_etf_mapping.yaml.mapping[industry==industry] 拿 layer/target_pct + 每只 ETF 的 theme/rationale
    3. 对每只 ETF 调 etf.duckdb 拿 last_close / return_1y / avg_turnover_60d
    4. 算 liquidity_score(60 日均换手在 35 ETF 全池的分位 0-100)
    5. 排序:layer 优先匹配当前周期 → liquidity_score 降序 → 取 Top N
    返回 list[ETFCandidate]
    """
    ...


def list_all_recommendations() -> dict[str, list[ETFCandidate]]:
    """所有 industry_etf_mapping 里的行业,各推 Top 3"""
    ...
```

#### 实现要点

**Step 1 · 读 yaml**:
- 双 yaml 都读,以 `industry_etf_mapping.yaml.mapping` 为主(更详细的 theme/rationale)
- `industry_master.yaml.etf_codes` 作 fallback(若 mapping 没记录此行业)

**Step 2 · etf.duckdb 数据**:
- `last_close`: `SELECT close FROM etf_prices WHERE etf_code=? ORDER BY date DESC LIMIT 1`
- `return_1y`: 当前 close / 365 天前 close - 1(可能不严格,选最近的有效日)
- `avg_turnover_60d`: `SELECT avg(turnover) FROM etf_prices WHERE etf_code=? AND date >= today - 60d`
- 若 ETF 不在 etf.duckdb,字段全 None,rationale 加 "数据未入库"

**Step 3 · liquidity_score**:
- 全 35 ETF 算 60 日均 turnover 的百分位排名
- 用 numpy 算 percentileofscore 或 SQL `PERCENT_RANK()`

**Step 4 · 排序逻辑**:
- 简化版:`liquidity_score` 降序;取 Top N
- 增强版(可选):layer 匹配 current_phase 加权(萧条期 → defensive 优先)

**Step 5 · rationale 模板**:
- 优先用 mapping yaml 里的 `rationale`(用户自己写过)
- 没有则自动:`"{theme}型 / 1y {return_1y:+.1%} / 流动性分位 {liquidity_score:.0f}"`

#### 边界保护

- 行业未在两个 yaml 中找到 → 返回空 list
- ETF code 在 yaml 但不在 etf.duckdb → ETFCandidate(数据 None, rationale="数据未入库")
- etf.duckdb 完全打不开 → 返回 yaml 里的静态信息,数据字段 None

---

### 测试 `.tools/dashboard/test_etf_recommender.py`(8-10 项)

```python
from tools.dashboard.etf_recommender import ETFCandidate, recommend, list_all_recommendations

def test_recommend_returns_list():
    r = recommend("白酒", top_n=3)
    assert isinstance(r, list)
    if r:
        assert isinstance(r[0], ETFCandidate)

def test_recommend_baijiu_at_least_one():
    r = recommend("白酒", top_n=3)
    assert len(r) >= 1

def test_recommend_unknown_industry_returns_empty():
    r = recommend("不存在XYZ", top_n=3)
    assert r == []

def test_recommend_etf_data_or_none():
    r = recommend("白酒", top_n=3)
    if r:
        c = r[0]
        # 要么有数据,要么明确标 None
        assert c.last_close is None or c.last_close > 0
        assert c.return_1y is None or -1 < c.return_1y < 5

def test_list_all_recommendations_returns_dict():
    d = list_all_recommendations()
    assert isinstance(d, dict)
    assert len(d) >= 8

# ... 3-5 项扩展
```

---

## 🛑 文件边界

- `.tools/dashboard/etf_recommender.py`(新建)
- `.tools/dashboard/test_etf_recommender.py`(新建)

**不动**:任何 yaml(yaml 由 01_knowledge agent 产出,本 agent 只读)/ 任何其他 .py

---

## ✅ 完成判定

```bash
cd /Users/gongyong/Desktop/Keyi/preson && source .venv/bin/activate

python3 -c "
import sys; sys.path.insert(0, '.')
from tools.dashboard.etf_recommender import recommend, list_all_recommendations
for ind in ['白酒','股份制银行','保险','化学制药','电池','通信设备','白色家电','饮料乳品']:
    r = recommend(ind, top_n=3)
    print(f'{ind}: {len(r)} ETF', [(c.code, c.name, c.theme, f'{c.return_1y:+.1%}' if c.return_1y else '?') for c in r])
"

pytest .tools/dashboard/test_etf_recommender.py -v
```

8/8 行业不报错;白酒至少 1 只;测试 8/8 过。

---

## 📚 参考

- [README.md 接口契约 G](README.md)
- 依赖:01_knowledge.md 产出的 `industry_master.yaml` 和 `industry_etf_mapping.yaml`
- etf.duckdb:`etf_meta`(etf_code/etf_name/etf_type/last_update)+ `etf_prices`(date/ohlcv/turnover/pct_change),35 ETF × 16940 行
- 记忆 [project_etf_peers_overlay.md](../../.claude/projects/-Users-gongyong-Desktop-Keyi-preson/memory/project_etf_peers_overlay.md)

---

## ⚠️ 已知坑

- ETF 主题 / 龙头 / 红利 是 yaml 自填字段,本引擎不去推断(数据池不够)
- 不要试图算"跟踪误差"(没数据,需要基准指数对比);留 None
- 不要试图爬费率(35 ETF 没基金费率字段);留 None
- liquidity_score 用 turnover 列(成交额),不要用 volume(成交量,单位差异)
- etf_prices 的 date 用 DATE 类型,365 天前用 `current_date - INTERVAL 365 DAY`
- 不要假设 mapping 里所有 ETF 都在 etf.duckdb 里(可能是知识库写的代码不存在);降级返回数据 None
