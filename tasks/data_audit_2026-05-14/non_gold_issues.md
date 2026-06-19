# 非黄金类数据/计算问题清单 (2026-05-14 大稽核)

> 来源：4 个 agent 并行检查 + 主对话亲验。本次只修黄金类问题,非黄金类待修。
> 黄金类已处理结果见 `PROGRESS.md` / 本目录其他文件。
> 共 16 条待修问题 + 1 条误报归档 = 17 条全部记录。

---

## P0 严重 — 影响决策结论

### #1 peers 表过期 + 五粮液 PE 错 14 倍

- **数据来源**：[`data/peers.duckdb`](../../data/peers.duckdb) 表 `peers`
- **证据**：
  - peers.duckdb 所有行 `refreshed_at = 2026-05-07 22:08`，今天 5/14，**已过期 7 天**
  - 五粮液 000858 在 peers 表里 `peer_pe = 11.68`，主库 [`data/preson.duckdb`](../../data/preson.duckdb) 今日 PE = 166
  - 误差倍数：166 / 11.68 ≈ **14.2 倍**
  - 5/6 五粮液财务异常新闻（参见 [reference_wuliangye_pe_anomaly](../../../.claude/projects/-Users-gongyong-Desktop-Keyi-preson/memory/reference_wuliangye_pe_anomaly.md)）未传导到 peers 快照
- **影响范围**：
  - [`.tools/dashboard/industry_percentile_engine.py`](../../.tools/dashboard/industry_percentile_engine.py)
  - [`.tools/dashboard/industry_cycle_engine.py`](../../.tools/dashboard/industry_cycle_engine.py)
  - [`.tools/dashboard/industry_screener.py`](../../.tools/dashboard/industry_screener.py)
  - [`.tools/dashboard/tabs/industry_focus.py`](../../.tools/dashboard/tabs/industry_focus.py)
  - 白酒行业当前判定 "极度便宜·见底" — 方向反了，真实是有股票财务异常拉高均值
- **建议修复**：
  1. (a) 立刻重跑 peers fetcher（短期）
  2. (b) `industry_percentile_engine.py` 改为实时从 `preson.duckdb` 算池子 median（中期）
  3. (c) `member_count < 5` 时 UI 强制 "样本不足" 警示（防御）
- **优先级**：**P0**

---

### #2 美的 PEG 锁在 1 年前扣非数据

- **数据来源**：`preson.duckdb` 表 `valuation`
- **证据**：
  - 美的 000333 PE-TTM(扣非) 最新日期 = **2025-04-30**
  - 美的 000333 PE-TTM(GAAP) 最新日期 = **2026-05-06**
  - 两者差 **372 天**
  - [`.tools/dashboard/peg_curve.py:197`](../../.tools/dashboard/peg_curve.py) 优先吃扣非，"扣非整列空" 才 fallback；列非空但末日已是 1 年前不切换
- **影响范围**：
  - 林奇五步法第 4 步 PEG 判定
  - `.tools/dashboard/lynch_extras.py` 中 `peg_curve_grade` 函数
  - 美的连续一年错误标记 "高估·减仓"
- **建议修复**：
  - `peg_curve.py:197` 把 "扣非整列空" fallback 改成 "扣非末日 < GAAP 末日 - 90 天" 也 fallback
  - 约 10 行代码改动
- **优先级**：**P0**

---

## P1 精度/口径不统一

### #3 PE 分位双口径并存

- **数据来源**：理杏仁内置字段 vs `derived_metrics.pe_pct_5y`
- **证据**：
  - 茅台 600519 理杏仁内置 10y PE-TTM 分位 = **8.91%**
  - 茅台 600519 [`derived_metrics.pe_pct_5y('600519')`](../../.tools/dashboard/derived_metrics.py) = **16.43%**
  - 误差 7.5 pp，方向都说 "便宜" 但程度不同
- **影响范围**：
  - lynch tab / score_card / multi_master 不同 tab 拿不同口径
  - "贵不贵" 答案随 tab 漂移
- **建议修复**：
  - 全部统一到理杏仁 `PE-TTM_分位点`（10y 内置）
  - [`derived_metrics.py`](../../.tools/dashboard/derived_metrics.py) 中 `pe_pct_5y` 改名 `pe_pct_5y_local_window` 或退役
  - 引用方批量替换
- **优先级**：**P1**

---

### #4 industry_pe 表只有 2 天数据但 percentile_engine 未使用

- **数据来源**：`preson.duckdb` 表 `industry_pe`
- **证据**：
  - `industry_pe` 表仅 **2026-04-29 ~ 2026-04-30** 两天
  - 120 行业 × 2 天 = 240 行
  - [`.tools/dashboard/industry_percentile_engine.py`](../../.tools/dashboard/industry_percentile_engine.py) 实际不读这张表，转而吃 peers 池子（见 #1）
- **影响范围**：
  - 权威 10y 时序数据浪费
  - percentile_engine 被 peers 快照过期问题间接传染
- **建议修复**：
  - (a) 补 `industry_pe` 历史数据到完整 10y
  - (b) 或退役这张表,在 schema 文档里说明
- **优先级**：**P1**

---

## P2 评分体系算法/方法论偏离

### #5 Graham g5 公式 eps_3y_avg 二次平滑（待亲验）

- **文件**：[`.tools/rules/graham.yaml:92-98`](../../.tools/rules/graham.yaml)
- **证据**：
  - 规则要求："10 年累计 EPS 增长 ≥ 33%"
  - 公式实际：`cagr(eps_3y_avg, 10) ≥ 0.029`
  - `eps_3y_avg` 已是 3 年滚动均，再做 10y CAGR = 二次平滑
- **影响范围**：
  - 评分虚高估计 20-30%
  - 茅台 / 招行受影响
- **建议修复**：
  - 改为 `cagr(eps, 10) ≥ 0.029`（直接用 EPS 不用平均）
  - 需亲验：跑前后对比看茅台/招行评分变化
- **优先级**：**P2**

---

### #6 Lynch PEG 用 3y CAGR vs Lynch 原书 5y

- **文件**：
  - [`.tools/score/engine.py:280-289`](../../.tools/score/engine.py)
  - [`.tools/rules/lynch.yaml:85`](../../.tools/rules/lynch.yaml)
- **证据**：
  - Lynch 《One Up on Wall Street》原书 PEG 用 5 年盈利增长率
  - 当前 engine 用 3y CAGR
- **影响范围**：
  - GARP 在估值过热期高估成长股 15-25%
- **建议修复**：
  - 增加 `eps_growth_5y` 衍生指标到 [`derived_metrics.py`](../../.tools/dashboard/derived_metrics.py)
  - PEG 取 `max(3y_cagr, 5y_cagr)` 保守
- **优先级**：**P2**

---

### #7 Buffett `direction: reverse` 可能未实现（待亲验）

- **文件**：
  - [`.tools/rules/buffett.yaml:88-101`](../../.tools/rules/buffett.yaml)
  - [`.tools/score/engine.py`](../../.tools/score/engine.py) `eval_rule()` 函数
- **证据**：
  - buffett.yaml 多条规则用 `direction: reverse`（如负债率越低越好）
  - 需亲验 engine.py 的 eval_rule() 是否实际处理 reverse 分支
- **影响范围**：
  - 若反向逻辑未实现，负债高的公司反得高分（逻辑反演）
  - 涉及 Buffett 评分所有 reverse 规则
- **建议修复**：
  - 亲验 eval_rule() 实现
  - (a) 在 eval_rule() 补齐 `direction: reverse` 处理
  - (b) 或 yaml 改成正向逻辑（如 `debt_ratio < 0.5`）
- **优先级**：**P2**

---

### #8 Buffett retained_earnings_return DPS 公式错（dashboard agent 实测确认）

- **文件**：[`.tools/dashboard/buffett_extras.py:320`](../../.tools/dashboard/buffett_extras.py)
- **证据**：
  - 错误公式：`dividend_per_share = eps × 股息率/100`
  - 等价于：`DPS = EPS × DPS/股价`（数学上不等于 DPS）
  - 正确公式：`DPS = 股息率 × 年末股价`
  - 已标 `verified=False` 但 UI 仍展示
- **影响范围**：
  - Buffett 留存收益回报率指标
  - UI 展示但未告警
- **建议修复**：
  - 修公式为 `dps = 股息率 × 年末股价`
  - UI 显示 `verified flag` 警示
- **优先级**：**P2**

---

### #9 Lynch "连续 5y ROE ≥20%" 实际只测 1 年（dashboard agent 实测确认）

- **文件**：[`.tools/dashboard/lynch_abcd_scorer.py:373-383`](../../.tools/dashboard/lynch_abcd_scorer.py)
- **证据**：
  - label 写 "连续 5 年 ROE ≥ 20%"
  - 代码实际只检查最新 1 年 ROE ≥ 20%
- **影响范围**：
  - label 误导用户以为是 5y 验证
  - 实际是 1y 快照
- **建议修复**：
  - (a) 改 label 为 "最新 ROE ≥ 20%"
  - (b) 或补 5y 真实回看代码
- **优先级**：**P2**

---

### #10 银行业派生 5 项 verified=False 但 UI 不警示

- **文件**：[`.tools/rules/piotroski_bank.yaml:14-23`](../../.tools/rules/piotroski_bank.yaml)
- **证据**：
  - 5 项银行业指标走 sina BS+IS 派生（参考 [reference_p3_bank_metrics_proxies](../../../.claude/projects/-Users-gongyong-Desktop-Keyi-preson/memory/reference_p3_bank_metrics_proxies.md)）
  - 全部 `verified=False`
  - 招行 600036 显示评分 6/6，但置信度未透传 UI
- **影响范围**：
  - 招行评分置信度被高估
  - 用户无从知道 5 项是派生估算
- **建议修复**：
  - UI 显示标签 "⚠️ 银行业派生指标 sina 口径"
  - 在 score card 加 verified 状态 icon
- **优先级**：**P2**

---

### #11 Piotroski f5 用有息负债率代替长期负债率

- **文件**：[`.tools/rules/piotroski.yaml:66-78`](../../.tools/rules/piotroski.yaml)
- **证据**：
  - 原 Piotroski F-Score f5 用长期负债率
  - 当前用有息负债率
- **影响范围**：
  - 替代有合理性（理杏仁无原字段）
  - 但未文档化
- **建议修复**：
  - 在 piotroski.yaml f5 加注释说明替代依据
  - 加 `f5_alt` 替代条件标记
- **优先级**：**P2**（中等问题）

---

## P3 边界 / 轻微

### #12 ETF overlay 起点不对齐

- **文件**：[`.tools/dashboard/dashboard_helpers.py:788-810`](../../.tools/dashboard/dashboard_helpers.py)
- **证据**：
  - 个股和每只 ETF 各自取 `iloc[0]` 为 base
  - "相对涨幅" 列名误导（不是同一起点的相对涨幅）
- **影响范围**：
  - ETF 行业对标图视觉误导
- **建议修复**：
  - 取所有 series 共同起点的最大日为 base
  - 所有 series 在该日归一化为 100
- **优先级**：**P3**

---

### #13 industry_focus tab `@st.cache_data(ttl=3600)` 缓存 1h

- **文件**：[`.tools/dashboard/tabs/industry_focus.py`](../../.tools/dashboard/tabs/industry_focus.py)
- **证据**：
  - 装饰器 `@st.cache_data(ttl=3600)` = 缓存 1 小时
- **影响范围**：
  - 修数据后 1h 内不刷新
- **建议修复**：
  - (a) UI 加手动 refresh 按钮
  - (b) 或 ttl 缩短到 300（5min）
- **优先级**：**P3**

---

### #14 graham_steps safety_margin 公式分母不一致

- **文件**：[`.tools/dashboard/graham_steps.py:599-604`](../../.tools/dashboard/graham_steps.py)
- **证据**：
  - safety_margin 分母在不同分支不统一
- **影响范围**：
  - 安全边际数值口径漂移
- **建议修复**：
  - 统一为 `(graham_value - price) / price`
- **优先级**：**P3**

---

### #15 蜜雪集团 02097 港股仅 2 年估值 / 5 年财务

- **数据来源**：`preson.duckdb` 蜜雪 02097
- **证据**：
  - 港股数据源问题（非 bug）
  - 估值 2 年 / 财务 5 年
- **影响范围**：
  - 蜜雪长期回测不可靠
- **建议修复**：
  - 文档化在公司摘要里
  - 蜜雪 score card 加 "数据窗口短" 标签
- **优先级**：**P3**（非 bug）

---

### #16 中际旭创 300308 2017 PE 极值 2733

- **数据来源**：`preson.duckdb` 中际 300308
- **证据**：
  - 2017 年 PE 极值 = 2733
  - 可能为 IPO 早期合理数据
- **影响范围**：
  - 影响 PE 分位计算（极端值拉高分布）
- **建议修复**：
  - 加 IPO 标记字段，分位计算可选排除前 N 年
- **优先级**：**P3**

---

## 误报归档（已排除）

### #17 主库 agent 报 `prices.pct_change` 百倍错 — **实测假阳性**

- **数据来源**：`preson.duckdb` 表 `prices`
- **实测**：
  - 300308 2026-04-30: `close=5661.28`, `prev=5578.75`
  - 自算 pct = `(5661.28 - 5578.75) / 5578.75 × 100 = 1.4794%`
  - 库里 `pct_stored = 1.4794`, ratio = 1.000025
- **结论**：
  - 字段单位就是**百分点**（1.4794 = 1.48%）
  - **没有 bug**，agent 误报
- **归档备查**

---

## 修复建议优先级排序

1. **修 P0 #1**：peers 重跑 + 实时算切换（高 ROI，影响所有行业分析）
2. **修 P0 #2**：美的 PEG fallback 阈值（10 行代码，立刻解锁林奇判定）
3. **修 P1 #3**：PE 分位口径统一（先统一接口，再批量替换调用方）
4. **修 P1 #4**：决策保留还是退役 `industry_pe` 表
5. **修 P2 #5-#11**：评分体系 7 项（按 yaml 模块分批，茅台/招行/美的为验证集）
6. **修 P3 #12-#16**：UI / 边界问题（低优先级，可纳入下个 sprint）

---

## 元信息

- 稽核日期：**2026-05-14**
- 方式：4 个 agent 并行检查 + 主对话亲验
- 范围：data/peers.duckdb / data/preson.duckdb / .tools/rules/*.yaml / .tools/score/engine.py / .tools/dashboard/*.py
- 黄金类问题：本次正在修复，**不在本清单**
- 后续：见 [MEMORY.md](../../../.claude/projects/-Users-gongyong-Desktop-Keyi-preson/memory/MEMORY.md) 索引行
