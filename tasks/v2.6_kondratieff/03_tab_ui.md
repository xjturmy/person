---
name: 03_tab_ui · 康波配置 Tab UI
priority: Wave 2(依赖 01 + 02,加分依赖 04)
estimate: ~3-4h
---

# 任务包 03 · 「📐 康波配置」Tab UI

> 写 `.tools/dashboard/tabs/kondratieff.py`(主 UI)+ `app.py` 接入 + 测试,把 01 数据 + 02 排序拼成完整 Tab。

---

## 📦 交付物

### 1. `.tools/dashboard/tabs/kondratieff.py`(~400-500 行)

#### 顶部 banner(金棕色 `#a16207 → #ca8a04`)

```
┌─ 当前康波位置:萧条期中后段 ────────────────────────┐
│ 配置目标:防御 65-75% / 进攻 25-35% / 过渡 0-5%   │
│ ── 实时信号(只读,不联动判定)──                  │
│ 实际利率 +1.63% (87 分位) / CPI -0.3% / M2 8.2%   │
│ 美元/人民币 7.12 / 10Y 国债 1.74%                 │
└────────────────────────────────────────────────────┘
```

实现:`from kondratieff_loader import load_config, get_phase_signals`,5 列 metric 卡。

#### 三层组合(垂直布局,折叠式)

每层一个标题块 + 该层全部行业 expander 网格(2 列):

```python
st.markdown("## 🛡️ 防御层(目标 65-75%)")
cols = st.columns(2)
for i, ind in enumerate(cfg.defensive):
    with cols[i % 2]:
        _render_industry_card(ind)
```

#### 行业卡(每行业一张)

默认收起,展开后内容:

```
┌─ 🛡️ 白酒 · 防御 · 10-15% · 稳定现金流 + 抗通胀 ──┐
│                                                  │
│ 📊 同行业 3 只 ETF 横评                          │
│ ┌────┬────┬────┬─────┬─────┬───────┬───────┐     │
│ │代码│名称│主题│1y涨跌│流动性│费率★ │规模★ │     │  ★ 阶段 2 后填
│ │512690│酒ETF│主题│-19% │73   │0.55%│120亿│Top1│
│ │159843│食饮│主题│-11% │1    │0.55%│25亿 │    │
│ │159736│消费│主题│-9%  │13   │0.50%│45亿 │    │
│ └────┴────┴────┴─────┴─────┴───────┴───────┘     │
│                                                  │
│ 💡 推荐:酒ETF(512690)— 流动性优 + 主题代表    │
│                                                  │
│ 📈 1y 归一化叠加图(三只走势对比)             │
│                                                  │
│ 📋 选择建议(主题 vs 龙头 vs 红利)            │
│ • 主题型:覆盖广,适合不知道选哪只龙头的用户    │
│ • 龙头型:更集中,在结构性行情中弹性大          │
│ • 红利型:股息高,适合收息配置                  │
└──────────────────────────────────────────────────┘
```

#### sidebar 编辑入口(可选,~30min)

「⚙️ 调整 layer 配置区间」expander — 临时调 target_pct,不写回 yaml(纯展示用 session_state)。

阶段 1 可不做,留 v2.7 加。

---

### 2. `app.py` 接入

```python
PAGE_KONDRATIEFF = "📐 康波配置"

PAGES = [..., PAGE_INDUSTRY, PAGE_KONDRATIEFF, PAGE_DC, PAGE_CLAUDE]
# 挂在 PAGE_INDUSTRY 之后(自顶向下视角的更高层)

if page == PAGE_KONDRATIEFF:
    try:
        from tabs import kondratieff as _k_mod
        _k_mod.render()
    except Exception as _e:
        st.error(f"康波配置加载失败:{_e}")
        import traceback as _tb
        st.caption(_tb.format_exc())
```

---

### 3. v2.5 行业 Tab C 区扩 2 列(顺手做)

阶段 2 跑完(04 任务包)后,etf.duckdb 有 fee/size 字段,在 industry_focus.py C 区表格加:
- "费率"(`fee_total`)
- "规模(亿)"(`fund_size`)

```python
# tabs/industry_focus.py 内修改 etf_df DataFrame 构造
etf_df = pd.DataFrame([{
    "代码": c["code"],
    "名称": c["name"],
    "主题": c["theme"],
    "1y 涨跌": ...,
    "流动性分位": ...,
    "费率": f"{c.get('fee_total'):.2%}" if c.get('fee_total') else "—",  # 新
    "规模(亿)": f"{c.get('fund_size'):.1f}" if c.get('fund_size') else "—",  # 新
    "层级": ...,
    "推荐理由": ...,
} for c in etfs])
```

同步 etf_recommender.ETFCandidate dataclass 加 `fee_total / fund_size` 字段;`recommend()` 内 SQL 加这两列。

---

### 4. 测试 `.tools/dashboard/test_kondratieff_tab.py`(10-15 项)

```python
def test_module_imports():
    from tabs import kondratieff
    assert hasattr(kondratieff, "render")

def test_render_helpers_exist():
    from tabs import kondratieff
    for name in ["_render_top_banner", "_render_industry_card",
                 "_render_etf_compare_table", "_render_etf_overlay"]:
        assert hasattr(kondratieff, name)

def test_app_default_loads():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(".tools/dashboard/app.py").run(timeout=60)
    assert not at.exception

def test_kondratieff_page_renders():
    """切到「📐 康波配置」页 0 异常."""
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(".tools/dashboard/app.py")
    at.session_state["page"] = "📐 康波配置"
    at.run(timeout=120)
    assert not at.exception

def test_loader_integration():
    """01 + 02 + 03 端到端"""
    import sys; sys.path.insert(0, ".tools/dashboard")
    from kondratieff_loader import load_config
    from etf_compare import pick_top_etf
    cfg = load_config()
    for ind in cfg.all_industries:
        top = pick_top_etf(ind)
        # 不 raise + Top 1 在 yaml 列表中(数据全 None 时仍返回第一只)
        assert top is None or top.code in [e.code for e in ind.etfs]

# ... 5-8 项扩展(banner / 行业卡 / overlay / sidebar)
```

---

## 🛑 文件边界

只能写:
- `.tools/dashboard/tabs/kondratieff.py`(新建)
- `.tools/dashboard/app.py`(加 PAGE_KONDRATIEFF + render 调度)
- `.tools/dashboard/test_kondratieff_tab.py`(新建)
- `.tools/dashboard/etf_recommender.py` + `tabs/industry_focus.py`(顺手加 fee/size 列,**仅 append 字段不改逻辑**)

---

## ✅ 完成判定

```bash
cd /Users/gongyong/Desktop/Keyi/preson && source .venv/bin/activate

# 测试
pytest .tools/dashboard/test_kondratieff_tab.py -v

# Streamlit headless
nohup streamlit run .tools/dashboard/app.py --server.port 8501 --server.headless true > /tmp/k.log 2>&1 &
sleep 6
curl -s http://localhost:8501/healthz
pkill -f "streamlit run"

# 既有测试不破坏
pytest .tools/dashboard/test_industry_focus_tab.py 2>&1 | tail -2
```

---

## 📚 参考

- [README.md 接口契约 A/B/D](README.md)
- 依赖产出(必须就绪):01 + 02 完整;04 加分(没有也能跑 MVP,只是费率/规模列展示"—")
- UI 风格参考:[tabs/industry_focus.py](../../.tools/dashboard/tabs/industry_focus.py)(刚交付的 v2.5,行业卡 4 区模式)
- banner 风格参考:[tabs/gold_analysis.py](../../.tools/dashboard/tabs/gold_analysis.py)(渐变色 + metric 行)

---

## ⚠️ 已知坑

- 同行业 N 只 ETF 起始日不齐 → 归一化图取最晚起始日开始 normalize
- 三层 19 行业一次性渲染可能慢 → expander 默认收起,数据按需加载(用 expander 内 cache)
- fee/size 列阶段 1 全部 "—",UI 上要明确标"待 04 任务包跑完"
- AppTest 切 page 用 `at.session_state["page"]` 不一定生效;需观察 sidebar radio 实际 key
- 颜色与现有 Tab 别撞:林奇绿 / 格雷厄姆蓝 / 黄金金 / 芒格紫 / 行业森林绿 / **康波金棕**
