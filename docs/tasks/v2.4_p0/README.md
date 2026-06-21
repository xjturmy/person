---
name: v2.4 P0+P1 平行任务包
date: 2026-05-08
owner: renmingyang@proton.me
基于: PROJECT_PLAN_v2.4_候选.md
---

# v2.4 P0+P1 · 4 任务平行执行包

> 把 v2.4 Phase 0 + Phase 1 拆成 4 个独立窗口可并行的任务包,每个含交付物清单 + 边界 + 完成判定 + 启动 prompt。

---

## 📦 任务清单

| 文件 | 候选 | 优先级 | 工时 | 依赖 |
|---|---|:-:|:-:|---|
| [step-A_market_snapshot.md](step-A_market_snapshot.md) | ⑨ Phase 1 · L1 全市场快照 | P0 | ~6h | 独立 |
| [step-B_search_bar.md](step-B_search_bar.md) | ⑩ 全局搜索栏 | P0 | ~2-3h | 独立 |
| [step-C_industry_focus.md](step-C_industry_focus.md) | ⑪ 行业聚焦 + 自动选优 | P0 | ~6-8h | 弱依赖 A |
| [step-D_gold_overheat.md](step-D_gold_overheat.md) | ⑫ 黄金过热引擎 | P1 | ~5-6h | 独立(基于 v2.3 D2) |

**总工时**:~20-23h(4 窗口并行折算 ~6-8h 实墙时间)

---

## 🔗 依赖图

```
step-A · L1 全市场快照(独立) ─────┐
                                    ├──→ step-C 弱依赖 A 的 market_spot
step-B · 全局搜索栏(独立) ──────────┘    (C 可先做骨架,A 完成后接 L1)
step-D · 黄金过热引擎(独立)

A/B/D 完全独立,C 弱依赖 A
```

---

## 🚀 推荐分窗口启动顺序

| 窗口 | 任务 | 启动时机 | 备注 |
|:-:|---|---|---|
| 1 | step-A | 立刻 | 数据基础,先动一步;AkShare ~7-8min 慢抓但写完代码就放着跑 |
| 2 | step-B | 立刻 | 完全独立,~2-3h 最快出活,先看到效果 |
| 3 | step-C | 立刻 | 先做评分引擎骨架(用现有 peers.duckdb),A 完成后接 L1 |
| 4 | step-D | 立刻 | 完全独立,与 D2 模块紧耦合但不与 ABC 冲突 |

---

## 📋 各窗口启动咒语(复制粘贴即可)

### 窗口 1 · step-A(L1 全市场快照)

```
你在 /Users/gongyong/Desktop/Keyi/preson 项目空间。先读 CLAUDE.md + ../tasks/v2.4_p0/step-A_market_snapshot.md + PROJECT_PLAN_v2.4_候选.md(候选 ⑨ 节)。

任务:实施候选 ⑨ Phase 1 — L1 全市场快照层。按 step-A 交付物清单逐项完成。

不需要请示,做到全部交付完成 + PROGRESS.md 更新 + 一段冒烟测试结果。
```

### 窗口 2 · step-B(全局搜索栏)

```
你在 /Users/gongyong/Desktop/Keyi/preson 项目空间。读 CLAUDE.md + ../tasks/v2.4_p0/step-B_search_bar.md。

任务:候选 ⑩ — 全局搜索栏。按 step-B 交付物清单完成。

不依赖其他 step,独立闭环。完成后写冒烟结果到 PROGRESS.md。
```

### 窗口 3 · step-C(行业聚焦 + 自动选优)

```
你在 /Users/gongyong/Desktop/Keyi/preson 项目空间。读 CLAUDE.md + ../tasks/v2.4_p0/step-C_industry_focus.md + .tools/rules/lynch.yaml + .tools/rules/graham.yaml(熟悉评分体系)。

任务:候选 ⑪ — 行业聚焦 + 自动选优。按 step-C 交付物清单完成。

数据源初版用 peers.duckdb + companies.csv;L1 spot 留 hook(step-A 完成后接)。复用 v2.3 已有评分(8 大师 + lynch 分类器),不写新规则。完成后写冒烟到 PROGRESS.md。
```

### 窗口 4 · step-D(黄金过热引擎)

```
你在 /Users/gongyong/Desktop/Keyi/preson 项目空间。读 CLAUDE.md + ../tasks/v2.4_p0/step-D_gold_overheat.md + .tools/rules/gold_paradigm.yaml + .tools/dashboard/paradigm_engine.py(完全照搬模式)。

任务:候选 ⑫ — 黄金短期过热引擎。按 step-D 交付物清单完成。

完全照 paradigm_engine.py + gold_paradigm.yaml 模式做,不创新架构。完成后写冒烟到 PROGRESS.md。
```

---

## 🛑 撞车防护(各窗口文件边界)

| 窗口 | 写入路径白名单 |
|:-:|---|
| step-A | `data/market.duckdb` / `.tools/db/fetch_market_spot.py` / `.tools/db/schema/market_spot.sql` / `.tools/db/update.py`(增段) / `.tools/dashboard/tabs/market_scan.py`(新建) / `app.py`(加 PAGE) |
| step-B | `.tools/dashboard/components/search_bar.py`(新建) / `app.py`(sidebar 顶部一段) / `requirements.txt` |
| step-C | `.config/focus_industries.yaml` / `.tools/rules/industry_type_map.yaml` / `.tools/dashboard/industry_screener.py` / `.tools/dashboard/tabs/industry_focus.py` / `app.py`(加 PAGE) |
| step-D | `.tools/db/fetch_gold_etf.py`(扩列) / `.tools/db/fetch_gold_etf_share.py`(新建) / `.tools/rules/gold_overheat.yaml` / `.tools/dashboard/overheat_engine.py` / `.tools/dashboard/tabs/gold_analysis.py`(加 banner + sub-tab) / `.tools/db/update.py`(增段) |

⚠️ **共享文件**:`app.py` 和 `.tools/db/update.py` 三个 step 都要动。约定:
- A 加 PAGE_MARKET_SCAN + sidebar 一项
- B 改 sidebar 顶部插搜索栏
- C 加 PAGE_INDUSTRY_FOCUS + sidebar 一项
- D 不动 app.py,只动 update.py 加一段

如果 git pull 后撞了,合并冲突 manually 解决(都是 append-only 一段,易合并)。

---

## ✅ 全部完成后

汇合到主窗口跑:
```bash
cd /Users/gongyong/Desktop/Keyi/preson
source .venv/bin/activate
streamlit run app.py
```

验收:
- 顶部 sidebar 看到搜索栏(B)+ 全市场扫描入口(A)+ 行业聚焦入口(C)
- 黄金 Tab 顶部 banner 加了短期热度卡 + 第 6 sub-tab(D)
- 4 个 PROGRESS.md 章节都更新

然后我把 `PROJECT_PLAN_v2.4_候选.md` 落成正式 `PROJECT_PLAN_v2.4.md`,记忆里加 v2.4 Phase 0+1 完成节点。
