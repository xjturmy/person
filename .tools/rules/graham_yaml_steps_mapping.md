# Graham YAML 准则 ↔ 五步法对照表(v2.5 G5)

> 本文件说明 `.tools/rules/graham.yaml` 中 7 项准则与
> `.tools/dashboard/graham_steps.py` 五步法(ABCD/12345)之间的映射关系。
>
> **重要**:两者是互补的独立逻辑,不是替代。
> - yaml 准则 → **定量评分**:产出 0-13 分,供 screener 排序
> - graham_steps.py 五步法 → **类型判定 + 完整诊断**:给用户"这家公司属于哪类格雷厄姆投资机会"的质性结论

---

## 对照表

| 五步法步骤 | yaml 准则 / 字段 | 备注 |
|-----------|----------------|------|
| **第 1 步** — 公司类别判定(deep_value / defensive / enterprising / special) | 无对应 yaml 准则 | 由 `classify_graham_type()` 输出,不进评分 |
| **第 2 步** — 基本面硬指标统计 | `g1_size`(500亿规模) | 排除小盘股 |
| | `g2_financial_strength`(流动比率 ≥ 2 + 长期负债 ≤ 净流动资产) | 财务结构稳健 |
| | `g3_earnings_stability`(10 年无亏损,2 分) | 盈利稳定性核心项 |
| **第 3 步** — 估值温和性 | `g6_pe_moderate`(PE ≤ 15,2 分) | 市盈率温和 |
| | `g7_pb_moderate`(PB ≤ 1.5 OR PE×PB ≤ 22.5,2 分) | v2.5 G2 新增 OR 条件 |
| **第 4 步** — 派息记录 + 盈利增长 | `g4_dividend_record`(连续派息 ≥ 10 年) | v2.5 G3 由 `derived_metrics.years_continuous_dividend` 提供数据 |
| | `g5_earnings_growth`(10 年 EPS 增长 ≥ 33%) | 用 3 年平均 EPS 平滑 |
| **第 4 步** — Graham Number 估值上限 | `graham_number_check`(市价 / Graham Number 比值分档) | √(22.5 × EPS × BVPS),4 档评级 |
| **第 5 步** — NCAV 极端低估检测 | `ncav_critical_bonus`(市值 < NCAV × 0.67,+3 bonus) | v2.5 G4 新增;A 股极少触发 |

---

## 设计原则

### 为什么两套逻辑并存?

1. **yaml 准则**面向批量筛选 — screener 需要一个数字化评分快速排序 15 家公司。
   每条准则都能机械映射到 DuckDB 字段,结果可重现。

2. **五步法**面向单公司诊断 — 给投资者一个完整叙事:
   "这家公司是防御型还是进取型?Graham Number 是多少?Net-Net 有没有机会?"
   它需要更多的业务判断,不适合简化成单一数字。

### 未来合并计划

下次迭代(v2.6 或 verify agent)可考虑:
- 将 `graham_steps.py` 的 `DefensiveSeven` 评估结果直接作为 yaml 准则的动态输入
- 或反过来,让 yaml 评分引擎调用 `classify_graham_type()` 并把类别作为附加权重

当前阶段:两套逻辑保持独立,共享 DuckDB 数据层,通过 `graham_extras.STEPS_TO_YAML_RULES_MAP` 字典作为运行时文档锚点。

---

## 数据依赖图

```
.config/companies.csv
    └── industry_l2 → graham_router.py → 选择 graham*.yaml

preson.duckdb
    ├── valuation   → g6(PE-TTM) / g7(PB) / g4(股息率,经 derived_metrics)
    ├── safety      → g2(流动比率/负债)
    ├── growth      → g3(EPS)/g5(EPS CAGR)/NCAV近似(资产总计)
    ├── profitability → (辅助)
    └── cashflow    → (辅助)

derived_metrics.py
    └── years_continuous_dividend(ticker) → g4 数据源

graham_extras.py
    └── compute_ncav_status(ticker)  → ncav_critical_bonus
    └── parse_g7_or(pb, pe)          → g7 OR 条件解析

graham_steps.py(只读,不被 yaml 调用)
    └── classify_graham_type()       → 五步法类别判定
    └── DefensiveSeven               → 五步法第 2 步详细评估
    └── GrahamNumberCheck            → 五步法第 4 步估值
    └── NCAVCheck                    → 五步法第 5 步 Net-Net
```

---

## Graham Number 说明

```
Graham Number = √(22.5 × EPS × BVPS)

其中:
  22.5 = PE 上限(15) × PB 上限(1.5)
  EPS  = 最近年报每股收益
  BVPS = 最近年报每股净资产

市价 / Graham Number 分档:
  < 0.5   → 极度低估
  0.5-0.8 → 低估
  0.8-1.2 → 合理
  > 1.2   → 高估
```

---

*文件由 Claude v2.5 TODO#1 G5 任务生成,2026-05-10*
