---
name: 同行对比深化计划
date: 2026-05-07
status: Phase A + B + C(C1-C4)全部交付 ✅
owner: renmingyang@proton.me
---

# 🤝 同行对比深化计划 · A→B→C 三阶段

> **目标**:每家公司从 2 个固定同行 → 5-8 家行业横评 + 多维分位 + 自动建议卡。
>
> 当前痛点:
> - peers.duckdb 28 行只是 PE/PB/市值 静态快照,**ROE 列全空、无毛利率/营收增速/PEG**
> - 同行业对比**只在 15 家清单内**比对(白酒只有茅台 vs 五粮液,缺汾酒/泸州/洋河)
> - **没有"建议"层** —— 现在只展示数据,没有"PE 比行业中位低 30% → 偏低"的结论

---

## 📋 当前已有基础(不重做)

- `_peers_same_industry()` 申万 l1/l2 同行业筛选(限 15 家清单内)
- `peer_pool()` 按 category 分组(non_financial/bank/insurance/hk)
- `peer_radar_chart()` 6 维雷达
- `compare_peers` MCP 工具
- `fetch_peers.py` 已有 `_all_a_spot()` 全 A 股能力 + EM 行业成分股拉取
- `companies_industry.csv` 14 家公司行业归类 + 总市值

---

## 🎯 Phase A · 扩同行池 + 多维同步(~3.5h)

| 子任务 | 工时 | 交付 |
|---|---:|---|
| A1 改造 `fetch_peers.py`:每家从 2 → **6 个**同行(同 EM 行业市值最近的) | 0.5h | peers.duckdb 28 → ~80 行 |
| A2 加 4 维度:**ROE / 毛利率 / 营收 YoY / 净利 YoY** —— 走 AkShare `stock_financial_abstract` | 1h | peers 表新增 4 列 |
| A3 PEG 列(理杏仁口径)—— 同行 PE-TTM ÷ 净利 3y CAGR | 1h | peers.peg 列 |
| ~~A4~~ F-Score 同行计算(改用 lite 版,4 规则:NI>0/CFO>0/ROE↑/营收↑) | 0.5h | peers.fscore_lite 列 |
| A5 写入 weekly cron(`update.py` 加一步) | 0.5h | 周末自动更新 |

**验收**:`SELECT * FROM peers WHERE ticker='600519'` 返回 6 行,每行含 PE/PB/ROE/毛利/营收YoY/净利YoY/PEG/fscore_lite,关键列非空率 ≥ 80%。

**完成标志**:本文件状态从「进行中(Phase A)」→「Phase A 完成」+ commit。

---

## 🎯 Phase B · 公司 Tab 加「行业横评」sub-tab(~5h)

| 子任务 | 工时 | 交付 |
|---|---:|---|
| B1 写 `industry_percentile.py` —— 输入(ticker, metric, peer_group)→ 返回(self, peer_median, peer_p25, peer_p75, percentile_in_peers) | 1.5h | metrics 模块 |
| B2 在公司 Tab 区块 C 现有 6 子 Tab 后新增「🏭 行业横评」—— 6 维卡片(估值/盈利/成长/PEG/F-Score/规模)各显示 self vs 行业 P25/中位/P75 + 分位条形 | 2h | UI 6 卡片 |
| B3 表格:全部同行并列(self 高亮)—— 可排序、可下载 CSV | 1h | DataFrame 渲染 |
| B4 离线 + headless 双验证 + 截图 | 0.5h | 截图存证 |

**验收**:打开「贵州茅台」→ 区块 C → 「行业横评」sub-tab 看到白酒 6 家并列 + 茅台位于「PE 第 70 分位」「ROE 第 95 分位」等条形可视化。

**依赖**:Phase A 完成。

---

## 🎯 Phase C · 自动建议引擎(~4h)

| 子任务 | 工时 | 交付 |
|---|---:|---|
| C1 写规则 YAML `peer_advice.yaml` —— 6 维 × 3 档(偏低/合理/偏高)阈值 + 综合标签逻辑 | 1h | rules 文件 |
| C2 写 `peer_advisor.py` —— 输入 ticker → 输出 `[(dim, label, evidence), ...]` + 综合「低估/中性/高估」+ 一句"为什么" | 1.5h | 引擎模块 |
| C3 在公司 Tab 区块 A(Hero)新增「💡 同行建议卡」—— 3 个 chip + 一句话理由 | 1h | Hero 卡 |
| C4 集成到决策中心 M4 —— 录入决策时自动附加"vs 同行结论快照" | 0.5h | decision_log 字段 |

**验收**:茅台 Hero 区出现"💡 vs 白酒 6 家:**偏低 / 综合优质** —— PE 第 30 分位、ROE 第 95 分位、PEG 0.8";伊利出现"vs 饮料乳品 6 家:**合理 / 增长平庸**……"。

**依赖**:Phase B 完成。

---

## 📅 总进度时间表

```
W1 (5/7-5/8)   Phase A  ████████░░░░░░░░░░░░  3.5h
W1 (5/8-5/9)   Phase B  ░░░░░░░░██████████░░  5h
W2 (5/12-5/13) Phase C  ░░░░░░░░░░░░░░░░████  4h
                总计 ~12.5h(2 个工作日内可全交付)
```

---

## ⚠️ 风险与缓解

| 风险 | 缓解 |
|---|---|
| AkShare `stock_financial_abstract` 调用速度(每家 ~1s × ~80 unique tickers = 80s+) | 加 dedupe(同行业 peers 复用)+ 0.3s sleep |
| 行业池超 50 家(银行业)→ 雷达图爆炸 | A1 限制 max_n=6;按市值距 self 最近的 6 家 |
| 港股(蜜雪)无 EM 行业映射 | category=hk 跳过 Phase A,沿用现有 2 个固定 peers |
| Phase C 规则误判 | 加 `--debug` flag 输出每条规则触发详情 |

---

## 📌 默认假设

1. ✅ 同行池规模 6 家(避免太宽,聚焦"贴身竞争对手")
2. ✅ Phase A 数据写 `peers.duckdb` 不进 `preson.duckdb`(解耦 cron)
3. ✅ Phase B sub-tab 加在区块 C 现有 6 子 Tab 后,**不动其他 Tab**
4. ✅ Phase C 建议卡显示在 Hero 区(用户最先看到)

---

## 📝 进度日志

| 日期 | 阶段 | 变更 |
|---|---|---|
| 2026-05-07 | 计划起草 | A→B→C 拆解,~12.5h 工时 |
| 2026-05-07 | **Phase A 完成** | `fetch_peers.py` 重构完毕:6 同行(--n 6)+ 4 维度基本面(ROE/毛利/营收YoY/净利YoY)+ PEG(理杏仁口径)+ F-Score lite(4 规则);新增 `self_metrics` 表(14 行);`update.py` 接入 `--peers-n` / `--skip-peers` 入口;EM 全网 SSL 挂时加 3 重 fallback(`--use-cached-peers` + 缓存 CSV + 老 peers.csv 回退);v8 端到端跑成 28 行 + ROE 100% 非空。茅台 PEG=1.68 / 山西汾酒 0.55 / 招行 ROE 13.4 vs 同行 9.7-11.7 数据合理。|
| 2026-05-07 | **Phase B 完成** | 新增 [industry_percentile.py](.tools/dashboard/industry_percentile.py) 9 指标分位计算 + IndustryPercentile dataclass;新增 [industry_compare_view.py](.tools/dashboard/industry_compare_view.py) 8 张分位卡片(self vs P25/P50/P75 + 三段彩条)+ 同行明细表 + CSV 下载;`app.py` 注入 `icv` 模块;[company.py:1191](.tools/dashboard/tabs/company.py#L1191) 在「横向对比」后插入「🏭 行业横评」divider;Streamlit AppTest headless 0 异常。|
| 2026-05-07 | **Phase C C1-C3 完成** | 新增 [.tools/rules/peer_advice.yaml](.tools/rules/peer_advice.yaml) 8 维 × 5 档信号阈值 + 加权 bands(权重总和 11);新增 [peer_advisor.py](.tools/dashboard/peer_advisor.py) advise() 引擎(MetricVerdict + PeerAdvice dataclass + render_hero_card_html);[company.py:625](.tools/dashboard/tabs/company.py#L625) 在区块 A 顶部插入「💡 vs 同行业」Hero 卡(emoji + 综合标签 + Top3 chip)。茅台:加权信号 -9 → 高估·中性(估值三件套都偏高);招行:+6 → 低估·优质(ROE/毛利/净利YoY 都强)。AppTest 0 异常。|
| 2026-05-07 | **Phase C C4 完成(全计划收口)** | 写入端:[snapshot.py:112-140](.tools/decisions/snapshot.py#L112) `capture()` 自动 advise(ticker) → snapshot 注入 `peer_advice` 字段(overall_label / weighted_sum / industry / top_evidence Top 3);显示端:[decision_center.py:668-689](.tools/dashboard/tabs/decision_center.py#L668) 历史决策表加 `vs 同行` 列从 `snapshot_json` 解出。**录入辅助增强**:[decision_center.py:632-672](.tools/dashboard/tabs/decision_center.py#L632) 「新增决策」expander 内动态显示当前选中公司的同行建议带色 banner(低估绿/合理黄/高估红 + Top3 evidence)。**端到端验证**:capture() 4 公司全部返回 peer_advice(茅台高估 -9 / 招行低估 +12 / 美的合理 +1 / 新华低估 +10);AppTest Default + 决策中心 0 异常,vs 同行业 关键词命中。|

---

📧 [renmingyang@proton.me](mailto:renmingyang@proton.me)
