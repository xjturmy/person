---
name: v2.5 行业分析与聚焦标准版
date: 2026-05-10
owner: renmingyang@proton.me
基于: PROJECT_PLAN_v2.5_TODO.md TODO #2(标准版,~22h)
合并: v2.4 候选 ⑪(走偏未落地的 step-C 行业聚焦)
---

# v2.5 · 行业分析与聚焦(标准版)

> 一次性把 v2.5 TODO #2 标准版 + v2.4 候选 ⑪ 全部做完,6 任务包并行,3 波依赖。

---

## 🎯 总目标

升级现有交互体系为「行业级自顶向下视角」:打开「🏭 行业分析」Tab,8 聚焦行业 × 4 区行业卡(速览 / Top 7 公司 / Top 3 ETF / 知识周期),回答用户原话四问 — 白酒过热吗 / 创新药周期到哪 / 半导体哪些 ETF 怎么选 / 该跟踪哪 7 家。

---

## 🧱 6 任务包

| 任务包 | 子任务 | 工时 | 依赖 |
|---|---|:-:|---|
| [01_knowledge.md](01_knowledge.md) | D1 行业主索引 + D2 8 行业知识 md + D3 ETF 主题映射 | ~6h | 无 |
| [02_percentile.md](02_percentile.md) | E1 行业估值分位引擎 | ~2h | step-A market.duckdb(降级 fallback) |
| [03_screener.md](03_screener.md) | E4 行业 Top 7 选优(候选 ⑪ 重启) | ~6-8h | 无(数据降级) |
| [04_cycle.md](04_cycle.md) | E2 行业周期判定引擎 | ~3h | 01 yaml + 02 接口 |
| [05_etf_recommender.md](05_etf_recommender.md) | E3 ETF 推荐引擎 | ~2h | 01 yaml + etf.duckdb |
| [06_tab_ui.md](06_tab_ui.md) | F1-F4 4 区 Tab + G1 顶部 banner + G2 sidebar 编辑 | ~6h | 02/03/04/05 全就绪 |

**总工时**:~22-25h(墙时间 6 agent 并行 ~1.5-2h)

---

## 🔗 依赖图与启动波次

```
Wave 1(0 依赖,并行):
  ├─ 01_knowledge      纯文档/yaml,无代码依赖
  ├─ 02_percentile     E1 估值分位引擎,数据降级
  └─ 03_screener       E4 Top 7 选优,数据降级

Wave 2(依赖 Wave 1,并行):
  ├─ 04_cycle          需要 industry_master.yaml + IndustryPercentile 接口
  └─ 05_etf_recommender 需要 industry_master.yaml + industry_etf_mapping.yaml

Wave 3(依赖全部):
  └─ 06_tab_ui         import 4 个引擎 + 写 Tab + app.py 接入
```

---

## 📐 接口契约(全局共享,所有 agent 必读必守)

### A · industry_master.yaml(D1 产出,所有引擎消费)

写入路径:`.config/industry_master.yaml`

```yaml
# ⚠️ 行业 key 用 SW 二级名(对齐 .config/companies.csv 的 industry_l2 列)
# 当前自选 15 家覆盖到的 SW L2:白酒 / 化学制药 / 股份制银行 / 保险 / 电池 / 通信设备 /
#                              白色家电 / 饮料乳品 / 化学制品 / 轨交设备 / 消费电子 / 家电零部件 / 乘用车
# 8 重点行业(必填):白酒 / 化学制药 / 股份制银行 / 保险 / 电池 / 通信设备 / 白色家电 / 饮料乳品

industries:
  - code: BAIJIU                  # 唯一 ID,大写英文
    name: 白酒                     # SW L2 名(精确匹配 companies.csv.industry_l2)
    sw_l1: 食品饮料                # SW L1
    type: stalwart                # 林奇六类:stalwart / fast_grower / cyclical / slow_grower / bank / insurance
    summary: "中国特色消费品..."    # 一句行业概览(30-60 字)
    cycle_attrs:
      type: 防御                   # 成长 / 价值 / 防御 / 周期
      kondratieff_position: 萧条期防御核心
      key_indicators:              # 关键观察指标 3-5 条
        - 飞天茅台批价
        - 渠道库存周转
        - 消费税政策
    etf_codes: ["512690", "159843"] # 推荐 ETF code 列表(2-4 只),从 etf.duckdb 实有
    knowledge_md: "03_macro/02_行业对标数据/01_白酒.md"  # D2 知识 md 相对路径
    leaders: ["600519", "000858", "000596"]  # 行业龙头(可选,用于龙头集中度判定)

  # ... 其他 7 重点行业同结构
```

### B · industry_etf_mapping.yaml(D3 产出,E3 消费)

写入路径:`.tools/rules/industry_etf_mapping.yaml`

```yaml
# 康波周期 × 行业 → 推荐 ETF 映射,从 03_macro/01_ETF分析工具/康波周期ETF配置汇总.md 解析
# 当前周期定位:第五次康波萧条期中后段(2026)

current_phase: 萧条期中后段
target_allocation:
  defensive: [65, 75]              # 防御层 65-75%
  offensive: [25, 35]              # 进攻层 25-35%

# 行业 → 周期阶段 → ETF 推荐
mapping:
  - industry: 白酒
    layer: defensive               # defensive / offensive / auxiliary
    target_pct: [15, 20]           # 配置区间 %
    recommended_etfs:
      - code: "512690"
        name: 酒ETF
        theme: 主题                # 主题 / 龙头 / 红利
        rationale: 白酒 + 啤酒等大消费综合曝光
      - code: "159843"
        name: 食品ETF
        theme: 主题
        rationale: 必选消费防御
    framework_logic: 稳定现金流 + 抗通胀
  # ... 其他行业
```

### C · focus_industries.yaml(E4 产出 / G2 编辑)

写入路径:`.config/focus_industries.yaml`

```yaml
focus:
  - industry: 白酒                  # 必须与 industry_master.yaml.industries.name 完全一致
    type: stalwart                  # 与 industry_master 同步
    weight: 1.0
  - industry: 股份制银行
    type: bank
    weight: 1.0
  - industry: 保险
    type: insurance
    weight: 1.0
  - industry: 化学制药
    type: fast_grower
    weight: 1.0
  - industry: 电池
    type: fast_grower
    weight: 1.0
  - industry: 通信设备
    type: fast_grower
    weight: 1.0
  - industry: 白色家电
    type: stalwart
    weight: 1.0
  - industry: 饮料乳品
    type: stalwart
    weight: 1.0

top_n: 7
market_cap_min: 5000000000          # 50 亿门槛
```

### D · industry_type_map.yaml(E4 产出)

写入路径:`.tools/rules/industry_type_map.yaml`

```yaml
# 6 类型 → 评分规则映射(引用现有 yaml,不写新规则)
type_to_scoring:
  stalwart:
    primary: lynch                   # primary 用 lynch_classifier 自动判定 stalwart
    secondary: [graham, piotroski]
    weights: {lynch: 0.5, graham: 0.3, piotroski: 0.2}
  fast_grower:
    primary: lynch
    secondary: [damodaran, piotroski]
    weights: {lynch: 0.5, damodaran: 0.3, piotroski: 0.2}
  cyclical:
    primary: lynch
    secondary: [graham, altman]
    weights: {lynch: 0.4, graham: 0.3, altman: 0.3}
  slow_grower:
    primary: lynch
    secondary: [graham, piotroski]
    weights: {lynch: 0.4, graham: 0.4, piotroski: 0.2}
  bank:
    primary: graham_bank
    secondary: [piotroski_bank]
    weights: {graham_bank: 0.6, piotroski_bank: 0.4}
  insurance:
    primary: graham_insurance
    secondary: [piotroski_insurance]
    weights: {graham_insurance: 0.6, piotroski_insurance: 0.4}
```

### E · IndustryPercentile dataclass(E1 产出,E2/F1 消费)

模块:`.tools/dashboard/industry_percentile_engine.py`

```python
from dataclasses import dataclass
from datetime import date

@dataclass
class IndustryPercentile:
    industry: str                    # SW L2 名
    pe_median: float | None
    pe_percentile_10y: float | None  # 0-100,基于行业 PE 中位数 10 年时序
    pb_median: float | None
    pb_percentile_10y: float | None
    member_count: int                # 行业成份股数
    as_of: date
    data_source: str                 # "market.duckdb" / "peers.duckdb" / "self_only"
    notes: str = ""                  # 数据降级说明

def compute(industry: str) -> IndustryPercentile:
    """优先 market.duckdb(全市场快照);降级 peers.duckdb;再降级 self_metrics(只算自选)"""
    ...
```

### F · IndustryCycle dataclass(E2 产出,F1 消费)

模块:`.tools/dashboard/industry_cycle_engine.py`

```python
@dataclass
class IndustryCycle:
    industry: str
    cycle_type: str                  # 成长 / 价值 / 防御 / 周期(从 industry_master.yaml.cycle_attrs.type)
    phase: str                       # rising / topping / falling / bottoming / sideways
    phase_cn: str                    # 中文 - 上行 / 见顶 / 下行 / 见底 / 横盘
    confidence: float                # 0-1
    rationale: str                   # 一句理由
    kondratieff_position: str        # 从 industry_master.yaml.cycle_attrs.kondratieff_position
    signals: dict                    # {"valuation_pct": 65, "1y_return": -0.12, "trend": "下行"}

def diagnose(industry: str) -> IndustryCycle:
    """规则化判定:估值分位 + 1y 涨跌 + ROE 趋势 + 康波映射"""
    ...
```

### G · ETFCandidate dataclass(E3 产出,F3 消费)

模块:`.tools/dashboard/etf_recommender.py`

```python
@dataclass
class ETFCandidate:
    code: str
    name: str
    theme: str                       # 主题 / 龙头 / 红利(从 mapping.yaml)
    fund_type: str                   # etf_meta.etf_type
    last_close: float | None
    return_1y: float | None          # 1 年涨幅
    avg_turnover: float | None       # 60 日均换手(流动性代理)
    liquidity_score: float           # 0-100 综合流动性
    rationale: str                   # 一句推荐理由

def recommend(industry: str, top_n: int = 3) -> list[ETFCandidate]:
    """读 industry_master.etf_codes + industry_etf_mapping.yaml + etf.duckdb 校验"""
    ...
```

### H · industry_screener 接口(E4 产出,F2 消费)

模块:`.tools/dashboard/industry_screener.py`

```python
def list_industry_candidates(industry: str) -> list[str]:
    """返回该行业候选公司 ticker 列表。
    优先 market.duckdb;降级 peers.duckdb + companies.csv 自选。
    """
    ...

def score_company(ticker: str, scoring_type: str) -> dict:
    """复用 .tools/dashboard/screener.py 的 score_with_master / score_lynch_classifier_all。
    返回 {ticker, name, score, breakdown, reason, primary_master, secondary_scores}
    """
    ...

import pandas as pd

def screen_industry(industry: str, type: str, top_n: int = 7) -> pd.DataFrame:
    """返回 cols: rank / ticker / name / score / reason / is_owned(L3 自选)/ data_source"""
    ...

def screen_all_focus(focus_yaml_path: str = ".config/focus_industries.yaml") -> dict[str, pd.DataFrame]:
    """批量跑所有聚焦行业"""
    ...
```

---

## 🛑 文件边界(严格,所有 agent 不得越界)

| 任务包 | 写入路径白名单 |
|:-:|---|
| 01 | `.config/industry_master.yaml` / `.tools/rules/industry_etf_mapping.yaml` / `03_macro/02_行业对标数据/01-08_*.md`(8 篇) |
| 02 | `.tools/dashboard/industry_percentile_engine.py` + 测试 `test_industry_percentile_engine.py` |
| 03 | `.config/focus_industries.yaml` / `.tools/rules/industry_type_map.yaml` / `.tools/dashboard/industry_screener.py` + 测试 |
| 04 | `.tools/dashboard/industry_cycle_engine.py` + 测试 |
| 05 | `.tools/dashboard/etf_recommender.py` + 测试 |
| 06 | `.tools/dashboard/tabs/industry_focus.py` + 测试 + `app.py` 加 PAGE_INDUSTRY_FOCUS + sidebar 编辑入口 |

⚠️ **共享文件**:
- `app.py` — 仅 Wave 3(06)动,加 PAGE_INDUSTRY_FOCUS 与 sidebar 入口
- `requirements.txt` — 不需要新依赖(yaml/duckdb/pandas/streamlit/plotly 都已有)

---

## ✅ 全部完成判定

1. `cat .config/industry_master.yaml` → 8 重点行业完整(industries 列表 ≥ 8)
2. `ls 03_macro/02_行业对标数据/01_*.md ... 08_*.md` → 8 篇 200-400 字
3. 离线引擎冒烟 4 项全过:
   ```python
   from tools.dashboard.industry_percentile_engine import compute as pct_compute
   from tools.dashboard.industry_cycle_engine import diagnose as cycle_diag
   from tools.dashboard.etf_recommender import recommend as etf_rec
   from tools.dashboard.industry_screener import screen_all_focus
   assert pct_compute("白酒").pe_median is not None or pct_compute("白酒").data_source == "self_only"
   assert cycle_diag("白酒").phase in ("rising","topping","falling","bottoming","sideways")
   assert len(etf_rec("白酒", top_n=3)) >= 1
   results = screen_all_focus()
   assert len(results) == 8 and all(len(df) >= 1 for df in results.values())
   ```
4. `streamlit run app.py --server.headless true` → 「🏭 行业分析」Tab 0 异常,8 行业 4 区卡片全渲染
5. PROGRESS.md 追加 v2.5 TODO #2 完成段

---

## 📚 参考资料

- 项目说明 [CLAUDE.md](../../CLAUDE.md)
- 计划文档 [PROJECT_PLAN_v2.5_TODO.md](../../plans/PROJECT_PLAN_v2.5_TODO.md) TODO #2
- v2.4 走偏教训 [../tasks/v2.4_p0/step-C_industry_focus.md](../v2.4_p0/step-C_industry_focus.md)
- 已有评分入口 [.tools/dashboard/screener.py:300-413](../../.tools/dashboard/screener.py)(`score_with_master` / `score_lynch_classifier_all`)
- 林奇分类 [.tools/dashboard/lynch_classifier.py](../../.tools/dashboard/lynch_classifier.py)
- 现有评分 yaml 14 套 [.tools/rules/](../../.tools/rules/)
- 康波 ETF 文档 [03_macro/01_ETF分析工具/康波周期ETF配置汇总.md](../../03_macro/01_ETF分析工具/康波周期ETF配置汇总.md)
- 已有 etf.duckdb:`etf_meta`(etf_code/etf_name/etf_type/last_update)+ `etf_prices`(date/ohlcv/turnover/pct_change),35 ETF × 16940 行
