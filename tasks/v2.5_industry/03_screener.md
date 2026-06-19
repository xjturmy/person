---
name: 03_screener · 行业 Top 7 选优(候选 ⑪ 重启)
covers: E4
priority: Wave 1(数据降级,可不等 step-A)
estimate: ~6-8h
agent: agent-screener
---

# 任务包 03 · 行业 Top 7 选优引擎(E4)

> v2.4 step-C 候选 ⑪ 重启 — 用户在 `focus_industries.yaml` 勾选 8 行业,系统按 `industry_type_map.yaml` 自动选评分规则,行业内 Top 7 公司排序输出。**复用 v2.3 已有 14 套评分 yaml,不写新规则**。

---

## 📦 交付物

### 1. `.config/focus_industries.yaml`

按 [README.md 契约 C](README.md) 默认填 8 重点行业。

### 2. `.tools/rules/industry_type_map.yaml`

按 [README.md 契约 D](README.md) 写 6 类型映射(stalwart / fast_grower / cyclical / slow_grower / bank / insurance)。

### 3. `.tools/dashboard/industry_screener.py`(~250-350 行)

```python
"""行业级 Top N 选优 — 候选 ⑪。

数据池三级降级:
  1. market.duckdb(全市场,行业全成份股,~5400 行)
  2. peers.duckdb(同行池 ~80 家)
  3. .config/companies.csv 自选 15 家

评分链路:
  1. industry_type_map.yaml 拿 type → primary/secondary masters
  2. primary 用 lynch_classifier(若 type ∈ {stalwart, fast_grower, cyclical, slow_grower})
     或 graham_bank/graham_insurance(若 type ∈ {bank, insurance})
  3. secondary 用 .tools/dashboard/screener.score_with_master 跑
  4. 加权平均 → 最终 score(0-100)

不写新评分规则;复用 .tools/dashboard/screener.py 现有入口。
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import yaml, duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FOCUS_YAML = PROJECT_ROOT / ".config" / "focus_industries.yaml"
TYPE_MAP_YAML = PROJECT_ROOT / ".tools" / "rules" / "industry_type_map.yaml"
COMPANIES_CSV = PROJECT_ROOT / ".config" / "companies.csv"
MARKET_DB = PROJECT_ROOT / "data" / "market.duckdb"
PEERS_DB = PROJECT_ROOT / "data" / "peers.duckdb"


@dataclass
class IndustryCandidate:
    ticker: str
    name: str
    score: float | None
    rating: str  # 🟢 优秀 / 🟡 合格 / 🟠 警戒 / 🔴 不及格 / ⚪ 数据不足
    reason: str  # 一句话理由
    is_owned: bool  # 在 companies.csv 自选?
    primary_master: str
    breakdown: dict  # {master: score}


def list_industry_candidates(industry: str) -> list[dict]:
    """返回该行业候选公司列表(ticker + name)。
    优先 market.duckdb;降级 peers.duckdb;再降级 companies.csv 自选。
    """
    ...


def score_company(ticker: str, scoring_type: str) -> IndustryCandidate:
    """单股评分。"""
    # 调 .tools/dashboard/screener.score_with_master / score_lynch_classifier_all
    ...


def screen_industry(industry: str, type: str, top_n: int = 7) -> pd.DataFrame:
    """单行业 Top N。
    返回 cols: rank / ticker / name / score / rating / reason / is_owned / primary_master / data_source
    """
    ...


def screen_all_focus(focus_yaml_path: str | Path = FOCUS_YAML) -> dict[str, pd.DataFrame]:
    """批量跑所有聚焦行业。"""
    ...
```

#### 实现要点

**list_industry_candidates 三级降级**:
- Path 1: `market.duckdb` 存在且非空时,`SELECT ticker, name FROM market_spot WHERE industry LIKE '%{sw_l2}%' AND total_market_cap >= market_cap_min`(行业字段 EM 风格,需做模糊匹配 / 也可拓宽到 SW L1 再 substr)
- Path 2: `peers.duckdb` 存在时(具体表名先 DESCRIBE 确认)
- Path 3: 读 `companies.csv` 过滤 industry_l2 == industry

**score_company 调用**:
- type ∈ {stalwart, fast_grower, cyclical, slow_grower}:用 `score_lynch_classifier_all` 拿 lynch 分;同时 `score_with_master(df, m)` 跑 secondary
- type ∈ {bank, insurance}:不能用 lynch_classifier(银行保险特殊);primary 直接 `score_with_master(df, "graham_bank" / "graham_insurance")`,secondary `piotroski_bank` / `piotroski_insurance`
- 加权:从 `industry_type_map.yaml` 读 weights,缺失项不计入
- reason 一句话:从分数最高 / 最低维度抽 — 例如 "ROE 22% / PE 15x / F-Score 7"

**screen_industry**:
- 拿候选 → 逐家 score_company → 排序 → Top N
- DataFrame 列必须固定(F2 Tab UI 直接读)
- 加 `data_source` 列说明数据池

**screen_all_focus**:
- 读 `focus_industries.yaml` 遍历 → 调 screen_industry
- 返回 `{industry_name: DataFrame}` dict

**性能**:
- 8 行业 × 平均 10 候选 × 每家 1-2 master = ~150 次评分,首次 < 30 秒可接受
- 不在引擎层缓存,UI 层加 `@st.cache_data(ttl=3600)`
- `lynch_classifier.classify_ticker` 已知较慢(N 秒级),要小心首次跑可能 1 分钟+

#### 边界保护

- 任何评分异常(数据缺失 / lynch_classifier 抛错)→ score=NaN, rating="⚪ 数据不足",不阻断其他公司评分
- companies.csv 行业 == 用户填写的 industry 时(例:`股份制银行` 自选 1 家招行),返回单家 + `data_source="self_only"`

---

### 4. 测试 `.tools/dashboard/test_industry_screener.py`(10-15 项)

```python
import pandas as pd
import yaml
from tools.dashboard.industry_screener import (
    IndustryCandidate, list_industry_candidates,
    score_company, screen_industry, screen_all_focus
)

def test_focus_yaml_valid():
    d = yaml.safe_load(open(".config/focus_industries.yaml"))
    assert "focus" in d and len(d["focus"]) >= 8
    assert d["top_n"] == 7

def test_type_map_yaml_valid():
    d = yaml.safe_load(open(".tools/rules/industry_type_map.yaml"))
    for t in ["stalwart","fast_grower","cyclical","slow_grower","bank","insurance"]:
        assert t in d["type_to_scoring"]

def test_list_candidates_baijiu_at_least_two_self():
    cands = list_industry_candidates("白酒")
    # 自选有茅台 + 五粮液
    tickers = {c["ticker"] for c in cands}
    assert "600519" in tickers and "000858" in tickers

def test_screen_industry_returns_dataframe():
    df = screen_industry("白酒", "stalwart", top_n=5)
    assert isinstance(df, pd.DataFrame)
    for col in ["rank","ticker","name","score","rating","reason","is_owned","primary_master","data_source"]:
        assert col in df.columns
    assert len(df) >= 1

def test_screen_industry_bank_uses_graham_bank():
    df = screen_industry("股份制银行", "bank", top_n=3)
    if not df.empty:
        assert df.iloc[0]["primary_master"] == "graham_bank"

def test_screen_all_focus_returns_dict():
    results = screen_all_focus()
    assert len(results) == 8
    for ind, df in results.items():
        assert isinstance(df, pd.DataFrame)

# ... 5-8 项扩展
```

至少 10 项测试通过。

---

## 🛑 文件边界

- `.config/focus_industries.yaml`(新建)
- `.tools/rules/industry_type_map.yaml`(新建)
- `.tools/dashboard/industry_screener.py`(新建)
- `.tools/dashboard/test_industry_screener.py`(新建)

**不动**:任何其他 yaml / 任何其他 .py / app.py

---

## ✅ 完成判定

```bash
cd /Users/gongyong/Desktop/Keyi/preson && source .venv/bin/activate

# 离线冒烟
python3 -c "
import sys; sys.path.insert(0, '.')
from tools.dashboard.industry_screener import screen_industry, screen_all_focus

# 单行业
df = screen_industry('白酒', 'stalwart', top_n=5)
print('白酒 Top 5:'); print(df[['rank','ticker','name','score','rating','reason']])
assert len(df) >= 2  # 茅台 + 五粮液

# 全聚焦
results = screen_all_focus()
print(f'8 行业全部:{list(results.keys())}')
assert len(results) == 8
"

# 测试
pytest .tools/dashboard/test_industry_screener.py -v
```

10/10+ 测试通过;白酒至少 2 家(茅台 + 五粮液),银行至少 1 家(招行)。

---

## 📚 参考

- [README.md 接口契约 C/D/H](README.md)
- 已有评分入口 [.tools/dashboard/screener.py:300-413](../../.tools/dashboard/screener.py)
- 林奇分类器 [.tools/dashboard/lynch_classifier.py](../../.tools/dashboard/lynch_classifier.py)
- 14 套评分 yaml [.tools/rules/](../../.tools/rules/)
- v2.4 走偏的 step-C 教训 [../v2.4_p0/step-C_industry_focus.md](../v2.4_p0/step-C_industry_focus.md)
- 记忆 [project_master_scoring_system.md](../../.claude/projects/-Users-gongyong-Desktop-Keyi-preson/memory/project_master_scoring_system.md)

---

## ⚠️ 已知坑

- `lynch_classifier.classify_ticker` 首次很慢(读 DuckDB + 算分类),~3-5s/家
- bank/insurance 不能走 lynch_classifier,会抛错;**type 必须在 type_map 切对**
- `score_with_master` 数据缺失时返回 score=NaN,UI 别 sort 时崩
- `data_source` 字段非常重要,UI 要明确标注"数据池来自:自选 15 家"还是"全市场"
- 测试时 mock 不到完整数据库,断言要松(`assert len(df) >= 1`)
- 不要尝试改 screener.py 的现有接口(`score_with_master` / `score_lynch_classifier_all`)
