---
name: PROJECT_PLAN_v2.6
version: v2.6
date: 2026-05-10
status: 已定型(扩展版 — 康波 ETF 配置 + 三大师 UI 集成)
owner: renmingyang@proton.me
基于:
  - v2.5 行业分析与聚焦标准版已交付
  - v2.5 TODO #1 三大师 16 条优化已交付(模块层),UI 集成留 v2.6
父目标:
  - 康波周期 ETF 配置自顶向下视角
  - 三大师评分体系自底向上 UI 完整化
---

# 📐 preson v2.6 · 康波 ETF 配置 + 三大师 UI 集成 + 黄金模块深化

> 状态:已交付,归档于 docs/plans/。黄金模块深化(板块 F+G+H+I)等已落地(详见项目记忆 project_v26_*),本文保留作历史存档。
>
> **三主题**:
>
> - **主题 1 · 康波 ETF 配置**(自顶向下"该配什么")— 打造「康波周期 → 推荐组合 → 同行业 N 选 1」Tab
> - **主题 2 · 三大师 UI 集成**(自底向上"该怎么打分")— 把 v2.5 TODO #1 模块层产出从"独立函数"升级为"用户可见 Dashboard 交互"
> - **主题 3 · 黄金模块深化**(纵深扩展"黄金赛道")— 加金股 ETF(放大版黄金 ETF)+ 红绿灯杠杆操作建议
>
> **总工时**:~36-42h(主题 1 ~12-15h + 主题 2 ~17-20h + 主题 3 ~5-7h)
>
> **推荐启动时机**:v2.5 TODO #1 已收口,v2.6 即可启动

---

## 🎯 用户痛点 → v2.6 解决

| 用户原话(2026-05-10) | 现状(v2.5 后) | v2.6 解决 |
|---|---|---|
| "基于康波周期推荐的行业,有哪些 ETF" | 🟡 yaml 已有 19 行业 × 35 ETF 完整映射,**但没有反向「康波 → 完整组合」的入口** | ✅ 阶段 1:独立「📐 康波配置」Tab,3 层组合全景 |
| "并且进行分析" | 🟡 ETF 对比仅 1y 涨跌 + 流动性 | ✅ 阶段 2:补费率 + 规模 + 同行业 N 选 1 推荐 |
| "列出作为计划需要考虑的内容" | — | ✅ 本文档 |

---

## 📦 推荐版交付物清单(2 阶段)

### 🏔️ 阶段 1 · 「📐 康波配置」Tab(MVP / ~6-8h)

新建独立 Tab(挂在 🏭 行业分析 后,作为 PAGES 第 10 项),主结构:

```
┌─ 顶部 banner ────────────────────────────────────────┐
│ 当前康波位置:萧条期中后段(第 5 次康波)            │
│ 配置目标:防御 65-75% / 进攻 25-35% / 过渡 0-5%      │
│ 实时信号(只读 macro.duckdb,不联动判定):           │
│   实际利率 +1.63% (87 分位) / CPI -0.3% / M2 8.2%   │
└──────────────────────────────────────────────────────┘

🛡️ 防御层(目标 65-75%)
  │ 黄金 15-20% │ 国债 10-15% │ 红利低波 15-20% │ 白酒 10-15%
  │ 银行 10-15% │ 家电 5-10%  │ 食品 5-10%       │ 保险 3-8%
  └─ 每行业 expander 默认收起,展开看同行业 N 只 ETF 横评 + Top 1 推荐

⚡ 进攻层(目标 25-35%)
  │ 半导体 / 通信 / 全球 AI / 新能源车 / 电池 / 化药 / AI 云 / 光伏 / 生物科技

🔄 过渡层(目标 0-5%)
  │ 化工 / 央企价值
```

#### 阶段 1 交付物

- `.tools/dashboard/kondratieff_loader.py`(~150 行)— 数据聚合层,把 yaml + etf.duckdb 组装成三层结构
- `.tools/dashboard/etf_compare.py`(~150 行)— 同行业 N 只 ETF Top 1 选优引擎(1y 涨跌 + 流动性 + 主流派加权)
- `.tools/dashboard/tabs/kondratieff.py`(~400-500 行)— Tab UI,3 层组合 + 行业 expander + 同行业横评归一化叠加图
- `.tools/dashboard/test_kondratieff_loader.py` + `test_etf_compare.py` + `test_kondratieff_tab.py`(各 8-12 项 pytest)
- `app.py` 加 `PAGE_KONDRATIEFF = "📐 康波配置"` + render 调度

#### 阶段 1 设计要点

- **完全复用** v2.5 已有 `industry_etf_mapping.yaml` 数据(不写新 yaml)
- **Tab 主色金棕色**(`#a16207 → #ca8a04`,对照林奇绿/格雷厄姆蓝/黄金金/芒格紫/行业森林绿,与"康波/经济周期"色调贴合)
- **不做组合优化器**(资金分配计算器)— 跳过阶段 3,优先 MVP
- **不联动康波信号判定** — current_phase 仍读 yaml 静态字段;实时信号(实际利率等)只展示供用户参考,不替换 phase
- **同行业 N 选 1** 复用 v2.5 etf_recommender.py(已有 1y 涨跌 + 流动性分位)

---

### 📊 阶段 2 · ETF 元数据扩展(~5-7h)

补 etf.duckdb 缺的字段,让同行业 N 选 1 有更全维度。

#### 阶段 2 交付物

- `.tools/db/fetch_etf_meta_extra.py`(~150 行)— AkShare `fund_etf_fund_em` 抓 35 ETF 的:
  - **管理费率**(`management_fee`)
  - **托管费率**(`custodian_fee`)
  - **基金规模**(`fund_size`,资产净值,亿元)
  - **跟踪指数 code**(`tracking_index`,作为后续阶段 3 跟踪误差的基础)
- `etf.duckdb` schema 扩 `etf_meta` 表(idempotent ALTER ADD COLUMN)
- 接入 `update.py` weekly cron(monthly 频率,~第 1 日触发)
- v2.5 `etf_recommender.py` ETFCandidate dataclass 加 `fee_total / fund_size` 字段填充
- v2.5 `tabs/industry_focus.py` C 区表格加 2 列(费率 + 规模)
- v2.6 `tabs/kondratieff.py` 同行业横评加 2 列
- `.tools/db/test_fetch_etf_meta_extra.py`(~6-8 项)— 离线 mock 测试

#### 阶段 2 设计要点

- **不算跟踪误差**(跳过 — 需要基准指数表 + 计算引擎,~3h 增量,边际收益低)
- **不爬 jin10**(避开记忆里 ssl 卡 + 中国 IP geo-block 坑;AkShare 失败时字段保 null,UI 标"未入库")
- **数据稳定性**:费率 + 规模 月度变化,monthly cron 即可,不必 weekly(节省 API 调用)
- **AkShare 接口**:`ak.fund_etf_fund_em()` 返回全市场 ETF 一张表;按 35 ETF code filter

---

---

## 🎯 主题 2 · 三大师 UI 集成(v2.5 TODO #1 收口 / ~17-20h)

> v2.5 TODO #1 已交付 16 条评分规则优化 + 3 套 extras 模块,但**模块函数没接到 UI**。v2.6 把它们接入对应 Tab,让用户在 Dashboard 直接看到所有新功能。

### 📦 板块 A · 林奇 Tab 深化(~6-7h / P0)

#### A1 · 4 类型(slow/cyclical/turnaround/asset_play)分类后专属评分卡(~2.5h)

- 现状:[lynch_abcd_scorer.py](.tools/dashboard/lynch_abcd_scorer.py) 只对 stalwart + fast_grower 做 ABCD 评分
- 实施:`score_abcd()` 入口加 4 类型路由,各自读 [lynch.yaml](.tools/rules/lynch.yaml) 对应段(`slow_grower_rules` / `cyclical_rules` / `turnaround_rules` / `asset_play_rules`)
- UI:[lynch_analysis.py:1864 _step_6_abcd_evaluation](.tools/dashboard/tabs/lynch_analysis.py#L1864) 渲染逻辑加分支,每类型展示对应规则评分明细

#### A2 · `insider_proxy_score` 接 第 3 步财务护栏(~1h)

- 接入位置:[_step_3_financial_guardrails](.tools/dashboard/tabs/lynch_analysis.py#L1269)
- UI:加"内部人代理信号"卡片(股东户数变动 5d/30d/90d 走势)
- AkShare 失败优雅降级显示"verified=False 数据未就绪"

#### A3 · `institutional_holding_proxy` 接 第 3 步财务护栏(~1h)

- 同 A2 入口,加"机构持仓代理"卡片(主力净流入 / 北向资金占比代理)

#### A4 · `peg_curve_grade` 接 第 4 步 PEG 估值(~1h)

- 接入位置:[_step_4_peg_valuation](.tools/dashboard/tabs/lynch_analysis.py#L1440)
- 现状:已显示 PEG 时间曲线;实施:曲线下加 grade 卡 — "近 5 年 PEG < 1.0 占比 N% → grade A/B/C/D"

#### A5 · `quarterly_continuity_score` 接 第 6 ABCD 评估(~0.5h)

- hits_10/hits_20 已在 v2.3 D1 块 A 落地,UI 加进度条 + 解读卡

#### A6 · 知识库 09_六类完整评分速查.md(~0.5h)

- 新建 `01_knowledge/03_投资策略与选股/02_彼得林奇投资法/09_六类完整评分速查.md`,6 类公司评分规则汇总 + 16 家持仓案例对照

#### A7 · 测试扩(~0.5h)

- 4 公司离线冒烟:茅台(stalwart)/招行(slow_grower)/三美(cyclical)/比亚迪(fast_grower);AppTest PAGE_LYNCH 各 sub-tab 关键词命中

---

### 📦 板块 B · 格雷厄姆 Tab 深化(~4-5h / P0)

#### B1 · g7 OR 条件 UI 显示(~0.5h)

- 接入位置:[_render_step3_health](.tools/dashboard/tabs/graham_analysis.py#L219) 或第 2 步硬指标统计
- UI:7 准则表里 g7 列展示"PB ≤ 1.5 OR PE×PB ≤ 22.5",哪条满足显示哪个;高 PE 公司案例 callout

#### B2 · NCAV bonus 卡片(~1h)

- 接入位置:第 4 步估值底部
- 调用 [graham_extras.compute_ncav_status(ticker)](.tools/dashboard/graham_extras.py)
- UI:卡片显示 NCAV / 市值 / ratio / status(no_data / negative_ncav / extremely_cheap / fair)

#### B3 · 第 6 sub-tab 新增「🪙 沃尔特·施洛斯简版」(~1.5h)

- [render](.tools/dashboard/tabs/graham_analysis.py#L672) `st.tabs([...])` 加第 6 项
- 调用 [graham_schloss_view.schloss_quick_score(ticker)](.tools/dashboard/graham_schloss_view.py)
- UI:15 项一页式过/未过 + 总分 + 评级(A:13-15 / B:10-12 / C:7-9 / D:0-6)

#### B4 · graham_router 接 graham_steps.py(~1h)

- 现状:graham_router 仅在 [screener.py](.tools/dashboard/screener.py) 接入,[graham_steps.py](.tools/dashboard/graham_steps.py) 仍走主 yaml
- 实施:graham_steps.py 入口加 `route_yaml(ticker)` 调用,选对应 yaml 跑五步分析(招行→bank yaml / 新华→insurance yaml)

#### B5 · graham_yaml_steps_mapping.md 接 README(~0.5h)

- [graham_yaml_steps_mapping.md](.tools/rules/graham_yaml_steps_mapping.md) 已有;在 [01_格雷厄姆投资法/README.md](01_knowledge/03_投资策略与选股/01_格雷厄姆投资法/) 加跳转链接

#### B6 · 测试扩(~0.5h)

- AppTest 第 6 sub-tab 渲染 0 异常;离线冒烟 4 公司(招行/新华/茅台/美的 走对应 yaml)

---

### 📦 板块 C · 巴菲特独立 Tab 新建(~7-8h / P0)

> **关键**:巴菲特目前没独立 Tab(评分仅作"评分卡"集成在公司详情);v2.6 新建跟林奇/格雷厄姆/芒格平行的独立 Tab。

#### C1 · 新建 `tabs/buffett_analysis.py` 骨架(~1h)

- 巴菲特橙色 banner(对照林奇绿/格雷厄姆蓝/黄金金/芒格紫)
- 5 sub-tab 设计:
  - ① 方法论速览 — 5 项护城河 + Owner Earnings 公式 + 经典语录
  - ② 5 项硬门槛 5 档梯度评分
  - ③ Owner Earnings 计算明细(简化版 vs 完整版对比)
  - ④ 留存收益再投资分析
  - ⑤ 5 项护城河主观打分
- [app.py](.tools/dashboard/app.py) PAGES 加 `PAGE_BUFFETT = "💎 巴菲特价值投资法"`

#### C2 · 5 档梯度评分可视化(~1.5h)

- 调用 [buffett_extras.py](.tools/dashboard/buffett_extras.py) + `engine.eval_rule` grades 求值
- UI:5 张卡片(每条规则一张)显示当前实测值 / 落入档位 / 颜色梯度 / 跨届距离("距 fair 还差 2.3pp")

#### C3 · Owner Earnings 详情页(~2h)

- 调用 `compute_owner_earnings(ticker)` + `simple_owner_earnings(ticker)`
- 完整版若 verified=False 显示 P3 阻塞说明;简化版用 free_cash_flow 展示 10 年 CAGR + 各年明细

#### C4 · 留存收益再投资分析(~1.5h)

- 调用 `retained_earnings_breakdown(ticker, years=10)`
- 表格:year / eps / dividend_per_share / retained_eps / eps_growth_yoy / 留存回报率
- 折线图:累计留存 EPS vs 累计 EPS 增量(12% 复合线对照)

#### C5 · 护城河 5 项 checkbox 录入 UI(~1.5h)

- 5 项:brand / switching_cost / network_effect / economies_of_scale / intangible_assets
- 每项 0-2 分;存到 [.config/buffett_qualitative.yaml](.config/buffett_qualitative.yaml)
- 调用 `load_qualitative_score(ticker)` / `save_qualitative_score(ticker, scores)`

#### C6 · 测试扩(~0.5h)

- AppTest:PAGE_BUFFETT 5 sub-tab 关键词命中
- 离线冒烟 3 公司:茅台(高分)/美的(中分)/招行(走 industry_alternatives)

---

### 📦 板块 D · 三大师交叉联动(~2-3h / P1)

#### D1 · 公司详情 Tab 加「三大师投票」总览卡(~1h)

- 接入位置:[tabs/company.py](.tools/dashboard/tabs/company.py) 区块 A 顶部 Hero 卡之上或之下
- UI:横向 3 卡(林奇/巴菲特/格雷厄姆)+ 一致性投票(3 同意"强力买入" / 2 同意"可关注" / 1 同意"观望")

#### D2 · sidebar 加大师 Tab 快捷跳转(~1h)

- 当前公司确定后,sidebar 加 3 个快捷按钮("林奇 / 巴菲特 / 格雷厄姆 分析"),点击直接跳到对应 Tab

#### D3 · 决策中心引用三大师(~1h)

- [tabs/decision_center.py](.tools/dashboard/tabs/decision_center.py) 录入 expander 自动注入"三大师投票"字段(类似 v2.3 peer_advice)
- 决策日志显示列加"三大师"

---

### 📦 板块 E · v2.5 TODO #2 行业分析模块验收 + memory 沉淀(~1h / P1)

- 跑全套测试确认 219+ 全过
- AppTest PAGE_INDUSTRY_FOCUS 渲染 0 异常
- 8 聚焦行业 Top 7 选优实测看是否真出推荐
- memory 沉淀:`project_v25_industry_analysis_delivered.md`(8 任务包 / 行业卡 / 引擎层)
- PROGRESS.md 顶部"最后更新"行去掉"全交付"夸大,改成"v2.6 待 UI 集成"

---

---

## 🎯 主题 3 · 黄金模块深化(金股 ETF + 红绿灯杠杆建议 / ~5-7h)

> **用户原话(2026-05-11)**:"在黄金 ETF 之外,增加一个黄金股 ETF 的分析,以及,基于红绿灯的操作建议,我的理解是放大版的黄金 ETF"
>
> **核心洞察**:黄金股 ETF(金矿股票挂钩)相对实物黄金 ETF 是**杠杆放大工具**,β 通常 1.5-2.5 倍 — 金价涨 10% 时金股 ETF 可能涨 20%,反之同理。

### 📊 现状盘点

| 资产 | 现状 |
|---|---|
| 实物黄金 ETF(SGE 挂钩) | ✅ gold.duckdb `gold_etf_master` 已有 4 只:518880/159937/518800/159934 |
| 金股 ETF(金矿股票挂钩) | 🔴 **缺失** — etf.duckdb 35 只 ETF 中无金股相关;159562/517400/159830/588120 等主流金股 ETF 未抓 |
| 红绿灯 verdict | ✅ [overheat_engine.py](.tools/dashboard/overheat_engine.py) 已有 add/hold/reduce 5 档 verdict |
| 仓位走廊 | ✅ [position_corridor.py](.tools/dashboard/position_corridor.py) 已有 5 档折扣;但仅作用于"实物黄金"配置 |

### 📦 板块 F · 金股 ETF 数据层(~2h)

- 新建 `.tools/db/fetch_gold_stock_etf.py` — AkShare `fund_etf_hist_em` 抓 4-5 只主流金股 ETF
  - 候选清单(2026-05 主流):159562(永赢黄金股)/517400(南方有色金矿)/159830(华夏中证沪深港金属矿业)/588120(国泰中证沪深港金属矿业)
- `gold.duckdb` 扩 2 表(idempotent DDL):
  - `gold_stock_etf_master`(同 `gold_etf_master` 结构:etf_code/etf_name/exchange/manager/tracking_index/fee_rate/listing_date)
  - `gold_stock_etf_prices`(同 `gold_etf_prices` 结构:date/etf_code/open/close/high/low/volume/turnover_rate)
- 接入 [update.py](.tools/db/update.py) weekly cron(`--skip-gold-stock` 兜底)

### 📦 板块 G · β 计算引擎(~1h)

- 新建 `.tools/dashboard/gold_stock_beta.py`
- 计算每只金股 ETF 相对参考黄金 ETF(默认 518880)的滚动 β:
  - `beta_30d` / `beta_60d` / `beta_180d` 三档窗口
  - 输出 dataclass `GoldStockBeta(etf_code, beta_30d, beta_60d, beta_180d, r_squared, as_of)`
- 公式:`β = Cov(R_stock_etf, R_gold_etf) / Var(R_gold_etf)`,日收益率回归
- 接口:`compute_beta(stock_etf_code, gold_etf_code='518880', window=60) -> GoldStockBeta`

### 📦 板块 H · 红绿灯杠杆建议(~1h)

- 扩 [overheat_engine.py](.tools/dashboard/overheat_engine.py) 加 `stock_etf_advice(verdict, beta) -> dict` 函数
- 扩 [gold_overheat.yaml](.tools/rules/gold_overheat.yaml) 加 `stock_etf_position` 段:

```yaml
stock_etf_position:
  # 金股建议矩阵(基于金价 verdict + 金股 β)
  matrix:
    add_low_beta:    { verdict: add,    beta_max: 2.0,  advice: 🟢 可加金股放大收益, position_multiplier: 1.2 }
    add_high_beta:   { verdict: add,    beta_min: 2.0,  advice: 🟡 谨慎加金股(β 过高), position_multiplier: 1.0 }
    hold_any:        { verdict: hold,   advice: 🟡 持金股观望, position_multiplier: 1.0 }
    reduce_high_beta:{ verdict: reduce, beta_min: 1.5,  advice: 🔴 优先减金股(放大下跌), position_multiplier: 0.6 }
    reduce_low_beta: { verdict: reduce, beta_max: 1.5,  advice: 🔴 减金股(同步), position_multiplier: 0.8 }
```

- 与 `position_corridor` 配合:战略目标 X% 黄金中,**金股 / 实物 比例**根据上述 multiplier 微调

### 📦 板块 I · UI 第 ⑦ sub-tab「📈 金股 ETF 杠杆视图」(~2h)

- 在 [tabs/gold_analysis.py](.tools/dashboard/tabs/gold_analysis.py) 现有 6 sub-tab 后加第 ⑦
- 布局:
  - **顶部 banner**:当前金价红绿灯 verdict + 金股 ETF 杠杆建议(基于 β 加权)
  - **主图**:金股 ETF 价格 vs 黄金 ETF 价格归一化叠加(180d)+ β 30d 滚动线副图
  - **表格**:4-5 只金股 ETF 横评 — 代码 / 名称 / 规模 / 费率 / 1y 涨跌 / β_30d / β_60d / 当前杠杆建议
  - **决策卡**:基于"金价 verdict + 每只金股 β"给出每只金股 ETF 的"加/持/减"建议 + 仓位 multiplier
  - **教育卡**:一句话解释"金股 = 放大版黄金 ETF" + β 含义 + 杠杆双向性提醒

### 📦 板块 J · 测试(~1h)

- `test_fetch_gold_stock_etf.py`(mock AkShare,验证字段映射 + idempotent ALTER)
- `test_gold_stock_beta.py`(用合成时序验证 β 计算正确性)
- `test_overheat_engine_stock.py`(5 verdict × beta 阈值 5 路径全覆盖)
- AppTest:PAGE_GOLD 第 ⑦ sub-tab 关键词命中(银/股/β/杠杆/放大)
- 离线冒烟:4 只金股 ETF 跑全套 + 黄金 ETF 对比

### 主题 3 完成判定

1. `python3 .tools/db/fetch_gold_stock_etf.py` 一次成功 → gold.duckdb 新增 2 表填充 4-5 只金股 ETF × 1y+ 价格
2. 打开「🥇 黄金分析法」Tab → 第 ⑦ sub-tab「📈 金股 ETF 杠杆视图」可见
3. 顶部 banner 显示当前金价 verdict + 金股建议(如"🟡 谨慎加金股 / β 2.3 偏高")
4. 4-5 只金股 ETF 横评表 + β 滚动图正常渲染
5. 每只 ETF 决策卡显示个性化建议(基于该只 β + 当前 verdict)
6. AppTest 0 异常 + 4-5 项单测全过
7. weekly cron 自动跑 fetch_gold_stock_etf + 更新 β 快照

### 主题 3 设计要点

- **复用 v2.5 D2 资产**:gold.duckdb schema 模式 / overheat_engine verdict 体系 / position_corridor 折扣思路完全可套
- **不算 GDX/GDXJ**(美股,中国 IP / 数据源阻塞;A 股金股 ETF 已足够代表)
- **不做主动选股**(不深入到金矿单股 紫金/山东黄金/赤峰黄金,那是公司分析 Tab 的事;此处只看 ETF 层)
- **β 双向性提醒**:UI 必须显式标注"放大上涨 = 放大下跌",避免用户单向解读

### 主题 3 风险与缓解

| 风险 | 缓解 |
|---|---|
| AkShare 金股 ETF 价格接口偶尔超时 | 复用 fetch_gold_etf retry 模式;失败时保留上期数据 |
| β 计算窗口短(30d)波动大 | 默认展示 60d,30d 作辅助;窗口可在 UI 切换 |
| 金股 ETF 跟踪指数差异(沪深港金属矿业 vs 纯金股)| 在 yaml 标 `tracking_index` 让用户知情;同行业横评归一 |
| 不同金股 ETF 规模差大(亿级到几百亿)| 表格按规模降序,小规模 ETF 标"流动性偏低" |
| 用户把"金股建议"误用到"金价见顶就空金股"| UI 教育卡明确:金股 = 杠杆工具,不是反向工具 |

---

## 📌 附录 · 历史尾巴收口(2026-05-11 加入 / ~7-10h / P1)

> 用户审计 v2.6 前各版本未收口债务,以 v2.6 为分界点统一归并。v2.5 TODO / v2.4 候选 / v2.1 文件中对应条目已在迁入时清理。
> 编号用 PATCH-* 避开主题 3 已占用的板块 F/G/H/I/J(参考 memory: 平行任务命名避免歧义)。

### PATCH-1 · 格林布拉特预设从 M3 筛选 Tab 下架(~0.5-1h / P0)

- 来源:v2.5 TODO #1 决策(2026-05-10 "只保留林奇/巴菲特/格雷厄姆 3 套",greenblatt 一并下线)
- 实施:`.tools/dashboard/presets.yaml` 删除 `greenblatt` 条目;M3 筛选 Tab 顶部预设按钮 4 → 3
- 保留 `.tools/rules/greenblatt.yaml` 文件(评分引擎可能仍引用),仅从 UI 入口下架
- 同步清理 PROGRESS.md L20 "TODO #1 4→7"过时表述

### PATCH-2 · 行业分析 Tab × 康波 ETF 联动(~3-4h / P1)

- 背景:v2.5 投 12-15h 交付的「🏭 行业分析」Tab 与 v2.6 主题 1 康波 ETF 配置有协同机会未被显性利用
- 实施:
  - 「🏭 行业分析」Tab D 区(行业知识 + 周期特性)加"康波阶段联动"行 — 显示该行业在当前康波阶段属于防御/进攻/过渡哪一层 + 一键跳转「📐 康波配置」
  - 「📐 康波配置」Tab 行业 expander 加"打开行业分析 Tab"反向按钮
- 复用 v2.5 `industry_master.yaml` + v2.6 阶段 1 `kondratieff_loader.py`,不写新数据层

### PATCH-3 · 大师评分迷你回测(~6-8h / P2 / 可推 v2.7)

- 来源:v2.4 候选 ④ 决策回测系统(跨多版本未做,数据条件现已成熟)
- 现状:L2 行业代表池 + 三大师评分体系 + market.duckdb 已就位
- 实施:
  - `.tools/dashboard/master_backtest.py` — 给定历史时点 + 大师方法 → Top N 公司 → 持有 1/3/5y 回报
  - 数据池用 L2 ~200-300 家(非全 A 股,避免幸存者偏差工作量);3 大师 × 3 时间窗 = 9 组对照
  - 新建独立「📈 大师回测」Tab(挂在「📐 康波配置」后)
- **若工时吃紧,PATCH-3 可整体推到 v2.7,不阻塞 v2.6 主线**

### PATCH-4 · v2.1 旧文档归档(~5min / P3 / ✅ 已完成 2026-05-11)

- `PROGRESS_v2.1_dashboard.md` + `PROJECT_PLAN_v2.1_dashboard.md` 已并入 PROGRESS.md
- 已执行:两份文件已 `mv` 到 `.archive/`

### 附录完成判定

- M3 筛选 Tab 顶部按钮 3 个,无 greenblatt
- 「🏭 行业分析」D 区显示康波联动,「📐 康波配置」行业 expander 有反向跳转
- (若 PATCH-3 在 v2.6 做)「📈 大师回测」Tab 上线
- ✅ `.archive/` 已含 v2.1 两份旧文件

---

## 🛑 已定型决策(用户已拍板,不再追问)

| # | 决策点 | 已选择 |
|---|---|---|
| 1 | 版本档位 | 推荐版(阶段 1 + 阶段 2,跳过阶段 3) |
| 2 | Tab 挂载位置 | 方案 A 独立 PAGE_KONDRATIEFF,挂在 🏭 行业分析 后 |
| 3 | 组合优化器(资金分配计算器) | ❌ 跳过(阶段 3 内容) |
| 4 | 康波信号自动化(phase 实时判定) | ❌ 跳过(阶段 3 内容);只读展示 macro 信号供参考 |
| 5 | 跟踪误差 | ❌ 跳过(阶段 2 收益最低) |

---

## 🔗 任务依赖图(2 波并行可压缩到 ~6-8h 墙时间)

```
Wave 1(并行,无依赖):
  ├─ 01_data_loader        kondratieff_loader.py 数据聚合
  ├─ 02_etf_compare        etf_compare.py 同行业 N 选 1
  └─ 04_etf_metadata       fetch_etf_meta_extra.py + etf.duckdb 扩字段

Wave 2(依赖 Wave 1):
  └─ 03_tab_ui             tabs/kondratieff.py + app.py 接入 + 测试
                           顺手在 industry_focus.py C 区加 2 列
```

参考 v2.5 经验:**主对话直写比 agent 并行稳**(避免 600s stall)。建议主对话顺序写 4 个模块。

---

## 📋 任务包

详见 [../tasks/v2.6_kondratieff/](../tasks/v2.6_kondratieff/):
- [README.md](../tasks/v2.6_kondratieff/README.md) — 总览 + 接口契约
- [01_data_loader.md](../tasks/v2.6_kondratieff/01_data_loader.md)
- [02_etf_compare.md](../tasks/v2.6_kondratieff/02_etf_compare.md)
- [03_tab_ui.md](../tasks/v2.6_kondratieff/03_tab_ui.md)
- [04_etf_metadata.md](../tasks/v2.6_kondratieff/04_etf_metadata.md)

---

## 🚧 风险与缓解

| 风险 | 缓解 |
|---|---|
| AkShare `fund_etf_fund_em` 接口偶尔不返回某些 ETF 元数据 | 字段保 null;UI 标"未入库";后续手填 csv 备份 |
| current_phase 仍是手填字符串,2026 年内若康波转段需手动改 yaml | 阶段 3 才做自动化;短期内萧条期不会切,影响小 |
| 同行业 N 选 1 算法把"高 1y 涨幅低规模"的 ETF 排前面 | 加权:流动性(60d turnover 分位)40% + 1y 涨跌 30% + 规模 30%(阶段 2 后);UI 上同时展示 N 只让用户自选 |
| ETF 主流派(主题/龙头/红利)分类来自 yaml 手填,有主观性 | 已有 industry_etf_mapping.yaml 标注;以 yaml 为准 |
| Tab 加载首次慢(35 ETF × 多次 SQL) | `@st.cache_data(ttl=1800)` 包数据加载;首次 < 5s 后续 cache hit < 1s |

---

## ✅ 全部完成判定

### 主题 1 · 康波 ETF 配置

1. `streamlit run app.py` → sidebar 看到「📐 康波配置」入口
2. Tab 顶部 banner 显示当前 phase + 实时 macro 信号(只读)
3. 防御层 / 进攻层 / 过渡层 三块全展示,合计行业数 = 19
4. 任意行业 expander 展开 → 同行业 N 只 ETF 横评 + Top 1 推荐 + 1y 归一化叠加图
5. ETF 表格含 6 列:代码 / 名称 / 主题 / 1y 涨跌 / 流动性分位 / **费率** / **规模**(阶段 2 后)
6. 月度 cron 跑 `fetch_etf_meta_extra.py` → etf.duckdb 元数据自动更新
7. 既有 v2.5 industry_focus Tab C 区也跟着补费率 + 规模 2 列
8. 5 套测试全过(loader 8+ / etf_compare 8+ / tab UI 12+ AppTest / metadata 6+ / industry_focus 回归 18 不破坏)

### 主题 2 · 三大师 UI 集成

9. sidebar 选「💎 巴菲特价值投资法」可见独立 Tab + 5 sub-tab 全交付
10. 林奇 6 sub-tab + 格雷厄姆 6 sub-tab(新增 Schloss 简版)全部接 v2.5 新功能
11. 林奇 ABCD 评估对 4 类型(slow/cyclical/turnaround/asset_play)显示对应规则评分明细
12. 格雷厄姆 招行/新华 走 graham_bank/insurance yaml(无论 screener / 五步法 Tab)
13. 公司详情顶部「三大师投票」一致性卡可见
14. 护城河录入 → 写入 `.config/buffett_qualitative.yaml` 持久化
15. 6+ 套新测试全过(buffett_tab 12+ / lynch_extras_ui 8+ / graham_extras_ui 8+ / cross_master 6+)

### 主题 3 · 黄金模块深化

1. `python3 .tools/db/fetch_gold_stock_etf.py` 一次成功 → gold.duckdb 新增 2 表填充 4-5 只金股 ETF × 1y+ 价格
2. 「🥇 黄金分析法」第 ⑦ sub-tab「📈 金股 ETF 杠杆视图」可见
3. 顶部 banner 显示金价 verdict + 金股建议(如"🟡 谨慎加金股 / β 2.3 偏高")
4. 4-5 只金股 ETF 横评表 + β 滚动图 + 每只决策卡正常渲染
5. weekly cron 自动跑 fetch_gold_stock_etf + 更新 β 快照
6. 4-5 项单测全过(fetch / beta / overheat_engine_stock / AppTest 第 ⑦ sub-tab)

---

## 📈 v2.6 完成后版图

| 维度 | 当前 | v2.6 后 |
|---|---|---|
| 单公司视角 | 🟡 林奇/格雷厄姆/芒格/黄金/决策中心 5 Tab(巴菲特无独立 Tab) | ✅ **新增 💎 巴菲特独立 Tab**;林奇/格雷厄姆 sub-tab 各深化到 6 sub-tab |
| 黄金模块 | 🟡 实物黄金 ETF 4 只 + 红绿灯 verdict + 仓位走廊 | ✅ **新增金股 ETF 杠杆视图**(第 ⑦ sub-tab / 4-5 只 / β 滚动 / 杠杆建议矩阵) |
| 三大师投票 | 🔴 缺失 | ✅ **公司详情 Hero 卡顶部 3 大师投票一致性视图** |
| 林奇评分 | 🟡 仅 stalwart + fast_grower 走 ABCD | ✅ 6 类型全覆盖 ABCD 评分 |
| 格雷厄姆评分 | 🟡 招行/新华仅 screener 链路自动切;Tab 五步法仍走主 yaml | ✅ Tab 五步法也按行业切 bank/insurance |
| 行业视角 | ✅ v2.5 🏭 行业分析 4 区单行业 | 不变 |
| **组合视角** | 🔴 缺失(只能从 yaml 看,无 UI) | ✅ **新增 📐 康波配置 Tab** |
| ETF 元数据 | 🟡 仅价格 + 流动性 | ✅ 加费率 + 规模 |
| 决策中心 | 🟡 已注入 peer_advice | ✅ 自动注入"三大师投票" |

---

## 📝 版本日志

| 日期 | 变更 |
|---|---|
| 2026-05-10 | 初始化 v2.6 计划(用户基于 v2.5 后追问"康波 → ETF 推荐",推荐版定型;阶段 3 信号自动化 + 组合优化器留 v2.7) |
| 2026-05-10 | **扩展 v2.6 加主题 2 · 三大师 UI 集成**(用户拍板"添加到 v2.6 作为新板块")— 把 v2.5 TODO #1 落地的 16 条评分优化 + 3 套 extras 模块从"独立函数"升级为"用户可见 Dashboard 交互";新增板块 A(林奇 Tab 深化)/ B(格雷厄姆 Tab 深化)/ C(巴菲特独立 Tab 新建)/ D(三大师交叉联动)/ E(行业模块验收 + memory 沉淀);总工时 ~12-15h → ~30-35h |
| 2026-05-11 | **扩展 v2.6 加主题 3 · 黄金模块深化**(用户原话"在黄金 ETF 之外加金股 ETF + 红绿灯操作建议;放大版黄金 ETF")— 新增板块 F(金股 ETF 数据层 + gold.duckdb 加 gold_stock_etf 2 表)/ G(β 计算引擎 30/60/180d)/ H(红绿灯杠杆建议 5 路径矩阵)/ I(第 ⑦ sub-tab「📈 金股 ETF 杠杆视图」)/ J(测试);候选金股 ETF:159562/517400/159830/588120;总工时 ~30-35h → ~36-42h |
