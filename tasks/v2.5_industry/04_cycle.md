---
name: 04_cycle · 行业周期判定引擎
covers: E2
priority: Wave 2(依赖 01 industry_master.yaml + 02 percentile 接口)
estimate: ~3h
agent: agent-cycle
---

# 任务包 04 · 行业周期判定引擎(E2)

> 给定行业,综合估值分位 + 1y 涨跌 + ROE 趋势 + 康波映射,判断"周期类型 × 当前阶段"。

---

## 📦 交付物

### 主模块 `.tools/dashboard/industry_cycle_engine.py`(~150-250 行)

```python
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDUSTRY_MASTER = PROJECT_ROOT / ".config" / "industry_master.yaml"


@dataclass
class IndustryCycle:
    industry: str
    cycle_type: str                    # 成长 / 价值 / 防御 / 周期(从 industry_master.yaml.cycle_attrs.type)
    phase: str                         # rising / topping / falling / bottoming / sideways
    phase_cn: str                      # 上行 / 见顶 / 下行 / 见底 / 横盘
    confidence: float                  # 0-1
    rationale: str                     # 一句理由
    kondratieff_position: str          # 从 industry_master.yaml.cycle_attrs.kondratieff_position
    signals: dict = field(default_factory=dict)  # {"valuation_pct": 65, "1y_return": -0.12, "roe_trend": "下行"}


def diagnose(industry: str) -> IndustryCycle:
    """规则化判定:
    1. 从 industry_master.yaml 读 cycle_type + kondratieff_position
    2. 从 industry_percentile_engine.compute() 拿 PE/PB 分位 → "估值高低"
    3. 从 etf.duckdb 或 prices 拿行业代表 ETF / 龙头 1y 涨跌 → "趋势方向"
    4. 从 self_metrics(preson.duckdb)拿行业内自选 ROE 同比 → "盈利趋势"
    5. 综合规则映射 phase
    """
    ...
```

#### 规则映射表(核心逻辑)

```
估值分位\1y 涨跌    上涨>+10%   横盘 ±10%      下跌 <-10%
高分位 (>70%)        topping     topping        falling
中分位 (30-70%)      rising      sideways       falling
低分位 (<30%)        rising      bottoming      bottoming
```

中文映射:
- `rising`=上行 / `topping`=见顶 / `falling`=下行 / `bottoming`=见底 / `sideways`=横盘

#### confidence 计算

- 三信号(估值分位 / 1y 涨跌 / ROE 趋势)同向 → confidence=0.8
- 两信号同向 → 0.6
- 信号冲突 → 0.4
- 单信号可用 → 0.3
- 全无 → 0.1,phase=sideways

#### rationale 一句话模板

例:`"PE 第 78 分位 + 1y 上涨 +24% + ROE 同比下滑 → topping(见顶,confidence 0.6)"`

#### 数据源

- **估值分位**:`from .industry_percentile_engine import compute as pct_compute; r = pct_compute(industry); pct = r.pe_percentile_10y`
  - 若返回 None,signal 标 `"valuation_pct": None`
- **1y 涨跌**:用 industry_master.yaml.etf_codes 第 1 只代表 ETF,从 etf.duckdb 拿最近 close vs 1y 前 close
  - 若 etf_codes 为空,降级用行业龙头 leader 第 1 只(从 preson.duckdb prices 表)
  - 都没数据 → signal 标 `None`
- **ROE 趋势**:行业内自选成份(从 companies.csv 过滤 industry_l2)的 latest ROE vs 上一报告期
  - 简化:增长 → "上行" / 持平 ±2pp → "持平" / 下降 → "下行"

#### 规则化映射可调

提供模块级常量 `RULE_TABLE` 5×3 dict,便于后续调整阈值:

```python
RULE_TABLE = {
    ("high", "up"): "topping",
    ("high", "flat"): "topping",
    ("high", "down"): "falling",
    ("mid", "up"): "rising",
    ("mid", "flat"): "sideways",
    ("mid", "down"): "falling",
    ("low", "up"): "rising",
    ("low", "flat"): "bottoming",
    ("low", "down"): "bottoming",
}
```

---

### 测试 `.tools/dashboard/test_industry_cycle_engine.py`(8-12 项)

```python
from tools.dashboard.industry_cycle_engine import IndustryCycle, diagnose, RULE_TABLE

def test_diagnose_returns_dataclass():
    r = diagnose("白酒")
    assert isinstance(r, IndustryCycle)
    assert r.phase in ("rising","topping","falling","bottoming","sideways")
    assert 0 <= r.confidence <= 1

def test_diagnose_unknown_industry_raises_or_default():
    r = diagnose("不存在的行业")
    assert r.confidence < 0.3  # 信号全无

def test_rule_table_complete():
    # 9 个组合都有映射
    for v in ["high","mid","low"]:
        for t in ["up","flat","down"]:
            assert (v, t) in RULE_TABLE

def test_diagnose_baijiu_kondratieff_position():
    r = diagnose("白酒")
    assert "防御" in r.kondratieff_position or "萧条" in r.kondratieff_position

# ... 4-8 项扩展
```

至少 8 项测试通过。

---

## 🛑 文件边界

- `.tools/dashboard/industry_cycle_engine.py`(新建)
- `.tools/dashboard/test_industry_cycle_engine.py`(新建)

**不动**:任何其他文件

---

## ✅ 完成判定

```bash
cd /Users/gongyong/Desktop/Keyi/preson && source .venv/bin/activate

python3 -c "
import sys; sys.path.insert(0, '.')
from tools.dashboard.industry_cycle_engine import diagnose
for ind in ['白酒','股份制银行','保险','化学制药','电池','通信设备','白色家电','饮料乳品']:
    r = diagnose(ind)
    print(f'{ind}: {r.phase_cn}({r.phase}) / 信心 {r.confidence:.1f} / 理由: {r.rationale}')
"

pytest .tools/dashboard/test_industry_cycle_engine.py -v
```

8/8 行业不报错;phase 在 5 类内;信心区间合理;测试 8/8 过。

---

## 📚 参考

- [README.md 接口契约 F](README.md)
- 依赖:01_knowledge.md 产出的 `industry_master.yaml`
- 依赖:02_percentile.md 产出的 `industry_percentile_engine.compute`
- 现有 `paradigm_engine.py`(参考 yaml 驱动 + 投票模式)
- etf.duckdb prices 表(date / close,可算 1y 涨跌)
- preson.duckdb fs_indicator 表(ROE 时序)

---

## ⚠️ 已知坑

- 不要假设 percentile_engine 返回的 pct 一定有值,None 时降级 confidence
- 1y 涨跌从 etf.duckdb 拿,要 close 时间序列至少 250 行有效;不够则降级
- ROE 趋势:`preson.duckdb` 的 fs_indicator 表 metric 列是中文(参考记忆 reference_lixinger_data_quirks.md)
- diagnose 不要硬抛错,所有数据缺失走 sideways + low confidence
- 周期判定是软指标,不要过度精细化阈值;给用户参考意见,不替用户做决定
