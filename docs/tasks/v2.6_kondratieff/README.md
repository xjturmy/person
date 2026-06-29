---
name: v2.6 康波周期 ETF 配置(推荐版)
date: 2026-05-10
status: 已定型 / 等"开干"信号
owner: renmingyang@proton.me
基于: PROJECT_PLAN_v2.6.md
---

# v2.6 · 康波周期 ETF 配置任务包

> **状态:⏳ 未交付 / 计划中(2026-06-28 核对,与根 README v2.6 行 ⏳ 一致)**
> 本任务包的 4 个模块均**未实施**:`kondratieff_loader.py`(KondratieffConfig)、`etf_compare.py`(`pick_top_etf`/`rank_etfs`)、`tabs/kondratieff.py`(独立 ETF 配置 Tab)、`fetch_etf_meta_extra.py` 都不存在。
> ⚠️ **易混淆**:现存的 `.tools/dashboard/tabs/market/kondratieff.py` 是 v2.1/v2.5「市场周期定位卡」(静态 yaml 驱动的康波定位 card,`_section_kondratieff_card`),**不是**本任务包要做的「康波 → ETF 推荐组合 → 同行业 N 选 1」配置 Tab。两者同名不同物。
> 下文为待执行规格,保留备用。
>
> **目标**:打造「康波周期 → 推荐组合 → 同行业 N 选 1」自顶向下视角的 ETF 配置 Tab,在 v2.5「单行业」视角之上补一层「全康波组合」入口。
>
> **范围**:推荐版(阶段 1 + 阶段 2),**不做** 阶段 3 信号自动化 + 组合优化器(留 v2.7)。

---

## 🧱 4 任务包

| 任务包 | 内容 | 工时 | Wave | 依赖 |
|---|---|:-:|:-:|---|
| [01_data_loader.md](01_data_loader.md) | kondratieff_loader.py 数据聚合层 | ~2h | 1 | 无 |
| [02_etf_compare.md](02_etf_compare.md) | etf_compare.py 同行业 N 选 1 引擎 | ~2h | 1 | 弱依赖 v2.5 etf_recommender |
| [04_etf_metadata.md](04_etf_metadata.md) | fetch_etf_meta_extra.py + etf.duckdb 扩字段 | ~5-7h | 1 | AkShare(网络) |
| [03_tab_ui.md](03_tab_ui.md) | tabs/kondratieff.py + app.py 接入 + 测试 | ~3-4h | 2 | 01 + 02(+ 04 加分) |

**总工时**:~12-15h(2 波串行,墙时间 ~6-8h 可压缩)

---

## 🔗 依赖图

```
Wave 1(并行,无强依赖):
  ├─ 01_data_loader      kondratieff_loader.py
  ├─ 02_etf_compare      etf_compare.py
  └─ 04_etf_metadata     fetch_etf_meta_extra.py + etf.duckdb 扩字段

Wave 2(依赖 Wave 1):
  └─ 03_tab_ui           tabs/kondratieff.py + app.py PAGE_KONDRATIEFF
                         (顺手在 industry_focus.py C 区补费率/规模列)
```

参考 v2.5 经验:**主对话直写比 agent 并行稳**(避免 600s stall)。建议主对话顺序写 4 个模块,合计 1.5-2h 实墙时间。

---

## 📐 接口契约(全局共享)

### A · KondratieffConfig dataclass(01 产出,03 消费)

模块:`.tools/dashboard/kondratieff_loader.py`

```python
from dataclasses import dataclass, field

@dataclass
class IndustryEntry:
    industry: str            # 行业名,与 industry_master.yaml.name 一致
    layer: str               # defensive / offensive / auxiliary
    target_pct: tuple        # [min, max] 配置区间 %
    framework_logic: str     # 一句框架逻辑(从 mapping yaml)
    etfs: list               # list[ETFEntry]


@dataclass
class ETFEntry:
    code: str
    name: str
    theme: str               # 主题 / 龙头 / 红利
    rationale: str           # mapping yaml 自填理由
    # 阶段 1 默认 None,阶段 2 后填:
    last_close: float | None = None
    return_1y: float | None = None
    avg_turnover_60d: float | None = None
    liquidity_score: float | None = None
    fund_size: float | None = None       # 阶段 2 加 — 资产规模(亿)
    fee_total: float | None = None       # 阶段 2 加 — 管理 + 托管费率合计


@dataclass
class KondratieffConfig:
    current_phase: str
    target_allocation: dict        # {defensive: [65, 75], offensive: [25, 35], auxiliary: [0, 5]}
    defensive: list                # list[IndustryEntry]
    offensive: list
    auxiliary: list

    @property
    def all_industries(self) -> list:
        return self.defensive + self.offensive + self.auxiliary


def load_config() -> KondratieffConfig: ...
```

### B · ETF Top 1 选优(02 产出,03 消费)

模块:`.tools/dashboard/etf_compare.py`

```python
def pick_top_etf(industry_entry: IndustryEntry,
                 weights: dict | None = None) -> ETFEntry | None:
    """同行业内 N 只 ETF 选 Top 1。

    默认权重:{liquidity: 0.4, return_1y: 0.3, fund_size: 0.3}
    阶段 2 之前 fund_size 缺失时降级为 {liquidity: 0.5, return_1y: 0.5}。
    """
    ...


def rank_etfs(industry_entry: IndustryEntry,
              weights: dict | None = None) -> list[tuple[ETFEntry, float]]:
    """返回排序后的 [(ETFEntry, composite_score), ...]"""
    ...
```

### C · etf.duckdb 扩字段(04 产出)

`etf_meta` 表 ALTER ADD COLUMN(idempotent):
```sql
ALTER TABLE etf_meta ADD COLUMN IF NOT EXISTS management_fee DOUBLE;  -- 管理费率(年化,如 0.005=0.5%)
ALTER TABLE etf_meta ADD COLUMN IF NOT EXISTS custodian_fee DOUBLE;   -- 托管费率
ALTER TABLE etf_meta ADD COLUMN IF NOT EXISTS fund_size DOUBLE;       -- 资产规模(亿元)
ALTER TABLE etf_meta ADD COLUMN IF NOT EXISTS tracking_index VARCHAR; -- 跟踪指数 code(留 v2.7 阶段 3 用)
ALTER TABLE etf_meta ADD COLUMN IF NOT EXISTS meta_updated DATE;      -- 最后更新日
```

### D · 顺手扩 v2.5 ETFCandidate(04 产出后,本任务包顺手做)

模块:`.tools/dashboard/etf_recommender.py`

```python
@dataclass
class ETFCandidate:
    # 已有字段不变
    ...
    # 阶段 2 新增:
    fee_total: float | None = None    # = management_fee + custodian_fee
    fund_size: float | None = None    # 亿元
```

`recommend()` 内 SELECT etf_meta 扩列;UI(industry_focus.py C 区)表格加 2 列。

---

## 🛑 文件边界(所有任务包不得越界)

| 任务包 | 写入路径白名单 |
|:-:|---|
| 01 | `.tools/dashboard/kondratieff_loader.py` + `test_kondratieff_loader.py` |
| 02 | `.tools/dashboard/etf_compare.py` + `test_etf_compare.py` |
| 03 | `.tools/dashboard/tabs/kondratieff.py` + `test_kondratieff_tab.py` + `app.py` 加 PAGE + render 调度 |
| 04 | `.tools/db/fetch_etf_meta_extra.py` + `.tools/db/test_fetch_etf_meta_extra.py` + 修改 `etf.duckdb` 表结构(idempotent) + `update.py` 加 step_etf_meta_extra |

⚠️ **共享文件**:
- `app.py` — 仅 03 动,加 PAGE_KONDRATIEFF + render 调度
- `update.py` — 仅 04 动,加 monthly cron 钩子
- `etf_recommender.py` + `tabs/industry_focus.py` — 03 收尾时顺手扩 2 列(零侵入,只 append)

---

## ✅ 全部完成判定

详见 [PROJECT_PLAN_v2.6.md](../../plans/_archive/PROJECT_PLAN_v2.6.md)「全部完成判定」段。

---

## 📚 参考

- v2.5 已交付 [project_v25_industry_focus_delivered.md](../../.claude/projects/-Users-gongyong-Desktop-Keyi-preson/memory/project_v25_industry_focus_delivered.md)
- 现有 [.tools/rules/industry_etf_mapping.yaml](../../.tools/rules/industry_etf_mapping.yaml)(19 行业 / 35 ETF / target_pct 完整)
- 现有 [data/etf.duckdb](../../data/) 35 ETF × 484 日(etf_meta + etf_prices)
- 现有 [.tools/dashboard/etf_recommender.py](../../.tools/dashboard/etf_recommender.py)(阶段 1 复用)
- 现有 [tabs/gold_analysis.py](../../.tools/dashboard/tabs/gold_analysis.py)(banner + sub-tab UI 模式参考)
- 康波文档 [03_macro/01_ETF分析工具/康波周期ETF配置汇总.md](../../03_macro/01_ETF分析工具/康波周期ETF配置汇总.md)
- macro.duckdb(实际利率/CPI/M2/USDCNY 时序,顶部 banner 只读展示)
