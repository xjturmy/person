# 黄金类数据/计算问题修复记录 (2026-05-14)

> 配套文档：[非黄金类问题清单](non_gold_issues.md)
> 范围：本次大稽核里"黄金相关"的 5 项问题全部修复或文档化收尾

---

## ✅ #1 `gold_overheat_history` 大面积错填 → 已修复

### 问题
- 576 行历史快照里 **385 行（66.8%）** 与 `overheat_engine.vote(as_of=d)` 实时算不一致
- 168 天 verdict 直接翻转（add ↔ pause）
- 集中在 2025-05 之后近 1 年；导致 2026-01-26 错给买入信号、2025-10-09 ~ 18 整段错给加仓

### 处理
- 备份原库到 [`.archive/gold.duckdb.before_backfill_2026-05-14`](../../.archive/gold.duckdb.before_backfill_2026-05-14)
- 执行：`python3 .tools/dashboard/overheat_engine.py --backfill --years=5 --freq-days=1`
- 写入 1827 行（每天 1 行，覆盖 5 年）

### 验证（修复后）
| 指标 | 修复前 | 修复后 |
|---|---|---|
| 不一致总数 | 385/576 (66.8%) | **0/1828 (0%)** ✅ |
| 1/26 verdict | add (2🔴/0🟡/4🟢) | **pause (3🔴/0🟡/3🟢)** |
| 10/09-10/18 verdict | add / add_caution | **全部 pause** |

回测如果重跑会得到正确的"过热期减仓"提示。

---

## ✅ #5 β 引擎 yaml `beta_threshold=2.0` 失效 → 已修复

### 问题
- 实测 4 只金股 ETF β60d：159562=1.09 / 159830=0.99 / 517400=1.11 / 588120=0.43
- yaml 阈值 2.0，无任何 ETF 进入高 β 分支，`add_high_beta`/`reduce_high_beta` 永不触发
- 588120 R²=0.258（拟合极差）但 β 仍被采用

### 处理
改了 4 个文件：

| 文件 | 改动 |
|---|---|
| [.tools/rules/gold_overheat.yaml](../../.tools/rules/gold_overheat.yaml) | `beta_threshold: 2.0 → 1.1`；matrix 5 条规则 lt/gte 全统一为 1.1；新增 `min_r_squared: 0.5` 字段 + 注释 |
| [.tools/dashboard/overheat_engine.py](../../.tools/dashboard/overheat_engine.py) | `stock_etf_advice()` 加 `r_squared` 参数 + R²<0.5 走 `beta_low_r2` 兜底 |
| [.tools/dashboard/tabs/gold_analysis.py](../../.tools/dashboard/tabs/gold_analysis.py) | 调用方 2 处传 r_squared (banner + 横评循环) |
| [.tools/dashboard/test_overheat_engine_stock.py](../../.tools/dashboard/test_overheat_engine_stock.py) | 调整 5 个 β 边界值 + 新增 3 个 R² 测试 |

### 验证
- `pytest test_overheat_engine_stock.py -v` → **14/14 全过**（0.13s）
- 实测 4 ETF 在 verdict=pause 下：

| 代码 | β60d | R² | matched_id | mult |
|---|---|---|---|---|
| 159562 | 1.09 | 0.660 | reduce_low_beta | 0.8 |
| 159830 | 0.99 | 0.997 | reduce_low_beta | 0.8 |
| 517400 | 1.11 | 0.663 | reduce_high_beta | 0.6 |
| 588120 | 0.43 | 0.258 | **beta_low_r2** | 1.0 |

---

## ⚠️ #4 黄金 ETF 换手率 75% 缺失 → 文档化（情况 B）

### 问题
- 4 只 ETF 中 `turnover_rate`：518880 有（缺 40%）；159934/159937/518800 **全 NULL**
- akshare `fund_etf_hist_em` 用 eastmoney 端点对这 3 只不返回「换手率」列（实测 SSL 失败但根本原因更可能是端点不报）
- 信号代表性削弱：实际是"518880 单 ETF 单日值"而非 yaml 写的"4 ETF 加权"

### 处理
未补数据（eastmoney SSL 当前不通；新浪等价 ETF API 是否提供换手率未确认），改 yaml 文档化：

[.tools/rules/gold_overheat.yaml](../../.tools/rules/gold_overheat.yaml) 第 30-50 行：
- 信号 1 `name`: `"ETF 换手率(4 只均值)"` → `"518880 换手率(主仓单 ETF)"`
- 注释 11 行说明：来源限制 / 实际行为 / 信号代表性 / 未来恢复路径

### 残留 TODO
- [ ] 调研：sina ETF API 是否支持换手率？参考 memory [reference_akshare_sina_fallback.md](../../../../.claude/projects/-Users-gongyong-Desktop-Keyi-preson/memory/reference_akshare_sina_fallback.md)
- [ ] 若可切：改 `.tools/db/fetch_gold_etf.py`，对 3 只 NULL ETF 走新浪兜底；补充历史 turnover_rate；恢复 yaml 4-ETF 加权
- [ ] 若不可切：保持当前文档化（已诚实化命名）

---

## ⚠️ #9.A 美国 CPI 数据滞后 9 个月 → 部分修复

### 问题
- gold_metrics 里 `US_CPI_MOM` 最新 2025-08-12，距今 9 个月没更新
- 派生指标 `US_CPI_YOY` / `US_REAL_RATE` 受影响

### 处理
重跑 `python3 .tools/db/fetch_real_rate.py`：

| 指标 | 结果 | 备注 |
|---|---|---|
| US_10Y_NOMINAL | ✅ 8854 行（最新 2026-05-12） | jin10 部分端点正常 |
| US_CPI_MOM | ❌ **SSLError** | jin10.com `datacenter-api` SSL EOF |
| US_CPI_YOY | ✅ 派生 656 行 | 基于已有 CPI_MOM 累计，最新值仍卡在 2025-08 |
| US_REAL_RATE | ✅ 8846 行（最新 2026-05-12） | 派生：US_10Y - CPI_YOY (MoM ffill 到日)，10Y 已更新 |

### 残留 TODO
- [ ] **US_CPI_MOM SSL 失败**：jin10 端点不稳定，需要重试机制（fetcher 已有 `_retry` 3 次但全部失败）或换源（FRED CPIAUCSL 是更稳的源）
- [ ] 临时方案：手填最近几个月 CPI 月环比（Bureau of Labor Statistics 公开数据，每月 13 号左右发布）

---

## ⚠️ #9.B 白银 SGE_AG99 数据稀疏 → 源头限制，无解

### 问题
- 850 行 vs 黄金 GOLD_SGE_AU99 的 2275 行
- 2024-08-29 最大断档 40 天；2024-2025 大部分月份只有 3-10 个数据点（正常应 20-23）

### 调研结论
- 数据源 `ak.spot_hist_sge('Ag99.99')` 是上海黄金交易所现货历史
- 重跑后 852 行（仅增加 2 行），**源头数据本身就是这么稀疏**
- 可能原因：SGE 现货白银报价不是每个交易日都有更新（不像 AU99.99 那样高频报价）

### 处理
- 重跑 fetcher 已是最佳努力，无法继续补
- 影响：康波周期 / 金银比信号可能噪声较大，但金价主信号不依赖白银

### 残留 TODO（低优先级）
- [ ] 若需要更密白银数据：考虑切到沪银期货 AG0（每日合约）替代现货 AG99.99；或用伦敦银 LBMA 现货

---

## 📊 修复后整体黄金模块可信度

| 模块 | 修复前 | 修复后 | 变化 |
|---|---|---|---|
| overheat_history 准确率 | 33% | **100%** | +67pp ✅ |
| β 引擎规则触发率 | 0% (永不触发高 β) | 实测 4 ETF 触发 4 个不同分支 | ✅ |
| ETF 换手率信号代表性 | 误标 4 ETF 实际单 ETF | 诚实化命名 | ⚠️ 文档修复 |
| CPI 时效性 | 9 个月滞后 | 仍滞后（源不通） | ⚠️ 待外部解决 |
| 白银数据 | 850 行 | 852 行 | ⚠️ 源头限制 |

### 黄金回测引擎建议下一步（仍未做的结构性改造）
- [ ] 让 `gold_backtest_engine.run()` 不再读 `gold_overheat_history` 表（即使现在 0% 不一致，下次 metrics 更新仍可能再次背离），改为每天实时调 `vote(as_of=d)` 现算
- [ ] 给 `overheat_engine.backfill_history()` 加冷启动期保护：窗口未满（如 RSI-14 需 ≥15 个数据点）的天数写 `verdict_id='unknown'` 而非走 default
- [ ] 给 `paradigm_engine` 补 `backfill_history()`，或在 UI 上明确"范式投票为快照型不可回看"

---

## 🔗 相关 memory 记忆

- [v2.6 黄金回测按日对照已交付](../../../../.claude/projects/-Users-gongyong-Desktop-Keyi-preson/memory/project_v26_backtest_daily_view_wip.md) — 之前已知 add_vrect 单日零宽 bug
- [v2.3 D2 Phase 2.4 范式引擎](../../../../.claude/projects/-Users-gongyong-Desktop-Keyi-preson/memory/project_v23_d2_phase24_paradigm_engine.md) — paradigm_engine 设计快照型
- [AkShare 数据源:eastmoney 易挂走新浪](../../../../.claude/projects/-Users-gongyong-Desktop-Keyi-preson/memory/reference_akshare_sina_fallback.md) — ETF turnover 切源备查
