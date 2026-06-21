---
name: 06_tab_ui · 行业聚焦 Tab(F1+F2+F3+F4 + G1+G2)
covers: F1 / F2 / F3 / F4 / G1 / G2
priority: Wave 3(依赖 02/03/04/05 全完成)
estimate: ~6h
agent: agent-tab-ui
---

# 任务包 06 · 行业聚焦 Tab UI

> 4 区行业卡 + 顶部聚焦 banner + sidebar 编辑入口,把 4 个引擎(percentile / cycle / etf_recommender / screener)拼成一个完整 Tab。

---

## 📦 交付物

### 1. `.tools/dashboard/tabs/industry_focus.py`(~400-600 行)

#### 顶部 banner(G1 · 8 行业速览一行)

```
┌─────────────────────────────────────────────────────────────────┐
│ 🏭 8 聚焦行业速览                                  最后更新 5/10 │
├─────────────────────────────────────────────────────────────────┤
│ 白酒 防御·见顶 PE 78%  | 银行 价值·见底 PE 12% | 保险 价值·横盘    │
│ 化学制药 成长·上行 PE 56% | 电池 成长·见顶 PE 82% | 通信设备 ...   │
│ 白色家电 防御·上行 PE 45% | 饮料乳品 防御·横盘 PE 38%             │
└─────────────────────────────────────────────────────────────────┘
```

每行业一个紧凑卡(2 行),emoji + 周期阶段 + 估值分位 + Top 1 公司 + 推荐 ETF Top 1。

#### 行业卡 4 区(F1+F2+F3+F4)

每行业一张 expander(默认全展开),内部 4 区:

##### A 区 · 速览(F1)
```
🏭 白酒(SW L2)  类型:防御 stalwart   康波:萧条期防御核心
─────────────────────────────────────────────────────────
当前周期阶段:🔻 见顶(置信度 0.6)
PE 中位:24.5 / 第 78 分位 ⚠️    PB 中位:8.2 / 第 65 分位
龙头集中度:CR3 ~50%             成份股数:N=3(自选)
一句话现状:PE 第 78 分位 + 1y 上涨 +24% → topping
```

实现:调 `industry_percentile_engine.compute()` + `industry_cycle_engine.diagnose()`,组装 4 列 metric 卡。

##### B 区 · 推荐公司 Top 7(F2)
```
| Rank | Ticker | Name      | Score | Rating  | Reason                  | 自选 |
| 1    | 600519 | 贵州茅台   | 92    | 🟢 优秀 | ROE 32%/PE 24/F-Score 7 | 🌟  |
| 2    | 000858 | 五粮液     | 86    | 🟢 优秀 | ROE 22%/PE 25/...       | 🌟  |
| 3    | 000596 | 古井贡酒   | 78    | 🟢 优秀 | ROE 28%/...             |      |
...
```

实现:调 `industry_screener.screen_industry(ind, type, top_n=7)`,渲染 DataFrame。

**一键操作按钮**(每行右侧):
- 🌟 加入 L3 自选 — 写 companies.csv 末尾(不立即抓数,提示用户后续手动跑 lixinger pipeline)
- 📊 跳转大师 Tab — 设置 `st.session_state["selected_company"] = ticker` + Hint 用户切到林奇/格雷厄姆 Tab(无法直接切,但 sidebar selectbox 会跟随)

##### C 区 · 推荐 ETF Top 3(F3)
```
| Code   | Name       | Theme | 1y涨跌  | 流动性 | 推荐理由              |
| 512690 | 酒ETF      | 主题  | +18%    | 92%   | 白酒大消费综合曝光     |
| 159843 | 食品ETF    | 主题  | +12%    | 76%   | 必选消费防御          |
| ...    | ...        | ...   | ...     | ...   | ...                  |
```

实现:调 `etf_recommender.recommend(ind, top_n=3)`,渲染 + 选择建议 caption(主题 vs 龙头 vs 红利,目标配置区间)。

下方加 ETF 价格归一化叠加图(plotly,各只 ETF 1y 走势归一到 100 起步),复用 [.tools/dashboard/tabs/company.py](../../.tools/dashboard/tabs/company.py) 的 ETF 叠加风格(memory project_etf_peers_overlay)。

##### D 区 · 行业知识 + 周期特性(F4)
```
📖 行业知识(从 03_macro/02_行业对标数据/01_白酒.md 加载)

(渲染整篇 md;若超 30 行用 expander 收起)

🔍 关键观察指标
- 飞天茅台批价
- 渠道库存周转
- 消费税政策
- 春节/中秋销售

📚 相关方法论
- [林奇 stalwart 估值口径](../../01_knowledge/03_投资策略与选股/02_彼得林奇投资法/02_稳健增长型_ABCD评估.md)
- [格雷厄姆防御型]
```

实现:`Path(industry_master.yaml.industries[name].knowledge_md).read_text()` → `st.markdown` 渲染。

#### sidebar 编辑入口(G2)

在 sidebar 末尾(不影响现有 search_bar 和 selectbox)加 expander「⚙️ 编辑聚焦行业」:
- 显示当前 8 行业列表(yaml 内容)
- streamlit form 提供:
  - 多选(从 industry_master.yaml.industries 全部 SW L2 中选)
  - top_n / market_cap_min 调节
  - 「💾 保存」按钮 → 写回 `.config/focus_industries.yaml`
- 保存后 `st.toast("已更新")` + `st.rerun()`

---

### 2. `app.py` 接入

```python
PAGE_INDUSTRY_FOCUS = "🏭 行业分析"

PAGES = [
    ...,  # 现有
    PAGE_INDUSTRY_FOCUS,  # 加在 PAGE_MUNGER 之后,作为新增大模块
]

# render 调度
if page == PAGE_INDUSTRY_FOCUS:
    from tabs.industry_focus import render as render_industry_focus
    render_industry_focus()
```

---

### 3. 测试 `.tools/dashboard/test_industry_focus_tab.py`(8-12 项)

```python
from streamlit.testing.v1 import AppTest

def test_app_default_loads():
    at = AppTest.from_file(".tools/dashboard/app.py").run()
    assert not at.exception

def test_industry_focus_tab_renders():
    at = AppTest.from_file(".tools/dashboard/app.py")
    at.session_state["nav_page"] = "🏭 行业分析"  # 或对应 sidebar 触发
    at.run()
    assert not at.exception
    # 关键词命中
    body = "".join([str(m.value) for m in at.markdown])
    assert any(k in body for k in ["白酒","股份制银行","保险","化学制药"])

def test_4_zones_present():
    """4 区 banner 命中"""
    ...

# ... 5-8 项扩展(banner / 卡 / sidebar 编辑等)
```

---

## 🛑 文件边界

- `.tools/dashboard/tabs/industry_focus.py`(新建)
- `.tools/dashboard/app.py`(加 PAGE_INDUSTRY_FOCUS + sidebar 编辑入口)
- `.tools/dashboard/test_industry_focus_tab.py`(新建)

**不动**:任何引擎 .py / 任何 yaml / 任何其他 Tab

---

## ✅ 完成判定

```bash
cd /Users/gongyong/Desktop/Keyi/preson && source .venv/bin/activate

# AppTest 离线 + headless 双验
streamlit run .tools/dashboard/app.py --server.headless true --server.port 8520 &
sleep 8
curl -s http://localhost:8520/healthz && echo " OK"
kill %1

pytest .tools/dashboard/test_industry_focus_tab.py -v
```

- AppTest 默认页 0 异常
- 切到 「🏭 行业分析」页 0 异常,8 行业卡片全渲染
- 行业卡 4 区 A/B/C/D 全展示
- sidebar 「⚙️ 编辑聚焦行业」expander 可展开 + 保存按钮可点击
- 顶部 banner 8 行业速览渲染

---

## 📚 参考

- [README.md 接口契约 + 全局架构](README.md)
- 依赖产出(必须就绪):
  - `.config/industry_master.yaml`(01)
  - `.tools/rules/industry_etf_mapping.yaml`(01)
  - `03_macro/02_行业对标数据/0[1-8]_*.md`(01)
  - `.config/focus_industries.yaml`(03)
  - `.tools/rules/industry_type_map.yaml`(03)
  - `industry_percentile_engine.compute`(02)
  - `industry_cycle_engine.diagnose`(04)
  - `etf_recommender.recommend`(05)
  - `industry_screener.screen_industry / screen_all_focus`(03)
- 已有 Tab 风格参考:[tabs/gold_analysis.py](../../.tools/dashboard/tabs/gold_analysis.py)(banner + sub-tab 模式) / [tabs/munger_analysis.py](../../.tools/dashboard/tabs/munger_analysis.py)(紫色系 banner)
- ETF 叠加图风格:[tabs/company.py](../../.tools/dashboard/tabs/company.py)(M5 ETF 行业对标已落地)

---

## ⚠️ 已知坑

- 引擎可能返回 None(数据未抓 / 行业无数据),UI 全部要降级显示("暂无数据"),不要崩
- `screen_all_focus` 首次跑可能 30s+(8 行业 × 评分),用 `@st.cache_data(ttl=3600)` 包
- ETF 价格归一化图,要确保各只 ETF 起始日对齐(取最晚的起始日开始 normalize)
- 加自选按钮写 companies.csv 时,**只 append 不覆盖**,要 backup .bak,提示用户后续手动跑 lixinger
- 跳转大师 Tab:streamlit 不支持代码切 page,只能 `st.session_state["selected_company"] = ticker`(sidebar selectbox 会跟随);`st.toast("已切换到该公司,请点击左侧林奇 Tab")`
- sidebar 编辑入口写 yaml 时,保留 industry_master.yaml 的 type 字段同步(从 industry_master.industries[name].type 抄过来)
- AppTest 切 page 用 `at.session_state["__page__"] = ...` 不一定生效,可能需要模拟 sidebar radio 点击;参考已有 `test_app.py` / `test_munger_tab.py` 的写法
- 紫色已被芒格用,黄金用金;**「🏭 行业分析」用绿色系 banner**(参考森林 / 工厂)
