# 📊 preson 项目进展追踪 v2.0

> 4 维度 12 任务进度看板,匹配 [PROJECT_PLAN.md](PROJECT_PLAN.md) v2.0
>
> **最后更新**:**2026-05-10 v2.5 TODO #1 三大师 16 条已交付 + TODO #2 行业分析与聚焦标准版全交付** — TODO #1:林奇 L1-L5 / 巴菲特 B1-B5 / 格雷厄姆 G1-G6 16 条 4 agent 并行(3 实施 + 1 验收);51/51 测试全过;TODO #2:一次性把 v2.5 TODO #2(标准版)+ v2.4 候选 ⑪(走偏 step-C 重启)合并落地;6 任务包并行 / 102 项测试全过 / 「🏭 行业分析」Tab 上线。
>
> | 任务包 | 子任务 | 状态 | 产出 |
> | :-: | --- | :-: | --- |
> | 01_knowledge | D1+D2+D3 知识层 | ✅ | industry_master.yaml(14 行业含 8 重点)+ industry_etf_mapping.yaml(19 行业)+ 8 篇 SW L2 知识 md(各 47 行) |
> | 02_percentile | E1 行业估值分位 | ✅ | industry_percentile_engine.py(三级降级)+ 20 测试 |
> | 03_screener | E4 候选 ⑪ 重启 Top 7 选优 | ✅ | focus_industries.yaml + industry_type_map.yaml + industry_screener.py(652 行)+ 22 测试 |
> | 04_cycle | E2 行业周期判定 | ✅ | industry_cycle_engine.py(580 行 / 9 格 RULE_TABLE / 三信号融合)+ 22 测试 |
> | 05_etf_recommender | E3 ETF 推荐 | ✅ | etf_recommender.py(390 行 / 流动性分位 / 1y 涨跌)+ 20 测试 |
> | 06_tab_ui | F1+F2+F3+F4 + G1+G2 | ✅ | tabs/industry_focus.py(415 行 / 4 区行业卡 / sidebar 编辑)+ app.py PAGE_INDUSTRY + 18 测试(含 AppTest) |
>
> **v2.4 候选 ⑪ 行业聚焦 = 已收口**(随 v2.5 TODO #2 一并交付,Top 7 选优 + 大师评分自动分流复用)
>
> v2.4 残留:**step-A 数据首次抓数**(用户在终端跑一次 `python3 .tools/db/fetch_market_spot.py` ~7-8min,扩到全 A 股 ~5400 行行业池)
>
> v2.5 剩余项已全部迁移到 [v2.6 附录 PATCH-1..4](PROJECT_PLAN_v2.6.md)(以 v2.6 为分界点统一归并;PATCH-1 greenblatt 下架 + PATCH-2 行业 × 康波联动 + PATCH-3 大师回测 + PATCH-4 v2.1 文件归档 ✅)。
>
> 详见下方 [📝 版本日志](#-版本日志)。

---

## 📈 总体进度

```text
MVP 关键路径(W1~W6):
[████████████████████] 100% 维度1🥇 数据层    ✅ 8 表 / 573k 行 / 周末 cron + bank_metrics + turnover
[████████████████████] 100% 维度2🥇 能力层    ✅ 4 MCP 工具挂载验证通过
[████████████████████] 100% 维度3🥇 交互层    ✅ 4-tab + V4 MCP 分位 + Dashboard M0-M5 + M6 林奇 Tab
[█████████████████░░░]  85% 维度4🥇 体系层    🟢 4.1+4.2+4.3 + P3 部分解锁;NPL/CET1/EV·NBV 仍需外部源
```

**MVP 关键路径累计 ~97%** · W1 单周完成原 W1-W5 计划 · 节省 7 周容量

**当前周次**:W1(2026-05-03 ~ 05-09)

---

## 📌 待办清单(2026-05-07)

| # | 任务 | 维度 | 阻塞 | 备注 |
| --: | --- | :-: | :-: | --- |
| 0 | **v2.3 三方向计划已起草** | — | 无 | [PROJECT_PLAN_v2.3.md](PROJECT_PLAN_v2.3.md);D1 林奇深化 / D2 黄金模块 / D3 格雷厄姆;~42h / 4 周 |
| 0.1 | **v2.3 D2 Phase 2.1 黄金方法论 6 件套** ✅ | 3 | 完成 | [12_黄金投资法/](01_knowledge/03_投资策略与选股/12_黄金投资法/);7 文件 / 1824 行;基于鲁政委 + 周金涛已读分析 |
| 0.1.1 | **v2.3 D2 Phase 2.2 黄金数据层(gold.duckdb 8 表)** ✅ | 1+3 | 完成 | [data/gold.duckdb](data/) 46,203 行 + [.tools/db/gold_schema.py](.tools/db/gold_schema.py) + 4 fetch 脚本 + 接入 update.py weekly cron;最新数据快照:实际利率 +1.63% / 金油 51.4 / 金银 53.3(SGE 国内口径);SPDR 持仓 jin10.com 卡 → 走 .config/spdr_holdings_manual.csv 备选 |
| 0.1.2 | **v2.3 D2 Phase 2.3 黄金 Dashboard Tab** ✅ | 3 | 完成 | [gold_data.py](.tools/dashboard/gold_data.py) 375 + [tabs/gold_analysis.py](.tools/dashboard/tabs/gold_analysis.py) 581 + app.py PAGE_GOLD 挂载;5 sub-tab(范式/实际利率/周期/比率/ETF)+ 黄金渐变 banner |
| 0.1.3 | **v2.3 D2 Phase 2.4 范式投票引擎(D2 100% 收口)** ✅ | 3+4 | 完成 | [.tools/rules/gold_paradigm.yaml](.tools/rules/gold_paradigm.yaml) 214 + [paradigm_engine.py](.tools/dashboard/paradigm_engine.py) 442;15 信号 × 5 source 类型(metrics/ratios/manual_const/manual_csv/not_implemented)+ 8 identity_rules;UI 切到 verified=True;首次写入 paradigm_signals 15 + history 1 行;接入 update.py weekly cron(record_snapshot 自动调度)|
| 0.2 | **v2.3 D3 阶段 A 格雷厄姆方法论 13 件套** ✅ | 3 | 完成 | [01_格雷厄姆投资法/](01_knowledge/03_投资策略与选股/01_格雷厄姆投资法/);13 文件 / 2724 行;深度价值五步 + 四类公司 ABCD/12345 + 99 双体系对照(对锚 16 家持仓)|
| 0.3 | **v2.3 D3 阶段 B+C Graham Tab + bank/insurance YAML** ✅ | 3 | 完成 | [graham_steps.py](.tools/dashboard/graham_steps.py) 893 + [tabs/graham_analysis.py](.tools/dashboard/tabs/graham_analysis.py) 698 + 7/7 测试 + [graham_bank.yaml](.tools/rules/graham_bank.yaml)/[graham_insurance.yaml](.tools/rules/graham_insurance.yaml);AppTest 5 公司渲染通过 |
| 0.4 | **v2.3 D1 块 A 林奇增长连续性修复** ✅ | 3 | 完成(commit d0c1183) | `quarterly_continuity()` 纯函数 + `QuarterlyContinuity` dataclass 跨模块共享;`lynch_abcd_scorer` stalwart/fast_grower 1.2 项接 8 季 hits_10/hits_20;`lynch_analysis` 第 2 步层 2 重写(4 列指标卡 + 铁律达标/退化提示);**茅台 stalwart 92/100 A 级**(旧 1.5% 误判修复)/ 恒瑞 7/8 满足铁律 15/15 / 比亚迪 4/8 边缘 / 招行真实断档维持 3/15 |
| 0.5 | **v2.3 D1 块 B 林奇知识库 5/6 + PEG/口径表** ✅ | 3 | 完成(commit d0c1183) | `02_彼得林奇投资法/` 6 → **10 个 md**;新增 [05 困境反转](01_knowledge/03_投资策略与选股/02_彼得林奇投资法/05_困境反转型_ABCD评估.md) 210 + [06 隐蔽资产](01_knowledge/03_投资策略与选股/02_彼得林奇投资法/06_隐蔽资产型_ABCD评估.md) 213 + [07 PEG 速查](01_knowledge/03_投资策略与选股/02_彼得林奇投资法/07_PEG估值速查.md) 239 + [08 六类口径表](01_knowledge/03_投资策略与选股/02_彼得林奇投资法/08_六类公司估值口径表.md) 165;~825 新行;命名偏差 03/04 → 07/08(避开冲突)|
| 0.6 | **v2.3 D1 块 C Phase A+B+C(全 4 阶段)** ✅ | 3 | 完成 | A:peers.duckdb 28 行 / 19 列(关键 6/8 列 100% 覆盖,PEG 68%)+ self_metrics 14 行;B:[industry_percentile.py](.tools/dashboard/industry_percentile.py) + [industry_compare_view.py](.tools/dashboard/industry_compare_view.py) + 公司 Tab 区块 C「🏭 行业横评」sub-tab;C1-C3:[peer_advice.yaml](.tools/rules/peer_advice.yaml) + [peer_advisor.py](.tools/dashboard/peer_advisor.py) + 区块 A Hero「💡 vs 同行业」卡;C4:[snapshot.py](.tools/decisions/snapshot.py#L112) `capture()` 自动注入 peer_advice + 决策日志 vs 同行 列 + 录入 expander 内动态色 banner;AppTest 0 异常;茅台高估 -9 / 招行低估 +12 / 美的合理 +1 / 新华低估 +10 |
| 0.7 | **v2.3 D3 阶段 C 4 项收尾(D3 100% 收口)** ✅ | 3 | 完成(commit ebb72ab) | Item 1 [market.py:_section_company_graham_number](.tools/dashboard/tabs/market.py) ②.5 单公司 PE×PB 实时位置卡片;Item 2 [graham_peer_radar.py](.tools/dashboard/graham_peer_radar.py) 5 维归一化(PE/PB/DY/流动比率/资产负债率)+ self vs peers 雷达叠加 + graham_analysis.py 第四步底部 expander;Item 3 决策日志写入已实现(`_build_decision_md` → `_auto.md` 后缀);Item 4 [test_graham_steps.py](.tools/dashboard/test_graham_steps.py) **10/10 通过**(招行/美的/茅台/新华/三美 5 公司 + 决策 markdown 4 类构建);AppTest market/graham/decision_center 全 0 异常 |
| 2 | **维度 4.1 portfolio.yaml** 完整版 | 4 | 无 | 15 家持仓权重 + 调仓规则 + 行业上限;数据齐;可即开即上 |
| 3 | **维度 4 P3 金融业字典解锁** | 4 | 🔴 字典 | 用户问理杏仁要字典 / 转 Tushare / 银保监爬虫;NPL/CET1/EV·NBV |
| 4 | **副线 fs API 容错改造** | 1 | 无 | `batch_update_fs_modules.py` try-except + 重试(非阻塞) |
| 5 | **v2.4 候选 10 方向起草** ⏳ | — | 待拍板 | [PROJECT_PLAN_v2.4_候选.md](PROJECT_PLAN_v2.4_候选.md);含用户新提 ⑨ 分层公司库(L1/L2/L3 三层 ~13h)+ ⑩ 全局搜索栏(~2-3h);3 套组合方案待勾选 |
| 6 | **🔍 全局搜索栏(快速查找公司)** ⏳ | 3 | 无 | 用户 2026-05-07 提需求;顶部 `st.text_input` + 模糊匹配 ticker / 中文名 / 拼音首字母 / 行业关键词;命中跳转公司详情 Tab;~2-3h;**与候选 ⑨ 强搭配**(库扩到 ~5400 家时搜索成必需)|
| 7 | **🎯 行业聚焦 + 自动选优工作流** ⏳ | 3 | 依赖 ⑨ Phase 1 | 用户 2026-05-07 提需求("聚焦行业找优秀公司");yaml 配置 5-10 个聚焦行业 + 行业类型→评分规则映射(复用 v2.3 的 8 大师 + 林奇分类 + bank/insurance);每行业自动 Top 7 + 推荐理由 + 一键加深度;~6-8h;**与候选 ⑨ 互补**(自底向上 vs 自顶向下)|
| 9 | **🌐 L1 全市场快照层(候选 ⑨ Phase 1)** 🟢 | 1+3 | 待跑首次抓数 | v2.4 step-A 代码全交付(2026-05-09):[fetch_market_spot.py](.tools/db/fetch_market_spot.py) 325 行(AkShare `stock_zh_a_spot_em` + EM 行业映射 + retry/进度条)/ [tabs/market_scan.py](.tools/dashboard/tabs/market_scan.py) 229 行(行业 selectbox + PE/PB/股息率/市值滑块 + 表格)/ [app.py](.tools/dashboard/app.py) PAGE_SCAN 挂在黄金 Tab 后 / [update.py](.tools/db/update.py) 加 step_market_spot 接入 weekly cron(`--skip-market-spot` 兜底);**未收口项**:`data/market.duckdb` 未生成,需用户跑一次 `python3 .tools/db/fetch_market_spot.py`(中国网络 ~7-8min,5400 家全 A 股) |
| 10 | **🔍 全局搜索栏(候选 ⑩)** ✅ | 3 | 完成 | v2.4 step-B 全交付(2026-05-09):见下方 ⑩ 详解 |
| 11 | **🎯 行业聚焦 + 自动选优(候选 ⑪)** 🔴 | 3 | 未启动 / 走偏 | ⚠️ 任务包 [../tasks/v2.4_p0/step-C_industry_focus.md](../tasks/v2.4_p0/step-C_industry_focus.md) 未落地;并行窗口把"step-C"理解成了候选 ③ 03 芒格 Tab(见 #12),原计划候选 ⑪(focus_industries.yaml + industry_screener.py + tabs/industry_focus.py)0 文件;**重启需求**:用户拍板后开新窗口重做 step-C(强依赖已落地的 step-A market.duckdb,可在 step-A 抓数完成后启动)|
| 12 | **🧠 03 芒格多元思维 Tab(候选 ③ 第 1 个 Tab)** ✅ | 3 | 完成(意外加项) | v2.4 候选 ③(2026-05-09):[tabs/munger_analysis.py](.tools/dashboard/tabs/munger_analysis.py) 772 + [test_munger_tab.py](.tools/dashboard/test_munger_tab.py) 226;5 sub-tab(① 速览 / ② 10 项决策清单加权打分 / ③ 反向思维 16 失败路径 / ④ 9 项心理偏差自检 / ⑤ md 报告导出);第 4/5/9 项数据钩子接 lynch_classifier 实时拉 PE/PB/股息率/ROE/PEG;[app.py](.tools/dashboard/app.py) PAGE_MUNGER 挂在黄金 Tab 后;紫色 banner 区分;8/8 测试通过;⚠️ 与 step-C 候选 ⑪ 同字不同物 |
| 8 | **⏱ 黄金短期过热信号引擎(D2 扩展)** ✅ | 3 | 完成 | v2.4 step-D 全交付(2026-05-09):[gold_overheat.yaml](.tools/rules/gold_overheat.yaml) 137 行 + [overheat_engine.py](.tools/dashboard/overheat_engine.py) 309 行(照 paradigm_engine 模式);6 信号 × 3 档红绿灯(换手率/volume ratio 5d/60d/RSI-14 Wilder/MA60 偏离/share change 5d/期货基差占位)+ 5 verdict + 8 trend_combo;[gold_schema.py](.tools/db/gold_schema.py) 8 → 10 表(`gold_etf_share` + `gold_overheat_history`)+ `gold_etf_prices.turnover_rate` ALTER 迁移;[tabs/gold_analysis.py](.tools/dashboard/tabs/gold_analysis.py) 加红/黄/绿对偶 banner + 第 ⑥ sub-tab(信号矩阵 + 365 天 stacked bar + 联动建议);接 [update.py](.tools/db/update.py) weekly cron;AppTest 0 异常 / 5/6 信号真实数据 / 期货基差待 P3 接 AkShare |

---

## 🚨 当前阻塞 / 已知风险

| 项 | 状态 | 出路 / 备注 |
| --- | :-: | --- |
| 理杏仁金融业 metric 字典未公开(NPL/CET1/EV/NBV) | 🔴 P3 | 用户提供字典 / 转 Tushare / 银保监爬虫(影响新华保险+招行评分卡) |
| ttyd 嵌入受 4 重阻塞(geo-block + Keychain ACL + 版本错配 + CLAUDECODE 嵌套) | 🟡 已转方案 B | VS Code Claude 旁挂(等价 UX);P3 备选 — 切合规节点后可启用 |
| 蜜雪集团港股 IPO < 1 年 / 三美 2019 上市 | 🟡 数据天花板 | 无解,4 项 critical 永久挂起 |
| 五粮液 PE-TTM 174.7(全窗 100%) | ✅ 不处理 | 新闻所致真实数据;dashboard 如实显示 |
| 自算分位 vs 理杏仁 10 年口径差 87pp | ✅ 已解除 | 13 家重抓 549k 行后 → 0.04pp |

---

## 🏢 数据状态

8 张主表 + 4 个独立 .duckdb 库:

| 库 / 表 | 行数 | 公司 | 来源 | 备注 |
| --- | ---: | ---: | --- | --- |
| `preson.duckdb` 8 表 | 573,271 | 15 | 理杏仁 + AkShare | 含 valuation 549k(P0 后扩 13.2x) |
| · 派生 `bank_metrics` | — | 4 银行项 | sina BS+IS 派生 | provision_to_loans / 净利息率 / 增速 |
| `macro.duckdb` | 5 项时序 | — | 理杏仁 + AkShare | A_FULL_PE / 10Y_YIELD / CPI / M2 / USDCNY |
| `turnover.duckdb` | 2,820 | 12 | sina BS+IS 派生 | 林奇护栏 5/5(存货/应收/总资产周转) |
| `etf.duckdb` | 484 | 35 ETF | — | ETF 行业对标 |
| `peers.duckdb` | — | — | 同行池 | 多公司同行雷达基础 |
| `decisions.duckdb` | — | — | M4 智能录入 | 决策日志独立库 |
| `gold.duckdb` 8 表 | 46,203 | — | SGE + AkShare + 派生 | Phase 2.2 黄金;6/8 表填充;paradigm 2 表等 Phase 2.4 |

**数据天花板**:03_蜜雪集团 4 项 critical / 02_三美股份 估值 71% / 银行/保险负债率字段缺(理杏仁口径)

---

## 📊 4 维度完成度

| 维度 | 完成度 | 关键产出 |
| --- | ---: | --- |
| **1 数据层** | **100%+** | 1.1 ingest(8 表)+ 1.2 validate + 1.3 AkShare cron + 副线 P0 解除(13 家 10y 补抓)+ bank_metrics + turnover |
| **2 能力层** | **100%** | 4 MCP 工具(query_metric / latest_snapshot / compare_peers / valuation_percentile)+ 三件套增强(freshness/percentile/errors)+ stdio 挂载验证 |
| **3 交互层** | **100%+** | 4-tab Streamlit 骨架 + V4 MCP 分位 + Dashboard 优化 M0-M5(9/9)+ M6 林奇五步法 Tab(2567 行)+ ETF 行业对标 + 决策中心 M4 |
| **4 体系层** | **85%** | 4.1 portfolio.yaml v0 + 4.2 评分引擎(F-Score 9/9 + 行业自动切换 + 多大师矩阵)+ 4.3 月度复盘模板;P3 部分解锁(招行 piotroski_bank v2 5-7 区间) |

详细子任务交付见各维度的代码与记忆 ([memory/](.claude/projects/-Users-gongyong-Desktop-Keyi-preson/memory/))。

---

## 📝 版本日志

| 日期 | 阶段 | 变更摘要 |
| ------ | --- | ------ |
| **2026-05-10** | v2.5 TODO#1 | **三大师评分体系优化(林奇 L1-L5 / 巴菲特 B1-B5 / 格雷厄姆 G1-G6)16 条全交付** — 4 agent 并行(3 实施 + 1 验收);51/51 测试全过(lynch 17 + buffett 12 + graham 22) — **林奇**:[lynch.yaml](.tools/rules/lynch.yaml) 新增 slow_grower / cyclical / turnaround / asset_play 四类型专属规则段 + L2/L3/L4/L5 修正 3 条规则(score_if_partial / verified=false / 权重降级);[lynch_extras.py](.tools/dashboard/lynch_extras.py) 4 函数(`insider_proxy_score` / `institutional_holding_proxy` / `peg_curve_grade` / `quarterly_continuity_score`)— **巴菲特**:[buffett.yaml](.tools/rules/buffett.yaml) 5 条规则全 5 档梯度化(0/0.5/1/1.5/2 替代 0/2 二值)+ `industry_alternatives` 段(bank PB-ROE / insurance EV·NBV 占位 / high_rd_tech R&D 还原占位)+ `qualitative_moat` 5 项护城河主观打分占位;[buffett_extras.py](.tools/dashboard/buffett_extras.py) 5 函数(`industry_alt_oe_score` / `compute_owner_earnings` / `simple_owner_earnings` verified / `retained_earnings_breakdown` / `load_qualitative_score`);[.config/buffett_qualitative.yaml](.config/buffett_qualitative.yaml) 空模板 — **格雷厄姆**:[graham.yaml](.tools/rules/graham.yaml) g7 改 OR 条件(`formula_primary` PB≤1.5 / `formula_alt` PE×PB≤22.5)+ g4 数据源切 derived + `ncav_critical_bonus` +3 分;[graham_router.py](.tools/dashboard/graham_router.py) 行业自动选 yaml(主/bank/insurance);[graham_extras.py](.tools/dashboard/graham_extras.py) `parse_g7_or` / `compute_ncav_status` / `STEPS_TO_YAML_RULES_MAP`;[graham_schloss_view.py](.tools/dashboard/graham_schloss_view.py) 15 项 Schloss 简版;[derived_metrics.py](.tools/dashboard/derived_metrics.py) 追加 `years_continuous_dividend`(仅追加,其余函数未动,git diff 验证);[graham_yaml_steps_mapping.md](.tools/rules/graham_yaml_steps_mapping.md) 文档化 — **P1+P2 修复(本次会话同步收口)**:[engine.py](.tools/score/engine.py) 加 `eval_rule(rule, evaluator)` 共享 helper 统一处理三种 schema(classic `formula` / `formula_primary`+`formula_alt`+`pass_logic` OR/AND / `grades` 多档求值);[multi_master.py](.tools/score/multi_master.py) + [dashboard_helpers.py](.tools/dashboard/dashboard_helpers.py) + [screener.py](.tools/dashboard/screener.py) `_score_one_master` 全部切到 `eval_rule`(`rule["formula"]` KeyError 解除);**P2 graham_router 接 screener**:`score_with_master(df, "graham", year)` 入口加按 ticker 路由(主/bank/insurance 自动切),招行/新华不再永远走主 yaml — **测试**:67/67 全过(extras 51 + AppTest 16);**实战 smoke**:graham 茅台/招行/新华/美的 路由分流正确(招行 7 总规则走 bank yaml / 茅台 8 走主 yaml),buffett grades 茅台 score=2.0 命中 excellent 档(CAGR ≥ 15%) — **已知后续**:extras.py 3 套函数为独立模块,UI Tab 集成待后续版本 |
| **2026-05-09** | step-D 收尾 | **v2.4 黄金过热历史回填 + 仓位走廊 UI**(用户提"历史回看为空,补 5 年和 1 年" + "短期热度对仓位影响的变化") — **数据**:[overheat_engine.py](.tools/dashboard/overheat_engine.py) 5 个数据源函数全加 as_of 参数(向后兼容,None=最新);新增 `backfill_history(years, freq_days)` + CLI `--backfill`;实跑两轮(5y/7d + 1y/1d) → `gold_overheat_history` 575 行(2021-05 ~ 2026-05;近 1 年 366 行日级 + 1 年外 209 行周级)— **真实过热警示点回看**:2024-04-21 / 2025-04-20 / 2025-10-12-19 连续 6 天 / 2026-01-25 都被捕获 — **UI**:[tabs/gold_analysis.py](.tools/dashboard/tabs/gold_analysis.py) ⑥ 短期过热扫描内,历史回看右上加「近 1 年 / 近 5 年」radio 切换,caption 实时报"共 N 个采样点";新增「📐 仓位走廊」expander 默认展开:3 输入(战略目标 X% / 当前持仓 Y% / 周期 N 周)→ plotly 水平条(浅灰带=走廊 + 虚线=目标 + 蓝点线=战略上限 + 圆点=当前 Y)+ 决策卡(▲加仓/→持有/▼减仓 + 当前档 + 走廊上下界 + 本周建议%) + 路径预测("约 N 周达上界") — **后端**:[gold_overheat.yaml](.tools/rules/gold_overheat.yaml) 加 `position_corridor` 段(5 档 × discount 1.00/0.95/0.85/0.70/0.60 + tolerance ±2% + default_strategic_pct=20 + default_period_weeks=26)/ [position_corridor.py](.tools/dashboard/position_corridor.py) 113 行 `compute_corridor()` 纯函数 + `Corridor` dataclass / [test_position_corridor.py](.tools/dashboard/test_position_corridor.py) 15 项单测(5 档折扣 × add/hold/reduce 三分支 × 实战 2024-04 案例 × 边界);**核心模型**:短期热度 = 战略上限的"动态折扣率",走廊 = X×discount ± 2%;Y 与走廊比较 → 加/持/减;阶梯式上限折扣 ≠ 步长倍率 — **测试**:position_corridor 15/15 + company_search 18/18 + AppTest smoke = 34/34 PASSED — **已知未修**:`gold_overheat.yaml` 的 verdict_rules 当 red=2 且 yellow<3 时落兜底"全绿"显示有 bug,banner 标签会错(走廊不受影响,走廊读 verdict_id 而非 label) |
| **2026-05-09** | step-A | **v2.4 step-A L1 全市场快照层代码交付**(候选 ⑨ Phase 1 P0 / ~6h 实落地;用户原话"每行业看多家公司,选效率太低")— **数据层**:新建 [.tools/db/fetch_market_spot.py](.tools/db/fetch_market_spot.py) 325 行(AkShare `stock_zh_a_spot_em` 一次性抓 ~5400 行 × 23 列 + 字段映射 EM中文 → 英文 schema + 重试 3 次指数退避 + 进度条 + EM 行业字符串入 industry 列 + `data/market.duckdb` 独立库不污染 prices/peers)— **简易扫描 Tab**:新建 [.tools/dashboard/tabs/market_scan.py](.tools/dashboard/tabs/market_scan.py) 229 行(行业 selectbox 从 distinct industry 取 + PE/PB/股息率/市值 4 滑块过滤 + 表格按 PE 排序 + 数据时效 caption)— **接入**:[.tools/dashboard/app.py](.tools/dashboard/app.py) `PAGE_SCAN = "🌐 全市场扫描"` 挂在黄金 Tab 后 + [.tools/db/update.py](.tools/db/update.py) 加 `step_market_spot` 接 weekly cron(`--skip-market-spot` 兜底,失败 non-blocking)— **未收口项**:`data/market.duckdb` 待用户跑一次 `python3 .tools/db/fetch_market_spot.py`(中国网络 5400 家分 58 batch ~7-8min);为候选 ⑪ 行业聚焦 + 候选 ⑩ L2 fallback 提供 industry 字段筛选源 |
| **2026-05-09** | 候选③ | **v2.4 候选 ③·03 芒格多元思维 Tab 首交付**(意外加项;并行窗口把 "step-C" 理解成候选 ③,原 step-C 候选 ⑪ 行业聚焦 0 文件) — [tabs/munger_analysis.py](.tools/dashboard/tabs/munger_analysis.py) 772 + [test_munger_tab.py](.tools/dashboard/test_munger_tab.py) 226;5 sub-tab(① 多元思维速览 4 层格栅+16 模型+7 句语录 / ② 10 项决策清单 1-5 打分加权 + 4 档决策规则 / ③ 反向思维 4 失败路径 16 checkbox / ④ 9 项心理偏差自检 + 防御策略 / ⑤ md 报告写到 `02_companies/{N}/05_投资决策/芒格决策清单_{date}_auto.md`);第 4/5/9 项接 lynch_classifier 实时拉 PE/PB/股息率/ROE/PEG;app.py PAGE_MUNGER 挂在黄金后;紫色系 banner;8/8 测试 + AppTest 0 异常 |
| **2026-05-09** | step-D | **v2.4 step-D 黄金短期过热引擎全交付**(候选 ⑫ P1 / ~5-6h 实落地;用户原话"除了博大趋势,还要知道短期是否存在过热的情况") — **数据扩展**:[gold_schema.py](.tools/db/gold_schema.py) 8 表 → 10 表(加 `gold_etf_share` ETF 份额时序 + `gold_overheat_history` 投票快照)+ `gold_etf_prices` ALTER 加 `turnover_rate` 列(idempotent 通过 `_migrate_v24_step_d` information_schema 检测)/ [fetch_gold_etf.py](.tools/db/fetch_gold_etf.py) 抽取 fund_etf_hist_em 「换手率」字段 / 新建 [fetch_gold_etf_share.py](.tools/db/fetch_gold_etf_share.py) 188 行(AkShare 无份额接口走 manual CSV / smoke 三路兜底,自动算 5d 变化率) — **过热引擎**:新建 [.tools/rules/gold_overheat.yaml](.tools/rules/gold_overheat.yaml) 137 行(6 信号 × 7 source 类型 × 3 档红绿灯 + 5 verdict_rules + 8 trend_combo 大趋势联动)/ 新建 [.tools/dashboard/overheat_engine.py](.tools/dashboard/overheat_engine.py) 309 行(`vote()` + `record_snapshot()` + `trend_combo_advice()` + Wilder 平滑 RSI-14 + 5d/60d volume ratio + 4 ETF 换手率均值,完全照 paradigm_engine.py 模式)— **Dashboard**:[tabs/gold_analysis.py](.tools/dashboard/tabs/gold_analysis.py) 加 `_render_overheat_banner` 主 banner 下方挂红/黄/绿对偶卡 + 第 ⑥ sub-tab「短期过热扫描」(4 metric + 6 信号矩阵表 + 365 天历史回看 stacked bar + 大趋势 × 短期 8 种联动建议矩阵);引擎可用时 `_OVERHEAT_AVAILABLE=True`,失败/缺数据走默认绿不阻塞 — **接入 weekly cron**:[update.py](.tools/db/update.py) 加 `fetch_gold_etf_share` + `overheat_engine --write` 两步 — **首次冒烟**:CLI engine 5/6 信号真实数据(volume_ratio 0.53x / RSI-14 49.64 / MA60 偏离 -2.99% / share_change 1.99% / turnover_rate 待 ETF 重抓后填充 / 期货基差占位 not_implemented),verdict='add' 🟢 加仓窗口 / `gold_overheat_history` 写入 1 行 / `gold_etf_share` smoke 120 行 4 ETF / **AppTest gold_analysis.render() 0 异常 + 6 sub-tabs 全渲染**;P3 待接(AkShare 期货基差 / ETF 份额真实接口) |
| **2026-05-09** | step-B | **v2.4 step-B 全局搜索栏交付**(候选 ⑩ P0 / ~2-3h 实落地) — 新建 [components/search_bar.py](.tools/dashboard/components/search_bar.py) 207 行(`load_index` + `search` 优先级降序 12 档 + `CompanySearcher` class + `search_l2_fallback` stub 留 hook + `render_search_bar` Streamlit 入口)/ [test_company_search.py](.tools/dashboard/test_company_search.py) 18 项测试(ticker/name/拼音首字母/全拼/行业/优先级/limit/L2 fallback/CompanySearcher class 全覆盖)/ [test_app.py](.tools/dashboard/test_app.py) +3 条 AppTest(gzmt → 06_贵州茅台 / 白酒 → 茅台+五粮液 / 无匹配回退 15 家);**优先级 score**:100 ticker 完全 / 95 name 完全 / 85 ticker 前缀 / 80 name 前缀 / 75-65 拼音首字母/全拼 / 60-55 行业 / 50-45 子串 / 30-44 rapidfuzz `WRatio` 兜底(阈值 75 避免短拼音噪声 zgzc vs zzzz=67% 误命中);**sidebar 接入**:`### 🎯 当前公司` 下加 `🔍 搜索` text_input,query 非空时 selectbox options 收敛到命中列表 + 哨兵 `── 📋 显示全部 ──` 重置;`_company_options_sig` 监测 options 变化清旧 session_state 防 StreamlitAPIException;**5 验收例**:茅台 / 600519 / gzmt / 白酒 / xhbx 全部命中 Top1;**测试结果**:18+3=21 新增全过 + smoke 0 异常;依赖 [requirements.txt](.tools/dashboard/requirements.txt) +`pypinyin==0.55.0` +`rapidfuzz==3.14.5`;为候选 ⑨ Phase 2 落地后 L2 industry_pool fallback 留好 hook |
| **2026-05-09** | v2.4 候选③ | **v2.4 候选 ③·03 芒格多元思维 Tab 首交付**(C 类「补齐方法论可视化」第 1 个 Tab;⚠️ 与 `../tasks/v2.4_p0/step-C` 候选 ⑪ 行业聚焦同名不同物) — [tabs/munger_analysis.py](.tools/dashboard/tabs/munger_analysis.py) 772 行 / [test_munger_tab.py](.tools/dashboard/test_munger_tab.py) 226 行;**5 sub-tab**:① 多元思维速览(4 层格栅 / 16 模型 / 4 大原则 / 7 句芒格语录)/ ② 10 项决策清单(能力圈/反向/多元/安全边际/长期/心理/护城河/管理/估值/风险 1-5 打分 + 加权平均 + 4 档决策规则)/ ③ 反向思维(行业衰退/竞争失利/管理治理/宏观政策 4 大失败路径 16 个 checkbox + 用户自填)/ ④ 9 项心理偏差自检(确认/可得性/锚定/损失厌恶/从众/权威/激励/禀赋/沉没成本 + 防御策略)/ ⑤ 决策报告导出(预览 + 下载 md + 写入 `02_companies/{N}/05_投资决策/芒格决策清单_{date}_auto.md`);**数据钩子**:第 4/5/9 项自动从 lynch_classifier 拉 PE/PB/股息率/ROE/PEG 实时参考;**测试 8/8 通过**(模块导入 + 10 项清单结构 + 决策规则 4 档边界 + data_hint + md 构建 + AppTest Default + PAGE_MUNGER + 5 sub-tab 内容渲染全命中);[app.py](.tools/dashboard/app.py) PAGES 加 PAGE_MUNGER 挂载在黄金 Tab 后;紫色系 banner(对照林奇绿/格雷厄姆蓝/黄金金) |
| **2026-05-07** | step-06 | **v2.3 D3 阶段 C 4 项收尾 → v2.3 100% 全收口**(commit ebb72ab) — **Item 1**:[market.py:_section_company_graham_number](.tools/dashboard/tabs/market.py) 在 ②.5 区块加单公司 PE×PB 实时位置卡片(4 列布局:公司 / PE+PB / PE×PB+评级 / 价值类型+置信度;sidebar selected 自动联动) — **Item 2**:[graham_peer_radar.py](.tools/dashboard/graham_peer_radar.py) 290 行(5 维归一化 0-100 buy-zone:PE/PB/资产负债率「越低越好」+ DY/流动比率「越高越好」)+ [graham_analysis.py:_render_step4_valuation](.tools/dashboard/tabs/graham_analysis.py) 第四步底部「🎯 同行雷达 · 5 维 vs 同行业」expander;peer 缺数据时优雅降级(只画 self) — **Item 3**:决策日志已在 `_build_decision_md` 实现,一键写到 `02_companies/{N}_{name}/05_投资决策/格雷厄姆五步分析_{date}_auto.md`(`_auto.md` 后缀避开人工版) — **Item 4**:[test_graham_steps.py](.tools/dashboard/test_graham_steps.py) 扩展至 **10/10 通过**(原 7 项 + 新华保险进取型 + 三美进取型 + 4 类公司决策 markdown 构建);**实测 5 公司分类**:招行 防御 PE×PB=5.4 / 美的 防御 防御 5/7 / 茅台 进取 PE×PB=132.3 / 新华 进取 PE×PB=8.93 防御 6/6 / 三美 进取 PE×PB=84.10 三防坚固;AppTest market/graham/decision_center 全 0 异常;**v2.3 完成度 ~86% → 100%**(D1 ✅ / D2 ✅ / D3 ✅);W2-W4 容量直接转入 [共享计划](共享计划.md) 公网部署 |
| **2026-05-07** | step-05 | **v2.3 D1 块 C Phase A+B+C(全 4 阶段)收口** — **A**:[fetch_peers.py](.tools/db/fetch_peers.py) v8 + peers.duckdb 28 行(关键 6/8 列 100% / PEG 68%)+ self_metrics 14 行;**B**:[industry_percentile.py](.tools/dashboard/industry_percentile.py) 9 指标分位 + IndustryPercentile dataclass / [industry_compare_view.py](.tools/dashboard/industry_compare_view.py) 8 张分位卡片 + 同行明细 CSV / [company.py:1191](.tools/dashboard/tabs/company.py#L1191) 区块 C 加「🏭 行业横评」divider;**C1-C3**:[peer_advice.yaml](.tools/rules/peer_advice.yaml) 8 维 × 5 档 + 加权 bands(总权重 11)/ [peer_advisor.py](.tools/dashboard/peer_advisor.py) advise() + MetricVerdict + PeerAdvice dataclass + render_hero_card_html / [company.py:625](.tools/dashboard/tabs/company.py#L625) 区块 A 顶部「💡 vs 同行业」Hero 卡;**C4**(本会话补完):写入端 [snapshot.py:112-140](.tools/decisions/snapshot.py#L112) `capture()` 自动注入 `peer_advice` 字段(overall_label / weighted_sum / industry / Top3 evidence)+ 显示端 [decision_center.py:668-689](.tools/dashboard/tabs/decision_center.py#L668) 决策日志加 `vs 同行` 列 + [:632-672](.tools/dashboard/tabs/decision_center.py#L632) 录入 expander 内动态色 banner(低估绿/合理黄/高估红);**端到端**:capture() 4 公司全过(茅台 -9 高估 / 招行 +12 低估 / 美的 +1 合理 / 新华 +10 低估);AppTest 决策中心 0 异常,vs 同行业关键词命中 |
| **2026-05-07** | step-04 | **v2.3 D2 Phase 2.4 范式投票引擎 + D2 100% 收口** — [.tools/rules/gold_paradigm.yaml](.tools/rules/gold_paradigm.yaml) 214 行(三大范式 × 5 信号 × 5 source 类型 + 8 identity_rules 主导身份判定)/ [.tools/dashboard/paradigm_engine.py](.tools/dashboard/paradigm_engine.py) 442 行(`load_config` + `_evaluate` 单信号 + `vote()` 投票 + `record_snapshot()` 写库 + CLI `--write`);**UI 切换**:tabs/gold_analysis.py 加 `_vote_cached()` → SimpleNamespace 适配,banner 显示 ✅ verified=True / `paradigm_engine_v1`;static_paradigm_vote 保留作 fallback;**首次写入**:gold_paradigm_signals 15 行 + gold_paradigm_history 1 行(2-4-5 / 主导 🔥+🔄 / 配置 15-20%);**AppTest** Default + PAGE_GOLD 0 异常,关键词全命中;**接入 update.py** — paradigm_engine `--write` 作 weekly cron 第 5 步,8/8 表全部填充 → **D2 黄金模块 100% 交付** |
| **2026-05-07** | step-04 | **v2.3 D2 Phase 2.3 黄金 Dashboard Tab 全交付** — [gold_data.py](.tools/dashboard/gold_data.py) 375 行(`Snapshot` / `ParadigmVote` dataclass + 6 数据查询 + `static_paradigm_vote` 静态判定 + 15 信号矩阵)/ [tabs/gold_analysis.py](.tools/dashboard/tabs/gold_analysis.py) 581 行(黄金渐变 banner + 5 sub-tab:① 三大范式投票 / ② 实际利率定价(双轴时序+四象限)/ ③ 周期定位(康波四阶段)/ ④ 关键比率(4 时序+分位仪表盘)/ ⑤ ETF 选择(归一化叠加))/ app.py PAGES 加 PAGE_GOLD 挂载在格雷厄姆 Tab 后;**离线测试**:`load_*` 6 个查询全通过(metrics 32k/ratios 9k/etf 4 行/prices 2.9k);**AppTest headless**:Default + PAGE_GOLD 0 异常 / 9/10 关键词命中 / 5 个 sub-tab 创建成功;**当前快照**:范式投票 2-3-5(3/3 中 2 激活,实际利率 +1.63 钝化范式一)→ 主导身份 🔥 抗通胀 + 🔄 周期 → 配置 15-20% |
| **2026-05-07** | step-05 | **v2.3 D1 块 A+B 林奇深化交付**(commit d0c1183) — **块 A 增长连续性修复**:[lynch_classifier.py](.tools/dashboard/lynch_classifier.py) 新增 `QuarterlyContinuity` dataclass + `quarterly_continuity()` 纯函数(路径1取 growth.同比 / 路径2从累计营收派生);[lynch_abcd_scorer.py](.tools/dashboard/lynch_abcd_scorer.py) `score_abcd` 入口注入 `m['quarterly_continuity']` + stalwart/fast 1.2 项接 hits_10/hits_20 评分;[lynch_analysis.py](.tools/dashboard/tabs/lynch_analysis.py) 第 2 步层 2 重写(4 列指标卡 + 铁律达标/退化提示);**茅台 stalwart 92/100 A 级**(旧版 1.5% 误判修复)/ 恒瑞 7/8 满足铁律 / 比亚迪 4/8 边缘 / 招行真实断档 — **块 B 知识库扩 6→10**:[02_彼得林奇投资法/05 困境反转](01_knowledge/03_投资策略与选股/02_彼得林奇投资法/05_困境反转型_ABCD评估.md) 210 行 + [06 隐蔽资产](01_knowledge/03_投资策略与选股/02_彼得林奇投资法/06_隐蔽资产型_ABCD评估.md) 213 + [07 PEG 速查](01_knowledge/03_投资策略与选股/02_彼得林奇投资法/07_PEG估值速查.md) 239 + [08 六类口径表](01_knowledge/03_投资策略与选股/02_彼得林奇投资法/08_六类公司估值口径表.md) 165;命名偏差 03/04 → 07/08 避开冲突;**v2.3 完成度 ~67%**(D3 100% / D1 50% / D2 50%) |
| **2026-05-07** | step-04 | **v2.3 D2 Phase 2.2 黄金数据层交付** — [data/gold.duckdb](data/) 8 表 46,203 行(gold_metrics 32,098 / gold_ratios 9,252 / gold_etf_prices 4,840 / gold_percentiles 9 / gold_etf_master 4);新建 [gold_schema.py](.tools/db/gold_schema.py)(idempotent DDL)+ 4 fetch 脚本([fetch_gold_prices.py](.tools/db/fetch_gold_prices.py) SGE金/银+WTI油+派生USD / [fetch_real_rate.py](.tools/db/fetch_real_rate.py) 美10Y+CPI MoM→YoY→实际利率 / [fetch_gold_etf.py](.tools/db/fetch_gold_etf.py) 4只ETF / [fetch_gold_ratios.py](.tools/db/fetch_gold_ratios.py) 金油/金银/分位);接入 [update.py](.tools/db/update.py) weekly cron(`--skip-gold` 兜底);**实测踩坑**:沪银接口单位是 CNY/kg 不是 CNY/g 已修;SPDR 持仓 jin10.com 中国 IP SSL 卡 → 走 `.config/spdr_holdings_manual.csv` 手填备选;最新快照:实际利率 +1.63%(分位 87%)/ 金油 51.4 / 金银 53.3(SGE 国内口径与 LBMA 国际口径不同) |
| **2026-05-07** | step-03 | **v2.3 D3 阶段 B+C 格雷厄姆 Dashboard Tab 全交付** — [graham_steps.py](.tools/dashboard/graham_steps.py) 893 行(四类判定 + 7 准则 + 三层防御 + NCAV + 格氏数 + 卖出触发)/ [tabs/graham_analysis.py](.tools/dashboard/tabs/graham_analysis.py) 698 行(顶部蓝色 banner + 5 sub-tab + ABCD/12345 决策矩阵 + 一键导出 md)/ [test_graham_steps.py](.tools/dashboard/test_graham_steps.py) 166 行 7/7 测试通过 / [graham_bank.yaml](.tools/rules/graham_bank.yaml) 7 准则银行变体(PB×DY ≥ 0.04 替代格氏数)/ [graham_insurance.yaml](.tools/rules/graham_insurance.yaml) v0(EV 数据待解锁)/ app.py PAGES 加 PAGE_GRAHAM 挂载;**离线后端验证**:招行(防御 PE×PB=5.4)/ 美的(防御 40.9)/ 茅台(进取 132.3)/ 伊利(防御 41.9)/ 新华(进取 8.9);**AppTest headless**:Default + Graham Tab + 多公司切换 0 异常 |
| **2026-05-07** | step-03 | **v2.3 D3 阶段 A 格雷厄姆方法论 13 件套交付** — [01_格雷厄姆投资法/](01_knowledge/03_投资策略与选股/01_格雷厄姆投资法/);13 文件 / 2724 行 / ~119KB(README + 00 总览/01 四类分类/02-05 ABCD 评估 4 套/06-10 实战 5 步重命名 + 标题对齐林奇/99 双体系对照 16 家持仓);四类:🪙 深度低估(NCAV)/🛡️ 防御型(格氏数 22.5 软达标)/⚔️ 进取型(PEG ≤ 1.0)/🎭 特殊情境(困境/重组/NAV);**格雷厄姆 vs 林奇 99 文档**给出 16 家持仓的双体系标签 |
| **2026-05-07** | step-04 | **v2.3 D2 Phase 2.1 黄金方法论 6 件套交付** — 新建 [01_knowledge/03_投资策略与选股/12_黄金投资法/](01_knowledge/03_投资策略与选股/12_黄金投资法/);7 文件 1824 行(README + 00 总览/01 三大范式/02 实际利率/03 配置量化/04 ETF 选择/05 指标速查);基于鲁政委《保卫财富》三大范式 + 周金涛康波 + 兴业 2004-2023 回测;命名采用 `12_` 避开与 `05_选ETF框架.md` 文件冲突;为 Phase 2.2(gold.duckdb + 4 数据脚本)+ Phase 2.3(tabs/gold_analysis.py)+ Phase 2.4(范式投票引擎 yaml)定下概念基线 |
| **2026-05-07** | step-03 | **林奇毛利率行业静态基准 + 格雷厄姆 UI 重构** — 新建 [industry_gm_static.py](.tools/dashboard/industry_gm_static.py) 13 家公司行业 GM 字典(白酒 78/创新药 70/汽车 17 等);[lynch_classifier._gross_margin_vs_industry](.tools/dashboard/lynch_classifier.py#L971) 加 db→static 回退 + source 字段;[lynch_abcd_scorer:245-269](.tools/dashboard/lynch_abcd_scorer.py#L245) detail 加"·静态基准(未校验)";茅台 +12.5pp 满分 / 伊利 +4.8pp 持平;银行+保险走手填。[tabs/market.py:386-466](.tools/dashboard/tabs/market.py#L386) 格雷厄姆指数:删 c3 列 + 红绿灯 4 档化(去 ≥6%)+ 当前位置加粗箭头 + 三列 `STAT_COL_HEIGHT=175px` 等高 + HTML 紧凑卡片。11 .md 打包至 [.temp/ima_upload/](.temp/ima_upload/)。**PROGRESS.md 精简**(429→~120 行) |
| **2026-05-06** | step-03 | **林奇护栏 5/5 + PEG 曲线 + M6 林奇 Tab 实质交付** — [data/turnover.duckdb](data/) sina BS+IS 派生 12 家 2820 行(存货/应收/总资产周转);林奇护栏由 1/5 → 5/5 真数据;[peg_curve.py](.tools/dashboard/peg_curve.py) 理杏仁口径 PEG 曲线 + 估值 sub-tab expander;[tabs/lynch_analysis.py](.tools/dashboard/tabs/lynch_analysis.py) 2567 行 5 sub-tab 挂载 [app.py:363](.tools/dashboard/app.py#L363);ETF 行业对标 35 ETF×484 行独立 etf.duckdb |
| 2026-05-05 第二轮 | M5+P3 | **M5 D5 收尾(9/9)+ P3 部分解锁** — header_thermometer 抽 `card_html()` + tabs/claude.py 4 列卡片;[fetch_bank_metrics.py](.tools/db/fetch_bank_metrics.py) sina BS+IS 派生 4 银行指标;[piotroski_bank.yaml v2](.tools/rules/piotroski_bank.yaml) 代理规则;招行 5y F-Score 5-7 区间(2025=6/9 ⭐⭐) |
| 2026-05-05 | dashboard | **Dashboard M0-M5 全部落地 + M6 启动** — M0(导航栏)/ M2(公司筛选)/ M3(单公司 Top3+6 子 Tab)/ M4(决策中心 5/5 含 .bak+diff+自动决策日志)/ M5(Claude 终端 8/9);M6 林奇 Tab 计划文档就位 |
| 2026-05-04 | dash-03+04 | **个股全景 + 决策中心** — peer_radar 同行池雷达;decision_timeline 决策散点 + 股价底图;score_card master_matrix;holdings_view + decision_center + floating_widget(右下浮窗 3 快捷入口)+ render_monthly_pdf + send_monthly_email + cron 安装包;V8 SWS 风格 6 维雪花图 + V9 公司详情布局重构 |
| 2026-05-03 晚 | step-04 | **维度 4 P1+P2 完成** — F-Score 9/9 衍生改写零 API:[engine.py](.tools/score/engine.py) `yoy()` 升级 + piotroski.yaml 4 项规则衍生(f4=cfo_to_ni / f5=有息负债率 / f7=NI÷EPS / f9=营收增长)+ run_score 加行业自动切换;比亚迪 2020 / 五粮液 2023 / 恒瑞 2023 拿到 9/9 |
| 2026-05-03 中 | 多会话 | **MCP 挂载验证通过 + ttyd 转方案 B + 副线 P0 解除** — 4 工具冒烟测试通过(茅台 PE-TTM 9.4% 分位);.mcp.json 配置位置修复;Tab 4 ttyd 受 4 重阻塞(geo-block / Keychain ACL / 版本错配 / CLAUDECODE 嵌套)→ 转 VS Code 旁挂方案 B;13 家估值 10y 补抓(549,617 行)解锁 valuation_percentile;step-03 V4-V7(MCP 分位 + F-Score 列 + 时效徽章 + 模式切换) |
| 2026-05-03 早 | step-0 | **理杏仁抓取工具 4 处改造** — [lixinger_resolve_token.py](.tools/lixinger-archiver/lixinger_resolve_token.py) token bug 修;[generate_wide_valuation.py](.tools/lixinger-archiver/generate_wide_valuation.py) `--metrics-preset core3`;[batch_update_fs_modules.py](.tools/lixinger-archiver/batch_update_fs_modules.py) fs 4→1 合并;新增 [update_company_incremental.py](.tools/lixinger-archiver/update_company_incremental.py);美的首抓 5→2 次 API |
| 2026-05-02 | W1 启动 | **改版 v2.0 + 4 维度并行启动** — 切"瀑布式三阶段"→"4 维度 12 任务";step-01 维度 1 全栈交付(1.1 ingest + 1.2 validate + 1.3 AkShare cron + ingest 扩 8 表);step-02 维度 2 增强三件套(freshness/percentile/errors);step-03 维度 3 工程化 8 件套 + M1-M4 联动 |

详细技术细节(token 实测、阻塞踩坑路径、行业字典等)落在 [memory/](.claude/projects/-Users-gongyong-Desktop-Keyi-preson/memory/) 的对应记忆里。

---

## 🎯 周次时间表

| 周 | 计划 | 实际 |
| --- | --- | --- |
| W1 (5/3-5/9) | schema + ingest.py(原 W1-W5 共 5 周计划) | ✅ **单周全交付** + 维度 4 提前启动至 85% |
| ~~W2-W5~~ | — | ✅ W1 提前完成 |
| W6 (6/7-6/13) | Streamlit + 嵌入终端 | ✅ 100%(实质;Tab 4 嵌入转方案 B)+ Dashboard M0-M5+M6 |
| W7 (6/14-6/20) | portfolio.yaml | 🟢 4.1 v0 已交付,完整版待启动(数据齐) |
| W8 (6/21-6/27) | 评分引擎 | 🟢 提前 7 周(P1+P2 ✅,P3 等字典) |
| W9 (6/28-7/4) | 月度复盘模板 | 🟢 4.3 已 v2 验收 |

**累计提前**:维度 1+2 全栈 + 维度 3 100% + 维度 4 85% 全部在 W1 完成 → **节省 W2~W8 共 7 周容量**。

---

📧 [renmingyang@proton.me](mailto:renmingyang@proton.me)
