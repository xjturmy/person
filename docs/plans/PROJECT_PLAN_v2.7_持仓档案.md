---
name: PROJECT_PLAN_v2.7_持仓档案
version: v2.7 (基础版)
date: 2026-06-02
status: 待拍板 — 最小切片,不带回看/预警/复盘
owner: renmingyang@proton.me
父目标:
  - 每只持仓"为什么买" 一句话可查
  - 每只持仓"最近 1 季度合理价格区间" 一眼可见
---

# 📐 preson v2.7 · 持仓档案(基础版)

> 状态:已交付(2026-06-03),归档于 docs/plans/。portfolio.yaml 15 家 + fair_price.py 5 档 Graham + 公司详情持仓卡 + 2 expander + 23 测试已落地(frontmatter 的「待拍板」为起草时状态,保留作历史)。
>
> **范围(就这两件事)**:
> 1. 持仓清单 + 一句话买入依据 → 静态 yaml
> 2. 每只持仓季度合理价格区间 → 复用 Graham Number 现成函数
>
> **不做**(留 v2.8+):加减仓历史、thesis_5y 回看、依据失效预警、季度复盘自动化、三套估值集成
>
> **总工时**:~3-4h(主对话直写)

---

## 📦 交付物清单(就 3 个文件)

### 1️⃣ `.config/portfolio.yaml` — 持仓清单与依据(用户手填)

```yaml
# 持仓档案 v1 — 最小版
# 每只持仓 4 个字段就够:代码 / 名称 / 一句话依据 / 流派标签
positions:
  - ticker: "600519"
    name: "贵州茅台"
    rationale: "高股息高 ROE 长期复利标的,PE-TTM 处于 10y 10% 分位附近时介入"
    school: "价值"        # 价值 / 成长 / 周期 / 黄金 / 其他

  - ticker: "600036"
    name: "招商银行"
    rationale: "银行业 ROE 领跑 + 零售护城河,PB < 1.0 时介入"
    school: "价值"

  - ticker: "000333"
    name: "美的集团"
    rationale: "家电龙头 + 高股息,PEG < 1 时按林奇 Stalwart 介入"
    school: "成长"

  # ...其余 13 家
```

字段语义:
- `rationale`:**一句话**说清"为什么"(刻意限制,反对长篇大论 — 长版留 02_companies/05_投资决策/)
- `school`:用于 UI 颜色 + 决定显示哪套合理价(价值=Graham / 成长=Lynch / 周期=PB / 黄金=红绿灯)
- ⚠️ 基础版只先用 Graham Number,school 字段先存着不分流,v2.8 再扩

### 2️⃣ `.tools/dashboard/fair_price.py`(~80-100 行)

```python
"""持仓季度合理价格区间 — 最小版(只用 Graham Number)。

设计:
- 调用现成的 graham_steps.check_graham_number(ticker)
- 输出 dataclass FairPriceRange(low, high, method, as_of, current_price, deviation_pct)
- low = graham_value × 0.85 (留 15% 安全边际)
- high = graham_value × 1.15 (容忍 15% 高估)
- 不存表(每次实时算,数据从已有 preson.duckdb 取);v2.8 再考虑季度快照
"""

@dataclass
class FairPriceRange:
    ticker: str
    name: str
    low: float           # 合理区间下沿
    high: float          # 合理区间上沿
    method: str          # "Graham Number"(v1 固定)
    as_of: date          # 数据快照日
    current_price: float
    deviation_pct: float # (current - mid) / mid × 100
    verdict: str         # 极低估 / 低估 / 合理 / 高估 / 极高估
    verified: bool       # graham number 算出来才 True

def compute_fair_range(ticker: str) -> FairPriceRange | None:
    """加载 graham metrics → check_graham_number → 封装 range。"""
    ...

def render_position_card(ticker: str, portfolio_entry: dict) -> None:
    """Streamlit 卡片:依据 + 合理区间 + 当前价 + verdict 颜色徽章。"""
    ...
```

verdict 规则(基础版,粗颗粒):
- 当前价 < low × 0.85 → "极低估 🟢🟢"
- 当前价 < low → "低估 🟢"
- low ≤ 当前价 ≤ high → "合理 🟡"
- 当前价 > high → "高估 🔴"
- 当前价 > high × 1.15 → "极高估 🔴🔴"

### 3️⃣ `.tools/dashboard/tabs/company.py` 接入(~30 行 diff)

在 Hero 区块下方、雪花评分上方,加一张「📌 我的持仓 · 依据 + 合理价」mini 卡:

```
┌─────────────────────────────────────────────────────────────┐
│ 📌 我的持仓 · 贵州茅台                                       │
│ 💭 依据:高股息高 ROE 长期复利标的,PE-TTM 10% 分位附近介入    │
│ 💰 合理区间:¥1,420 - ¥1,920  当前 ¥1,680  🟡 合理(+0.3%)    │
│   ▸ 估值方法:Graham Number(EPS×BPS×22.5 开方)              │
│   ▸ 数据日期:2026-06-02                                     │
└─────────────────────────────────────────────────────────────┘
```

- 卡只在 `ticker in portfolio.yaml` 时显示(非持仓股不挡 Hero)
- 加 expander 显示 graham_value 计算明细(EPS / BPS / 公式)
- ⚠️ Graham Number 算不出(EPS 负 / 银行业等)时显示"⚠️ Graham 不适用,v2.8 增加 PB-based / DCF"

---

## ✅ 完成判定(就 4 条)

1. `.config/portfolio.yaml` 含 15 家公司 × 4 字段填齐
2. `streamlit run app.py` → 选任意持仓公司 → Hero 下方可见持仓卡
3. 卡显示依据 + 合理区间 + 当前价 + verdict + 数据日期
4. 离线 pytest 覆盖:Graham 适用(茅台/美的)+ Graham 不适用(招行/新华)各一个

---

## 🛑 明确不做(v2.7 边界)

| 不做 | 原因 |
|:--|:--|
| decisions.duckdb 决策日志录入 | 当前需求只要"一句话依据",yaml 就够;细颗粒决策历史留 v2.8 |
| 三套估值集成(Graham + Lynch + Buffett) | Graham 足够覆盖大部分持仓,先看效果再扩;Lynch/Buffett 路径已有,v2.8 加 |
| 季度快照表 | 实时算够用,~50ms;季度快照留到回看功能时一起做 |
| thesis_5y 回看 / 兑现度打脸卡 | 需要先填数据并跑一两季度,本期没意义 |
| 依据失效预警 / 季度复盘自动化 | 取决于 thesis_5y,同上 |
| 加减仓历史追踪 | 决策日志的活,本版不碰 |

---

## 📋 实施顺序(主对话直写,~3-4h)

| 步骤 | 内容 | 工时 |
|:-:|:--|:-:|
| 1 | 用户填 `.config/portfolio.yaml`(我提供 15 家模板,用户改 rationale) | ~15min |
| 2 | 写 `fair_price.py` + 离线测 4 公司 | ~1.5h |
| 3 | 改 `tabs/company.py` 接入 mini 卡 + AppTest | ~1h |
| 4 | 写 4 项 pytest + memory 沉淀 | ~0.5h |
| 5 | 联调 + 截图给用户验收 | ~0.5h |

---

## 📈 v2.7 完成后 → v2.8 候选方向

基于 v2.7 基础数据沉淀,后续可按需扩(按用户痛点优先级,不预先承诺):

- 加 Lynch PEG + Buffett Owner Earnings 进 fair_range(三套并存,verdict 用主流派)
- 加加减仓历史(接 decisions.duckdb,Tab「📝 决策日志」激活)
- 加 thesis_5y 回看(每季度自动 diff 当时假设 vs 实际)
- 加季度复盘自动化(导出 markdown 到 01_knowledge/05_/持仓统计与复盘/)
- 加依据失效预警(rationale 量化条件穿透 → sidebar 通知)

---

## 📝 版本日志

| 日期 | 变更 |
|:--|:--|
| 2026-06-02 | 初始化 v2.7 基础版:用户原话"先做最基础版本,不要那么多信息";砍掉 v2.7 full 计划里 P1/P2 所有项,只留持仓清单 yaml + Graham 合理价单一方法 + 公司详情 mini 卡 |
