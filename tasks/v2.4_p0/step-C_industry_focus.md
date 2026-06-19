---
name: step-C · 行业聚焦 + 自动选优
candidate: 候选 ⑪
priority: P0
estimate: ~6-8h
depends_on: 弱依赖 step-A(可先做骨架)+ 强依赖 v2.3 已有评分体系
blocks: 无
---

# step-C · 行业聚焦 + 自动选优(候选 ⑪)

> 用户在 yaml 勾选 8 行业,系统自动算行业内 Top 7,「🎯 行业聚焦」Tab 展示 + 一键加深度跟踪。

---

## 🎯 任务目标

**用户原话**:"我更加希望聚焦某些行业,然后在行业中找到优秀的公司"

**本 step 解决**:从"自选 15 家自我观察"升级为"聚焦 N 行业 × 系统持续推荐 Top 7"。**复用 v2.3 已有评分体系**(8 大师 + lynch 分类器 + bank/insurance 变体),**不写新评分规则,只组装**。

---

## 📦 交付物清单

### 1. 配置文件

- [ ] `.config/focus_industries.yaml` — 用户聚焦行业(默认填 8 个示例,允许编辑):
  ```yaml
  focus:
    - industry: 白酒Ⅱ
      type: stalwart        # 林奇分类:稳健消费
      weight: 1.0
    - industry: 银行Ⅱ
      type: bank            # 用 graham_bank.yaml + piotroski_bank.yaml
      weight: 1.0
    - industry: 创新药
      type: fast_grower     # 用 lynch.fast_grower + DCF
      weight: 1.0
    - industry: 乘用车
      type: cyclical
      weight: 1.0
    - industry: 白色家电
      type: stalwart
      weight: 1.0
    - industry: 电池
      type: fast_grower
      weight: 1.0
    - industry: 通信设备
      type: fast_grower
      weight: 1.0
    - industry: 饮料乳品
      type: stalwart
      weight: 1.0

  top_n: 7                   # 每行业推荐 N 家
  market_cap_min: 5000000000 # 50 亿门槛(过滤微盘)
  ```

- [ ] `.tools/rules/industry_type_map.yaml` — 行业类型 → 评分规则映射(6 类型):
  ```yaml
  type_to_scoring:
    stalwart:
      primary: lynch_stalwart
      secondary: [graham, piotroski]
      weights: {lynch_stalwart: 0.5, graham: 0.3, piotroski: 0.2}
    fast_grower:
      primary: lynch_fast_grower
      secondary: [damodaran, piotroski]
    cyclical:
      primary: lynch_cyclical
      secondary: [graham, altman]
    bank:
      primary: graham_bank
      secondary: [piotroski_bank]
    insurance:
      primary: graham_insurance
      secondary: [piotroski_insurance]
    slow_grower:
      primary: graham
      secondary: [piotroski]
  ```

### 2. 选优引擎

- [ ] `.tools/dashboard/industry_screener.py`(~200-300 行)
  - `def list_industry_candidates(industry: str) -> list[ticker]`:
    - **初版**(step-A 未完成):从 `.config/companies.csv` + `peers.duckdb` 取该行业全部
    - **接 step-A 后**:从 `data/market.duckdb` market_spot 表筛 industry
    - 留 try/except 双源切换
  - `def score_company(ticker: str, scoring_type: str) -> dict`:
    - 复用 `.tools/dashboard/master_scoring.py` 已有引擎(若有)
    - 返回:`{score, breakdown: {metric: value}, reason: "ROE 22% / PE 15 / F-Score 7"}`
  - `def screen_industry(industry: str, type: str, top_n: int = 7) -> pd.DataFrame`:
    - list_industry_candidates → 逐家 score_company → 排序 → Top N
    - 字段:ticker / name / score / 一句话理由 / 是否已自选(L3)
  - `def screen_all_focus(focus_yaml_path) -> dict[industry, df]`:批量跑所有聚焦行业

### 3. Dashboard Tab

- [ ] `.tools/dashboard/tabs/industry_focus.py`(~250-350 行)
  - **顶部 banner**:N 个聚焦行业 × 行业景气度 / PE 中位 / 推荐 Top 3 一行
  - **行业卡片**(每行业 1 张 expander,默认全展开):
    - 行业名 + 类型 tag(stalwart/fast_grower/...)+ 最后更新时间
    - 行业速览:成份股数 / PE 中位 / ROE 中位 / 股息率中位
    - 推荐 Top 7 表格:rank / ticker / name / score / 一句话理由 / 🌟 已自选标记
    - 每只可点击 → `st.session_state["selected_company"] = ticker` + 跳转「林奇/格雷厄姆」Tab
    - **一键操作按钮**:
      - 🌟 加入 L3 自选(append `companies.csv`,提示用户去主窗口跑 lixinger 抓取)
      - 🏭 加入 L2 跟踪(step-A 完成后接,当前 disable + tooltip "需 step-A")
  - **行业内对比雷达图**:Top 7 在 5 维上的并列(估值 / 盈利 / 成长 / 现金流 / 安全性)
  - **侧栏**:聚焦行业编辑入口(读 `focus_industries.yaml`,提供 streamlit 表单写回)

### 4. app.py 接入

- [ ] `app.py` 加 `PAGE_INDUSTRY_FOCUS = "🎯 行业聚焦"` + sidebar 入口

### 5. 月报小工具(可选,有时间再做)

- [ ] `.tools/dashboard/industry_focus_monthly_report.py`
  - 每月 1 日 cron 跑 screen_all_focus → 写到 `02_companies/_行业聚焦月报/{YYYY-MM}.md`
  - diff 上月 → 进入/退出 Top 7 自动 highlight
  - 接入 update.py monthly cron

### 6. PROGRESS.md 更新

- [ ] 追加:
  ```markdown
  ## v2.4 step-C · 行业聚焦 + 自动选优(2026-05-XX)
  - focus_industries.yaml 8 聚焦行业默认配置
  - industry_type_map.yaml 6 类型 → 评分规则映射
  - industry_screener.py 选优引擎(~XXX 行)
  - 「🎯 行业聚焦」Tab(行业卡片 + Top 7 表 + 雷达 + 一键加自选)
  - 数据源:初版用 peers.duckdb,L1 hook 留 step-A 完成后接
  - 复用 v2.3 8 大师 + lynch 分类 + bank/insurance,零新规则
  ```

---

## 🛑 文件边界(防撞车)

- `.config/focus_industries.yaml`(新建)
- `.tools/rules/industry_type_map.yaml`(新建)
- `.tools/dashboard/industry_screener.py`(新建)
- `.tools/dashboard/tabs/industry_focus.py`(新建)
- `app.py`(加 PAGE_INDUSTRY_FOCUS + sidebar 一项)
- (可选)`.tools/dashboard/industry_focus_monthly_report.py`(新建)
- (可选)`02_companies/_行业聚焦月报/`(新建目录)

**不动**:step-A 的 market.duckdb / step-B 的 search_bar.py / step-D 的 gold 模块

---

## ✅ 完成判定

1. `cat .config/focus_industries.yaml` 显示 8 行业
2. 离线测试 screener:
   ```python
   from tools.dashboard.industry_screener import screen_industry
   df = screen_industry("白酒Ⅱ", "stalwart", top_n=5)
   assert len(df) >= 2  # 至少茅台 + 五粮液(自选库内白酒 2 家)
   assert "score" in df.columns
   assert "reason" in df.columns
   ```
3. `streamlit run app.py` → 「🎯 行业聚焦」Tab → 看到 8 行业卡片 + 各自 Top 7
4. 点茅台 → 跳转到林奇 Tab,selectbox 已切换
5. 改 focus_industries.yaml(去掉 1 个行业,加 1 个新行业)→ 刷新页面看到变化

---

## ⚠️ 已知坑

- **数据源双源**:初版只能跑自选 15 家 + peers ~80 家,白酒能给 2-5 家,医药能给 3-5 家。**必须在 UI 上明确标注"数据池:L3 自选 + L2 peers,候选 ⑨ Phase 1 完成后扩到全行业"**
- **lynch 分类器** 在 `.tools/dashboard/lynch_classifier.py`(v2.3 已有,~记忆 [project_dimension1_data_layer.md])。score_company 内部应自动判定单股的 lynch type,**不要硬绑 yaml 里的 industry → type 映射**(避免某些"白酒"也是 fast grower 的失准)
- **评分缓存**:每次切 Tab 跑 8 行业 × Top N 太慢,加 `@st.cache_data(ttl=3600)`
- **类型 yaml 引用现有规则**:`graham_bank` / `piotroski_bank` / `lynch_stalwart` 都是已有 yaml 文件名,不要新建
- **首次进入页面慢**:8 行业 × ~10 候选 × 8 大师 ≈ 640 次评分。如果实测 > 5s,优化:并行 + 缓存。底线:首次 < 10s,后续 cache hit < 1s

---

## 🔬 冒烟脚本(交付时跑)

```bash
cd /Users/gongyong/Desktop/Keyi/preson
source .venv/bin/activate

# 1. 离线引擎
python3 -c "
import sys; sys.path.insert(0, '.')
from tools.dashboard.industry_screener import screen_industry, screen_all_focus
df = screen_industry('白酒Ⅱ', 'stalwart', top_n=5)
print(df[['ticker', 'name', 'score', 'reason']])

# 全量
results = screen_all_focus('.config/focus_industries.yaml')
for ind, df in results.items():
    print(f'{ind}: {len(df)} 家, top1={df.iloc[0][\"name\"]}')
"

# 2. Streamlit headless 验证
streamlit run app.py --server.headless true &
sleep 5
curl -s http://localhost:8501/healthz && echo "OK"
```

---

## 📚 参考资料

- 记忆 [project_master_scoring_system.md](../../memory/project_master_scoring_system.md):8 大师评分体系
- 记忆 [project_p2_score_data_unblocked.md](../../memory/project_p2_score_data_unblocked.md):评分数据缺口已解锁
- 记忆 [project_dimension1_data_layer.md](../../memory/project_dimension1_data_layer.md):lynch_classifier 已有
- 已有评分 yaml:`.tools/rules/lynch.yaml` / `graham.yaml` / `graham_bank.yaml` / `piotroski.yaml` / `piotroski_bank.yaml` / `altman.yaml` / `damodaran.yaml` / `greenblatt.yaml`
- v2.3 D1 块 C 同行对比:`industry_compare_view.py`(逻辑参考)
