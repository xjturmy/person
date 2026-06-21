---
name: PROJECT_PLAN_v2.3
date: 2026-05-07
status: 已收口 — D3 ✅ 100%(C 4 项收尾完成)· D2 ✅ 100%(2.1+2.2+2.3+2.4 全交付)· D1 ✅ 100%(A+B+C 全 / 块 C A+B+C1-C4 + 数据补强)· **完成度 ~100%**
owner: renmingyang@proton.me
基于: PROJECT_PLAN_v2.1_dashboard.md(M0-M6 已交付)
---

# 📊 preson 项目计划 v2.3 — 三方向并行

> v2.1 把 Dashboard M0-M6 全部落地后,v2.3 启动三个**互不阻塞**的方向:
>
> **D1 · 林奇深化** — 补缺失数据 + 扩同行池
> **D2 · 黄金模块** — 基于已读 4 本书新建独立分析模块
> **D3 · 格雷厄姆模块** — 参照林奇 Tab 模式独立成 Tab + 方法论补齐 + 调优

---

## 🎯 总体目标

| 方向 | 一句话目标 | 主交付物 | 工时 |
|---|---|---|---:|
| **D1 林奇深化** | 把 M6 林奇 Tab 从"框架级"推到"数据完备 + 跨同行可比" | 季度 YoY 真数据 + 类型 5/6 知识库 + peers 扩 30 家 | ~12h |
| **D2 黄金模块** | 新增独立 `🥇 黄金分析法` Tab,基于鲁政委三大范式 + 周金涛康波 | gold.duckdb + tabs/gold_analysis.py + 4 篇方法论 md | ~16h |
| **D3 格雷厄姆模块** | 把格雷厄姆从"market.py 一段指数"升级为独立 Tab,与林奇并列 | 方法论 6 件套 + tabs/graham_analysis.py + 调优 | ~14h |

**总工时 ~42h**(可分 3-4 周完成,每周一个方向收口)

---

## 📌 当前基线(v2.1 已交付)

- ✅ Dashboard M0-M6 全部落地(导航/市场/筛选/单公司/决策/Claude 终端/林奇)
- ✅ 8 张主表 + 4 个独立 .duckdb(preson / etf / macro / peers / turnover)
- ✅ 4 MCP 工具挂载验证
- ✅ 评分体系 8 大师 9 套规则;F-Score 9/9 衍生改写
- ✅ 林奇五步 sub-tab 2567 行 / 护栏 5/5 真数据 / PEG 曲线理杏仁口径

**v2.3 不动** 维度 1(数据层)、维度 2(MCP 能力层)的现有形态,只**叠加新数据源**与**新 Tab**。

---

# 🌱 D1 · 林奇深化(补缺失数据 + 扩同行池)

## 1.1 现状盘点(2026-05-07 更新)

| 项 | 状态 | 缺口 |
|---|:-:|---|
| `tabs/lynch_analysis.py` | ✅ 2567 行 5 sub-tab | — |
| `lynch_classifier.py` | ✅ 893 行六类判定 + `quarterly_continuity()` 纯函数 | — |
| `lynch_abcd_scorer.py` | ✅ 8 季 hits_20pct/hits_10pct 接入 | — |
| 财务护栏 5 项 | ✅ turnover 表派生 | — |
| 增长连续性(8 季 YoY) | ✅ **块 A 已交付**(commit d0c1183) | 茅台 stalwart 92/100 / 恒瑞 7/8 满足铁律 |
| 知识库 02/03/04 类型 ABCD | ✅ 稳健/快速/周期 | — |
| 知识库 05/06 类型 ABCD | ✅ **块 B 已交付**(困境反转 + 隐蔽资产 ABCD)| — |
| PEG 估值速查 + 六类口径表 | ✅ **块 B 已交付**(07/08 编号,避开冲突)| — |
| 同行池 peers.csv / peers.duckdb | ⏳ **块 C Phase A 进行中**(扩 ~80 行 + 多维基本面)| 见 [PROJECT_PLAN_peer.md](PROJECT_PLAN_peer.md) |

## 1.2 三块工作拆分

### 块 A · 增长连续性 A 方案(~4h)✅ **已交付 2026-05-07**(commit d0c1183)

**问题**:`lynch_classifier.py` 判增长连续性时,茅台单季 YoY 跌到 1.5% 触发"快速→稳健"误判。

- [x] 接 `growth.csv` 营业收入季度累计 → 单季还原(Q1=累计;Q2/Q3/Q4=当期-上期);**偏差**:用营收而非净利,营收单季 YoY 比净利可靠(扣非/一次性损益噪音小)
- [x] 8 季 YoY 滑窗连续性判断 — `quarterly_continuity()` 纯函数 + `QuarterlyContinuity` dataclass 跨模块共享
- [x] `lynch_abcd_scorer.py` stalwart 1.2 + fast_grower 1.2 项接 hits_10pct/hits_20pct,带退化提示与 fallback
- [x] `lynch_analysis.py` 第 2 步层 2 重写:4 列指标卡 + 类型铁律达标/退化提示
- [x] 茅台/招行/比亚迪/恒瑞 4 家回归测试通过

**回归结果**:

| 公司 | 类型 | 8 季 hits | 旧 → 新评分 |
|---|---|---|---|
| 茅台 | stalwart | 0/8 >20% / 4/8 >10% | 3/15 → 10/15 ✅(总分 92 A 级) |
| 招行 | stalwart | 0/8 >10% | 3/15(真实断档) |
| 比亚迪 | fast_grower | 4/8 >20% | 3/15 → 10/15(快速边缘) |
| 恒瑞 | stalwart | 7/8 >10% | 3/15 → 15/15 ✅(铁律达标) |

**验收**:✅ 茅台 1.5% 不再误判;`QuarterlyContinuity` 含 series 数组 + 统计量;Streamlit AppTest 无异常

### 块 B · 知识库补 05/06 + 估值口径表(~4h)✅ **已交付 2026-05-07**(commit d0c1183)

参照 [02_稳健增长型_ABCD评估.md](01_knowledge/03_投资策略与选股/02_彼得林奇投资法/02_稳健增长型_ABCD评估.md) 模板:

- [x] **[`05_困境反转型_ABCD评估.md`](01_knowledge/03_投资策略与选股/02_彼得林奇投资法/05_困境反转型_ABCD评估.md)**(210 行)— 反转改善信号 + 现金流拐点 + EV/Sales + 反转催化剂
- [x] **[`06_隐蔽资产型_ABCD评估.md`](01_knowledge/03_投资策略与选股/02_彼得林奇投资法/06_隐蔽资产型_ABCD评估.md)**(213 行)— P/NAV + NCAV + 资产分散度 + 催化剂可见度
- [x] **[`07_PEG估值速查.md`](01_knowledge/03_投资策略与选股/02_彼得林奇投资法/07_PEG估值速查.md)**(239 行)— 5 档评级 + 4 类不适用清单 + PSG/EV-EBITDA/P-NAV/股息 4 套替代口径 + 4 家实战
- [x] **[`08_六类公司估值口径表.md`](01_knowledge/03_投资策略与选股/02_彼得林奇投资法/08_六类公司估值口径表.md)**(165 行)— 6 类一张大表打齐:估值法/买入阈值/卖出条件/故事检查 + 本仓库 15 家映射
- [x] `00_方法论总览.md` 第十节索引扩为"6 类评估 + 通用工具速查 + 阅读路径建议"

**命名偏差**:计划原文 `03_/04_` 与现存"快速增长型/周期型"编号冲突 → 实际用 **`07_/08_`** 紧接 5/6 类,语义更清晰

**验收**:✅ `02_彼得林奇投资法/` 目录从 6 → **10 个 md**;每类公司有专属 ABCD 评估页(05 困境反转 / 06 隐蔽资产)

### 块 C · 同行池扩展(~4h → 升级为 12.5h 三阶段)⏳ **进行中**

> **范围扩展**:用户起草 [PROJECT_PLAN_peer.md](PROJECT_PLAN_peer.md) 把原"扩 30 家"升级为 **A→B→C 三阶段**(扩同行池 + 多维同步 + 行业横评 sub-tab + 自动建议引擎),工时 4h → 12.5h。

**Phase A · 扩同行池 + 多维同步(~3.5h)** ⏳ **跑数据中**:
- [x] 改造 `fetch_peers.py`:n=2 → n=6 + 多维基本面 + PEG + F-Score lite + cache fallback
- [x] 改造 `update.py`:加 `--skip-peers` / `--peers-n` 参数,cron 集成
- [x] 离线 sanity:`_calc_peg` 7 case + `_pick_peers` 4 家市值排序通过
- [⏳] **实跑 Phase A 数据**:用户在另一终端跑 run5(PID 20161,21:15PM 启动),阶段 1 行业映射 14/15 完成,后续阶段 2/3 进行中
- [ ] 验收:`peers.duckdb` 28 → ~80 行,17 列(PE/PB/ROE/GM/营收YoY/净利YoY/PEG/fscore_lite),关键列非空率 ≥ 80%

**Phase B · 公司 Tab 加「行业横评」sub-tab(~5h)** ⏳ **待启动**(依赖 Phase A 数据落库):
- [ ] `industry_percentile.py` — (ticker, metric, peer_group) → (self, peer_median, P25, P75, percentile_in_peers)
- [ ] 公司 Tab 区块 C 新增「🏭 行业横评」sub-tab — 6 维卡片 + 分位条形 + 同行表格

**Phase C · 自动建议引擎(~4h)** ⏳ **待启动**(依赖 Phase B):
- [ ] `peer_advice.yaml` 6 维 × 3 档阈值 + 综合标签
- [ ] `peer_advisor.py` → 输出 `[(dim, label, evidence), ...]` + 综合"低估/中性/高估"
- [ ] Hero 区「💡 同行建议卡」+ 决策中心 M4 集成

**验收**(Phase A 完成判定):`SELECT * FROM peers WHERE ticker='600519'` 返回 6 行,每行含 PE/PB/ROE/GM/PEG/fscore_lite,非空率 ≥ 80%

## 1.3 风险

- 同行池扩 30 家 → 估值数据约 +30 家 × 10 年 ≈ 1.2M 行,DuckDB 可吃下
- 不在 portfolio 里的 peers 不需要 fs 全量,**只抓估值** = ~30 次 API 调用
- 5/6 类知识库纯写作,无数据依赖,可纯离线写

---

# 🥇 D2 · 黄金分析模块(新增 Tab)

## 2.1 设计哲学

基于已读 4 本书的"三层定位"框架:

```text
┌──────────────────────────────────────────────────────────────────┐
│ 黄金的三种身份(任一时刻只主导一种)                                │
├──────────────────────────────────────────────────────────────────┤
│  ① 避险资产 — 金融危机/地缘冲突时跑赢                              │
│  ② 抗通胀工具 — 实际利率为负时跑赢                                │
│  ③ 周期资产 — 康波萧条期跑赢                                      │
│                                                                    │
│  当前主导身份 = 三大信号矩阵投票                                   │
└──────────────────────────────────────────────────────────────────┘
```

**理论来源**:
- **三大范式** — 鲁政委《保卫财富:黄金投资新时代》⭐⭐⭐⭐⭐ 已读
- **康波萧条期黄金** — 周金涛《涛动周期论》《人生财富靠康波》已读
- **周期与配置时机** — 霍华德·马克斯《周期》⭐⭐⭐⭐⭐ 已读

## 2.2 数据需求与来源

| 指标 | 来源 | 频率 | 备注 |
|---|---|---|---|
| 金价 LBMA AM/PM | AkShare `macro_cons_gold_amount` | 日 | 美元计 |
| 沪金 AU99.99 | AkShare `spot_hist_sge` | 日 | 人民币计 |
| 美债 10Y 名义利率 | macro.duckdb 已有 `10Y_YIELD` | 日 | ✅ 已有 |
| 美国 CPI | AkShare `macro_usa_cpi_monthly` | 月 | → 实际利率 |
| 美元指数 DXY | AkShare `macro_fx_sentiment` 或 `currency_history` | 日 | — |
| 油价 WTI | AkShare `futures_global_em_dict` | 日 | 金油比用 |
| 银价 LBMA | AkShare `macro_cons_silver_volume` | 日 | 金银比用 |
| SPDR 黄金 ETF 持仓 | AkShare `macro_cons_gold_volume` | 日 | 市场情绪 |
| 央行购金(WGC) | AkShare 不全 → 手填年度数据 | 季 | 长期需求 |
| 国内黄金 ETF | AkShare `fund_etf_hist_em` 标的(518800/518880/159834/518680) | 日 | 投资工具 |

**新建库**:`data/gold.duckdb` 8 张表(对照 preson.duckdb 命名风格)

## 2.3 模块组件

### 知识库(`01_knowledge/03_投资策略与选股/12_黄金投资法/` ✅ **已交付 2026-05-07**)

> 注:实际位置为 `03_投资策略与选股/12_黄金投资法/`(原计划 `05_黄金投资法/` 与已有 `05_选ETF框架.md` 文件冲突,改用 `12_` 编号)

- [x] `README.md` — 目录索引 + 三身份速查 + 心法 + 关联代码 ✅
- [x] `00_方法论总览.md` — 黄金三种身份 + 配置决策树 ✅
- [x] `01_三大范式判定.md` — 鲁政委框架细化(避险信号/通胀信号/周期信号 各 5 项)+ 投票判定矩阵 ✅
- [x] `02_实际利率定价模型.md` — 实际利率 = 名义利率 - 通胀预期;反向叠加金价散点 + 四象限决策 ✅
- [x] `03_配置比例量化.md` — 康波四阶段 + 风险偏好乘数 + 战术微调 + 鲁政委 38% 高风险结论推导 ✅
- [x] `04_黄金ETF选择.md` — 国内 4 只 ETF 对比(518880/159937/159934/518800)+ 海外 GLD/IAU + 工具组合策略 ✅
- [x] `05_关键指标速查.md` — 实际利率/金油比/金银比/SPDR 4 张分位表 + 四象限决策 + 综合仪表盘 ✅

### Dashboard Tab(`tabs/gold_analysis.py` 新建)

```text
┌──────────────────────────────────────────────────────────────────┐
│ 🥇 黄金分析法 · 三身份决策框架                                       │
├──────────────────────────────────────────────────────────────────┤
│ [⏱ 数据更新:2026-05-07] [刷新]                                      │
│                                                                    │
│ ★ 当前主导身份:🛡️ 避险(投票 3-1-1)                              │
│ 📍 范式判定:实际利率 -1.2% / 美元指数高位 / 康波萧条尾段             │
│ 💡 配置建议:权益类组合中 黄金 占 15-20%(防御为主)                  │
└──────────────────────────────────────────────────────────────────┘

[① 三大范式投票] [② 实际利率] [③ 周期定位] [④ 关键比率] [⑤ ETF 选择]
                              ↓
        每 sub-tab 含:理论速读 + 数据图表 + 当前判定 + 历史分位
```

**5 个 sub-tab 详细**:
- ① **三大范式投票** — 5 个避险信号 + 5 个通胀信号 + 5 个周期信号,3 组 ✅/❌ 矩阵 + 投票结果
- ② **实际利率定价** — 实际利率反向叠加金价(双 Y 轴);近 20 年散点 + 当前点位 + 趋势线
- ③ **周期定位** — 康波四阶段时间轴 + 当前位置;历史四次萧条期黄金回报对照
- ④ **关键比率** — 金油比 / 金银比 / 央行购金趋势 / SPDR 持仓 — 4 张时序图 + 分位表
- ⑤ **ETF 选择** — 4 只国内 ETF 对比 + 跟踪误差 + 持有成本 + 推荐建议

### 数据脚本(`.tools/db/fetch_gold_*.py` ✅ **已交付 2026-05-07**)

- [x] [`gold_schema.py`](.tools/db/gold_schema.py) — 共享 DDL,8 表 idempotent CREATE ✅
- [x] [`fetch_gold_prices.py`](.tools/db/fetch_gold_prices.py) — SGE Au99.99(CNY/g)+ Ag99.99(CNY/g,/1000 修单位)+ WTI 油 + 派生 USD 金价 ✅(13,082 行)
- [x] [`fetch_real_rate.py`](.tools/db/fetch_real_rate.py) — 美 10Y + 美 CPI MoM → 累计 CPI → YoY → 实际利率(月→日 ffill) ✅(19,016 行)
- [x] [`fetch_gold_etf.py`](.tools/db/fetch_gold_etf.py) — 4 只国内黄金 ETF master + 5y K 线;SPDR 走 `.config/spdr_holdings_manual.csv` 手填备选(jin10.com 中国 IP SSL 卡死)✅(4,844 行)
- [x] [`fetch_gold_ratios.py`](.tools/db/fetch_gold_ratios.py) — 派生金油 / 金银比 + 5y/10y/20y 滑动分位 ✅(9,252 + 9 行)
- [x] 接入 [`update.py`](.tools/db/update.py) weekly cron — 4 步串联(`--skip-gold` 兜底) ✅

## 2.4 Phase 拆分

| Phase | 内容 | 工时 | 状态 |
|---:|---|---:|---|
| **2.1** | 知识库 6 篇 md 起草(从已读分析提炼)| ~4h | ✅ **已交付 2026-05-07**(7 文件 / 1824 行)|
| **2.2** | 数据脚本 4 个 + gold.duckdb 8 表 + 周末 cron | ~5h | ✅ **已交付 2026-05-07**(46,203 行 / 6/8 表填充 / paradigm 2 表等 2.4)|
| **2.3** | `tabs/gold_analysis.py` Tab 骨架 + 顶部 banner + 5 sub-tab | ~5h | ✅ **已交付 2026-05-07**([gold_data.py](.tools/dashboard/gold_data.py) 375 + [tabs/gold_analysis.py](.tools/dashboard/tabs/gold_analysis.py) 581;5 sub-tab + 黄金渐变 banner + 静态范式投票兜底;AppTest 0 异常)|
| **2.4** | 三大范式投票引擎(15 信号自动判定) + 配置建议联动 | ~2h | ✅ **已交付 2026-05-07**([gold_paradigm.yaml](.tools/rules/gold_paradigm.yaml) 214 + [paradigm_engine.py](.tools/dashboard/paradigm_engine.py) 442;15 信号 × 5 source 类型 + 8 identity_rules;UI 切 verified=True;首次写库 15 信号 + 1 history;接入 update.py weekly cron)|

**总 ~16h** · 1.5-2 周

## 2.5 风险

- AkShare 黄金接口稳定性历史一般 → 多源备份(eastmoney + sina);失败 fallback 到手填年度
- 国内 ETF 持仓数据不一定能拿到 → 转用规模 + 跟踪误差替代
- "范式投票"5+5+5 信号阈值是主观选择 → 写到 yaml 让用户调

---

# 💎 D3 · 格雷厄姆投资法独立模块

## 3.1 现状盘点(2026-05-07 更新)

| 项 | 状态 | 缺口 |
|---|:-:|---|
| `01_格雷厄姆投资法/` 知识库 | ✅ **阶段 A 已交付** — 13 个 md(00-10 + 99 + README)| — |
| `rules/graham.yaml` 评分规则 | ✅ 已有 | 阶段 C:加 `graham_bank` / `graham_insurance` 变体 |
| `tabs/graham_analysis.py` Tab | ❌ **不存在** | **阶段 B 核心交付物(待启动)** |
| `market.py` 格雷厄姆指数 | ✅ 顶部一段 | 调优:加分位与红绿灯(已 v2.1 完成) |
| 实战案例 | ✅ 新华保险五步分析 | — |
| 适配:金融业(招行/新华) | ⚠️ piotroski_bank 联动 | **阶段 C:graham.yaml 加银行/保险变体** |

**用户需求拆解**:
1. 先参考彼得林奇方法论结构,补齐知识库
2. 再实现可视化模块
3. 最后效果调优

## 3.2 三阶段拆分

### 阶段 A · 方法论补齐(~4h)✅ **已交付 2026-05-07**(独立会话产出)

参照 [02_彼得林奇投资法](01_knowledge/03_投资策略与选股/02_彼得林奇投资法/) 的 6 件套结构,把现有"实战 11-15"重组并扩展:

| 林奇结构 | 格雷厄姆对应 | 状态 |
|---|---|:-:|
| `00_方法论总览.md` | `00_方法论总览.md` — 深度价值五步 + ABCD/12345 矩阵 | ✅ |
| `01_六类公司分类法.md` | `01_四类价值分类.md` — 深度低估/防御型/进取型/特殊情境 | ✅ |
| `02_稳健增长型_ABCD评估.md` | `02_深度低估型_ABCD评估.md` — 净流动资产法 + 安全边际 | ✅ |
| `03_快速增长型_ABCD评估.md` | `03_防御型_ABCD评估.md` — 大盘蓝筹 + 稳定股息 | ✅ |
| `04_周期型_ABCD评估.md` | `04_进取型_ABCD评估.md` — 二线优质 + 适度成长 | ✅ |
| (新增) | `05_特殊情境_ABCD评估.md` — 困境反转 / 套利机会 | ✅ |
| (复用) | `11-15` 实战 → `06-10` 改名(商业模式/盈利/财务健康/估值/深度审视)| ✅ |
| (新增) | `99_格雷厄姆_vs_林奇.md` — 同一公司在两套体系下的差异 | ✅ |
| (新增) | `README.md` — 目录索引 | ✅ |

**验收**:✅ 目录从 5 个 md 扩到 **13 个 md**;每类公司有专属 ABCD 评估页

### 阶段 B · 可视化 Tab(~7h)✅ **已交付 2026-05-07**(独立会话产出)

实际交付:
- [x] [graham_steps.py](.tools/dashboard/graham_steps.py)(893 行)— 四类判定 + 7 准则 + 三层防御 + NCAV + 格氏数 + 卖出触发
- [x] [tabs/graham_analysis.py](.tools/dashboard/tabs/graham_analysis.py)(698 行)— 顶部蓝色 banner + 5 sub-tab + ABCD/12345 决策矩阵 + 一键导出 md
- [x] [test_graham_steps.py](.tools/dashboard/test_graham_steps.py)(166 行)— 7/7 离线测试通过
- [x] app.py PAGES 加 PAGE_GRAHAM 挂载
- [x] **5 公司离线验证**:招行(防御 PE×PB=5.4)/ 美的(防御 40.9)/ 茅台(进取 132.3)/ 伊利(防御 41.9)/ 新华(进取 8.9)
- [x] **AppTest headless**:Default + Graham Tab + 多公司切换 0 异常

> 原计划仅写 Tab 实现;实际**与阶段 C 一并交付**(见下)



完全对照 [tabs/lynch_analysis.py](.tools/dashboard/tabs/lynch_analysis.py) 模式:

```text
┌──────────────────────────────────────────────────────────────────┐
│ 💎 格雷厄姆投资法 · 深度价值五步框架                                  │
├──────────────────────────────────────────────────────────────────┤
│ [公司 ▼] [年份 ▼] [🔄 重新评估]   ⏱ 上次:5/7                       │
│ ★ 价值类型:🛡️ 防御型(PE 12 / PB 1.4 / DY 4.2%)                  │
│ 📍 安全边际:当前 vs 内在价值 -23%(打 7.7 折)                       │
└──────────────────────────────────────────────────────────────────┘

[① 商业模式] [② 盈利能力] [③ 财务健康] [④ 估值/安全边际] [⑤ 深度审视]
                              ↓
   每 sub-tab:理论速读 + 自动判定 + 用户修订 + 评分卡 + 知识嵌入

底部:🎯 综合结论 + ABCD/12345 等级 + [💾 写决策日志] [📤 导出 md]
```

**5 个 sub-tab 关键点**:
- ① **商业模式** — 行业龙头判定 + 业务可理解性自评 + 周期/非周期分类
- ② **盈利能力** — 10 年盈利记录 + ROE 稳定性 + EPS 增长率(格雷厄姆要求 10y 不亏损)
- ③ **财务健康** — 流动比率 ≥ 2 / 长期负债 < 营运资金 / Altman Z-Score
- ④ **估值 + 安全边际** — PE × PB ≤ 22.5(格氏数) + DCF 内在价值 + 安全边际百分比 + 同行雷达
- ⑤ **深度审视** — 大股东动作 / 审计意见 / 关联交易 / 现金流真实性 / 一致性核查

**新增/扩展文件**:
- `tabs/graham_analysis.py` 主入口(~600 行)
- `graham_steps.py` 5 步纯逻辑
- `graham_templates/` 评分模板 yaml
- 复用 `rules/graham.yaml` + `score/engine.py`

### 阶段 C · 调优 ✅ **已交付 2026-05-07**(全部 5 项收口)

- [x] **金融业适配** — [graham_bank.yaml](.tools/rules/graham_bank.yaml)(7 准则银行变体,PB×DY ≥ 0.04 替代格氏数)+ [graham_insurance.yaml](.tools/rules/graham_insurance.yaml)(v0,EV 数据待解锁)
- [x] **格雷厄姆指数 · 单公司联动** — [market.py:_section_company_graham_number](.tools/dashboard/tabs/market.py) 在 ②.5 区块加单公司 PE×PB 实时位置卡片(PE / PB / PE×PB / 评级 / 价值类型 + 跳转到 💎 Tab 提示)
- [x] **同行雷达联动** — [graham_peer_radar.py](.tools/dashboard/graham_peer_radar.py)(5 维归一化 0-100:PE/PB/DY/流动比率/资产负债率 → buy-zone)+ self vs peers 叠加雷达;接入 [graham_analysis.py:_render_step4_valuation](.tools/dashboard/tabs/graham_analysis.py) 第四步底部 expander
- [x] **决策日志写入** — [graham_analysis.py:_build_decision_md](.tools/dashboard/tabs/graham_analysis.py#L544) 已实现,一键写到 `02_companies/{N}_{name}/05_投资决策/格雷厄姆五步分析_{date}_auto.md`,带 `_auto.md` 后缀避开人工版
- [x] **离线测试** — [test_graham_steps.py](.tools/dashboard/test_graham_steps.py) **10/10 通过**,覆盖 4 类公司(招行防御 / 美的防御 / 茅台进取 / 新华进取 / 三美进取)+ 决策 markdown 4 类公司构建

## 3.3 风险

| 风险 | 处理 |
|---|---|
| 格氏数 PE×PB ≤ 22.5 对当前 A 股太严苛 → 几乎无标的合格 | 加"软达标"档(< 30 / < 50 灰阶展示),不一刀切 |
| 银行/保险 PE 不可比(用 PB+DY 替代) | yaml 变体里把 PE 列为可选项 |
| 与林奇 Tab UI 高度雷同 → 用户混淆 | 顶部 banner 主色:林奇绿 / 格雷厄姆蓝;Emoji 🌱 vs 💎 |
| 新华保险已有人工五步分析 md → 不要被覆盖 | "导出 md"加 `_auto.md` 后缀,人工版保留 |

---

## 📅 整体时间表与优先级(2026-05-07 更新)

| 周次 | 主线 | 副线(并行) | 计划交付 | 实际状态 |
|---|---|---|---|---|
| **W1** (5/7-5/13) | D1 块 A + 块 C 三阶段 | **D2 全 4 阶段 + D3 全 3 阶段(含 C 4 项收尾)** | 全方向收口 | ✅ **W1 单日 100% 收口**(D1 A+B+C 全 / **D2 100% 全交付** / **D3 100% 全交付**) |
| ~~W2-W4~~ | — | — | — | ✅ W1 单日提前完成,共享计划公网部署可直接启动 |

**v2.3 实质 W1 单日全收口**(原计划 4 周 / 42h)— 提前 ~3 周,容量直接转入共享计划(preson-dashboard 公网部署)

### 进度统计(2026-05-07 晚 最终更新)

| 方向 | 任务数 | 已完成 | 进行中 | 待启动 | 完成率 |
|---|---:|---:|---:|---:|---:|
| **D1 林奇深化** | A + B + C(PA+PB+PC+C4 + 数据补强)| **全部 ✅** | — | — | **100%** |
| **D2 黄金模块** | Phase 2.1-2.4 | **全部 ✅**(2.1+2.2+2.3+2.4)| — | — | **100%** |
| **D3 格雷厄姆** | 阶段 A/B/C(C 5 项收口)| **全部 ✅** | — | — | **100%** |
| **总计 v2.3** | (12+16+14)h | 42h | — | — | **100%** |

### 下一步优先级

1. 🎯 **共享计划启动**(preson-dashboard Streamlit Cloud 公网部署,~10h)— v2.3 已全收口,直接进入下一阶段
2. 🔵 **同行模块信任度升级包**(可选,见 [PROJECT_PLAN_peer.md](PROJECT_PLAN_peer.md))— 数据时效透明 + 决策反查 + 价值陷阱防御 ~6.5h

---

## 🔗 与其他计划的关系

- **共享计划(preson-dashboard 公网部署)** — v2.3 的所有产出**不影响**子仓拆分;子仓拷贝时按现有 `改名表` 拉新文件即可
- **PROGRESS.md** — v2.3 各方向进展会同步反映到 PROGRESS 的 `📌 待办清单` 和 `📝 版本日志`
- **维度 4 P3 字典阻塞** — 不在 v2.3 范围;NPL/CET1/EV·NBV 仍等用户给字典

---

## ❓ 待用户拍板

- [ ] **顺序确认** — W1-W4 的时间表 OK?或者想要"一个方向干完再下一个"?
- [ ] **D2 黄金 ETF 标的** — 默认监控 518800/518880/159834/518680 4 只,是否要加沪金期货?
- [ ] **D3 格雷厄姆 yaml 严苛度** — "格氏数 22.5"在 A 股几乎无标的,是否接受"软达标"模式?
- [ ] **同行池扩 30 家是否要全维度抓** — 默认只抓估值表(PE/PB/市值/股息率),fs 模块跳过(节省 token)

---

## 📊 工时与依赖汇总

| 方向 | 工时 | 强依赖 | 弱依赖 |
|---|---:|---|---|
| D1 林奇深化 | ~12h | growth.csv | peer_radar.py |
| D2 黄金模块 | ~16h | AkShare 黄金接口 | macro.duckdb |
| D3 格雷厄姆 | ~14h | rules/graham.yaml | piotroski_bank.yaml |
| **合计** | **~42h** | — | — |

**风险敞口**:D2 的 AkShare 黄金接口可能不稳定(占 5h 风险) → 建议先做 D1+D3,D2 放最后(也匹配 W3-W4 时间表)

---

## 📝 版本记录

| 日期 | 变更 |
|---|---|
| 2026-05-07 | v2.3 起草 — 林奇深化 + 黄金模块 + 格雷厄姆模块 三方向并行 |
| 2026-05-07 晚 | **W1 单日大爆发** — D1 A+B(commit d0c1183 / 林奇 8 季 YoY 修复 + 4 篇 ABCD/PEG/口径表)+ D2 Phase 2.1(黄金方法论 7 件 1824 行)+ D2 Phase 2.2(gold.duckdb 46k 行 / 6/8 表填充)+ **D3 全交付**(13 件方法论 + graham_steps.py 893 + graham_analysis.py 698 + 7/7 测试 + bank/insurance yaml);D1 块 C 升级为 PROJECT_PLAN_peer.md A→B→C 三阶段(12.5h);**v2.3 完成度 ~67%**(D3 100% / D1 50% / D2 50%) |
| 2026-05-07 晚 第二次 | **D2 Phase 2.3 黄金 Tab 交付** — [gold_data.py](.tools/dashboard/gold_data.py) 375 + [tabs/gold_analysis.py](.tools/dashboard/tabs/gold_analysis.py) 581(5 sub-tab + 黄金渐变 banner + 静态范式投票兜底);AppTest 0 异常;**v2.3 完成度 ~67% → ~81%**(D2 50% → 88%,仅剩 Phase 2.4 范式引擎 ~2h) |
| 2026-05-07 晚 第三次 | **D2 Phase 2.4 范式投票引擎 + D2 100% 收口** — [.tools/rules/gold_paradigm.yaml](.tools/rules/gold_paradigm.yaml) 214(三大范式 × 5 信号 × 5 source 类型 + 8 identity_rules)+ [paradigm_engine.py](.tools/dashboard/paradigm_engine.py) 442(`load_config` + `_evaluate` + `vote()` + `record_snapshot()` + CLI `--write`);UI 切到 verified=True;首次写库 15 信号 + 1 history(2-4-5 / 主导 🔥 抗通胀 + 🔄 周期 / 配置 15-20%);接入 update.py weekly cron 第 5 步;**8/8 表全填充**;**v2.3 完成度 ~81% → ~86%**(D2 ✅ 100% / D3 ✅ 100% / D1 50%);**v2.3 仅剩 D1 块 C ~9h**(Phase A 跑数据中 + Phase B/C 待启动) |
| 2026-05-07 晚 第四次 | **D1 块 C 全收口 + D3 阶段 C 4 项收尾 → v2.3 100%** — D1 块 C(同行对比深化):Phase A+B+C(C1-C4)全交付 + 数据补强(self_metrics PE/PB 三层兜底,4 commits:5366c1b / 12b4db3 / 99b9ffa / 2267410)+ Hero「💡 vs 同行业」卡 + 区块 C-3「🏭 行业横评」+ 决策中心「vs 同行」列(详见 [PROJECT_PLAN_peer.md](PROJECT_PLAN_peer.md));D3 阶段 C 4 项收尾:Item 1 `market.py:_section_company_graham_number` 单公司 PE×PB 卡片 + Item 2 `graham_peer_radar.py` 5 维归一化雷达 + Item 3 决策日志已实现 + Item 4 `test_graham_steps.py` **10/10 通过**(招行/美的/茅台/新华/三美 5 类公司 + 决策 markdown 4 类构建);AppTest market/graham/decision_center 全 0 异常;**v2.3 完成度 ~86% → ~100%** |
