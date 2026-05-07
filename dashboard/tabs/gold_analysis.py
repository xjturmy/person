"""D2 Phase 2.3 · 黄金分析法 Tab(对照 lynch / graham 模式,但**资产类**不针对单家公司)。

5 sub-tabs:
  ① 三大范式投票  → 5+5+5=15 信号矩阵 + 投票结果(Phase 2.4 引擎前用静态判定)
  ② 实际利率定价  → 双轴时序图 + 散点图 + 四象限决策
  ③ 周期定位      → 康波四阶段时间轴 + 历史萧条期黄金回报对照
  ④ 关键比率      → 金油 / 金银 / 实际利率 / SPDR 4 张时序 + 分位仪表盘
  ⑤ ETF 选择      → 4 只 ETF 对比 + 归一化叠加 + 推荐评分

设计原则:
- 顶部 banner 主色:黄金渐变(对照林奇绿 / 格雷厄姆蓝)
- 复用 gold_data.py 纯数据 + Phase 2.4 引擎接入位预留(`paradigm_engine.py` 待建)
- 与 lynch/graham 一致的 render 签名(忽略 selected/year/folder_to_ticker)

Author: Claude (D2 Phase 2.3, 2026-05-07)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
KNOWLEDGE_BASE = ROOT / "01_knowledge" / "03_投资策略与选股" / "12_黄金投资法"

if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from gold_data import (  # noqa: E402
    Snapshot, ParadigmVote,
    latest_snapshot, static_paradigm_vote, fill_dynamic_signals,
    load_indicator, load_ratios, load_percentiles,
    load_etf_master, load_etf_prices,
)

# Phase 2.4 yaml 投票引擎(可用时优先)
try:
    from paradigm_engine import vote as _engine_vote, ParadigmVoteV1  # noqa: E402
    _ENGINE_AVAILABLE = True
except Exception:
    _ENGINE_AVAILABLE = False

# 黄金渐变 banner
BANNER_GRADIENT = "linear-gradient(90deg, #b45309 0%, #f59e0b 50%, #fbbf24 100%)"


# ─── 缓存层(随 db_mtime 失效)──────────────────────────────────────────


@st.cache_data(ttl=600, show_spinner=False)
def _snapshot_cached(db_mtime: float) -> dict | None:
    """返回 dict 而非 dataclass(streamlit cache 不爱 dataclass)。"""
    try:
        return latest_snapshot().to_dict()
    except Exception as e:
        return {"_error": str(e)}


_VOTE_CACHE_VERSION = "v2.4_engine"  # 升版强制 cache 失效(每次切换 engine/static 行为时 +1)


@st.cache_data(ttl=600, show_spinner=False)
def _vote_cached(db_mtime: float, cache_version: str = _VOTE_CACHE_VERSION) -> dict:
    """yaml 引擎投票(verified=True);失败回落 static。

    cache_version 是显式 cache key 一部分 — 切换 engine/static 行为时改它,
    避免 streamlit 复用旧 dict(常被 ttl 复用)。
    """
    if _ENGINE_AVAILABLE:
        try:
            return _engine_vote().to_dict()
        except Exception as e:
            # 引擎失败 → 回落 static
            snap = latest_snapshot()
            d = static_paradigm_vote(snap).to_dict()
            d["_engine_error"] = str(e)
            return d
    snap = latest_snapshot()
    return static_paradigm_vote(snap).to_dict()


@st.cache_data(ttl=600, show_spinner=False)
def _ratios_cached(db_mtime: float, days: int | None = None) -> pd.DataFrame:
    return load_ratios(days=days)


@st.cache_data(ttl=600, show_spinner=False)
def _indicator_cached(indicator: str, db_mtime: float, days: int | None = None) -> pd.DataFrame:
    return load_indicator(indicator, days=days)


@st.cache_data(ttl=600, show_spinner=False)
def _percentiles_cached(db_mtime: float) -> pd.DataFrame:
    return load_percentiles()


@st.cache_data(ttl=600, show_spinner=False)
def _etf_master_cached(db_mtime: float) -> pd.DataFrame:
    return load_etf_master()


@st.cache_data(ttl=600, show_spinner=False)
def _etf_prices_cached(db_mtime: float, days: int = 1825) -> pd.DataFrame:
    return load_etf_prices(days=days)


# ─── Banner ─────────────────────────────────────────────────────────────


def _render_banner(snap: Snapshot, vote) -> None:
    """vote 可以是 ParadigmVote(static)/ ParadigmVoteV1(engine)/ SimpleNamespace(dict→ns)。"""
    rr_str = f"{snap.real_rate:+.2f}%" if snap.real_rate is not None else "—"
    rr_pct = f"{snap.real_rate_pct_10y * 100:.0f}% 分位(10y)" if snap.real_rate_pct_10y is not None else "分位 —"
    go_str = f"{snap.gold_oil:.1f}" if snap.gold_oil is not None else "—"
    gs_str = f"{snap.gold_silver:.1f}" if snap.gold_silver is not None else "—"
    pct_lo, pct_hi = vote.suggested_pct
    as_of_str = snap.as_of.strftime("%Y-%m-%d") if snap.as_of else "—"

    st.markdown(
        f'<div style="padding:14px 18px;border-radius:10px;'
        f'background:{BANNER_GRADIENT};color:white;margin:8px 0">'
        f'<span style="font-size:26px">🥇</span> '
        f'<span style="font-size:21px;font-weight:700;margin-left:8px">'
        f'当前主导身份:{vote.dominant_label}</span>'
        f'<span style="margin-left:14px;background:rgba(255,255,255,0.25);'
        f'padding:3px 10px;border-radius:10px;font-size:13px">'
        f'范式投票 {vote.p1_count}-{vote.p2_count}-{vote.p3_count} '
        f'({"3/3 全开" if (vote.p1_active and vote.p2_active and vote.p3_active) else f"{sum([vote.p1_active, vote.p2_active, vote.p3_active])}/3 激活"})</span>'
        f'<span style="margin-left:14px;background:rgba(255,255,255,0.18);'
        f'padding:3px 10px;border-radius:10px;font-size:13px">'
        f'⏱ {as_of_str}</span>'
        f'<div style="font-size:13px;opacity:0.92;margin-top:6px">'
        f'📍 实际利率 <b>{rr_str}</b> · {rr_pct}'
        f' &nbsp;&nbsp;|&nbsp;&nbsp; 金油比 <b>{go_str}</b>'
        f' &nbsp;&nbsp;|&nbsp;&nbsp; 金银比 <b>{gs_str}</b>(SGE 国内口径)</div>'
        f'<div style="font-size:14px;font-weight:600;margin-top:6px">'
        f'💡 配置建议:权益类组合中 黄金占 <b>{pct_lo:.0f}-{pct_hi:.0f}%</b>'
        f'(高风险偏好可至 38%)</div>'
        f'<div style="font-size:11px;opacity:0.7;margin-top:4px">'
        f'{"✅ 来源:yaml 投票引擎(verified=True)" if vote.verified else "⚠️ 来源:静态判定(Phase 2.4 引擎未启用)"}'
        f' · {getattr(vote, "source", "—")}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── ① 三大范式投票 ─────────────────────────────────────────────────────


def _render_paradigm(snap: Snapshot, vote) -> None:
    st.markdown("### ① 三大范式投票(15 信号矩阵)")
    st.caption(
        "📚 方法论:[01_三大范式判定.md]"
        f"({KNOWLEDGE_BASE}/01_三大范式判定.md)"
        " · 鲁政委《保卫财富》框架"
    )

    # 引擎可用 → 用引擎信号(dict 列表);否则回落 static
    engine_signals = getattr(vote, "signals", None)
    if engine_signals:
        # 引擎结果格式:list[dict] — 适配为 UI 期望格式
        # paradigm 字段(经济金融 / 技术革命 / 大国博弈)从 paradigm_label 提取
        p_map = {"economic_financial": "经济金融",
                 "tech_revolution": "技术革命",
                 "great_power_struggle": "大国博弈"}
        signals = []
        for sig in engine_signals:
            if isinstance(sig, dict):
                p_zh = p_map.get(sig.get("paradigm", ""), sig.get("paradigm", ""))
                signals.append({
                    "id": sig["signal_id"],
                    "p": p_zh,
                    "name": sig["name"],
                    "current": str(sig.get("current_value")) if sig.get("current_value") is not None else "—",
                    "threshold": sig.get("threshold_str", ""),
                    "active": bool(sig.get("active", False)),
                    "source": sig.get("source", "—"),
                })
    else:
        signals = fill_dynamic_signals(snap)
    by_paradigm = {"经济金融": [], "技术革命": [], "大国博弈": []}
    for sig in signals:
        by_paradigm.setdefault(sig.get("p", ""), []).append(sig)

    col_a, col_b, col_c = st.columns(3)
    paradigm_meta = [
        ("经济金融", "🟢 范式一", "短期(月-季)", vote.p1_count, vote.p1_active, col_a),
        ("技术革命", "🟡 范式二", "中期(年-十年)", vote.p2_count, vote.p2_active, col_b),
        ("大国博弈", "🔴 范式三", "长期(十年-世代)", vote.p3_count, vote.p3_active, col_c),
    ]

    for p_name, p_label, p_horizon, count, active, col in paradigm_meta:
        with col:
            badge = "✅ 激活" if active else "⚪ 钝化"
            color = "#10b981" if active else "#9ca3af"
            st.markdown(
                f'<div style="padding:10px 12px;border-radius:8px;'
                f'border-left:4px solid {color};background:rgba(0,0,0,0.04);margin-bottom:6px">'
                f'<div style="font-size:13px;color:#666">{p_label} · {p_horizon}</div>'
                f'<div style="font-size:18px;font-weight:700;margin-top:4px">{p_name}</div>'
                f'<div style="font-size:14px;margin-top:4px">{badge} · {count}/5 信号</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            for sig in by_paradigm[p_name]:
                emoji = "✅" if sig["active"] else "⚪"
                st.markdown(
                    f'<div style="padding:6px 8px;font-size:12px;line-height:1.5">'
                    f'{emoji} <b>{sig["name"]}</b><br/>'
                    f'<span style="color:#888">阈值:{sig["threshold"]}</span><br/>'
                    f'<span style="color:#444">当前:{sig["current"]}</span><br/>'
                    f'<span style="color:#aaa;font-size:11px">来源:{sig["source"]}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    st.divider()
    st.markdown("#### 投票判定 → 主导身份 → 配置区间")
    pct_lo, pct_hi = vote.suggested_pct
    actives = sum([vote.p1_active, vote.p2_active, vote.p3_active])
    st.markdown(f"""
- **范式一(经济金融)**:{vote.p1_count}/5 信号激活 → {"✅ 激活" if vote.p1_active else "⚪ 钝化"}
- **范式二(技术革命)**:{vote.p2_count}/5 信号激活 → {"✅ 激活" if vote.p2_active else "⚪ 钝化"}
- **范式三(大国博弈)**:{vote.p3_count}/5 信号激活 → {"✅ 激活" if vote.p3_active else "⚪ 钝化"}

**主导身份**:{vote.dominant_label}({actives}/3 范式激活)
**建议黄金占比**:{pct_lo:.0f}-{pct_hi:.0f}%(高风险偏好客户可至 38%,鲁政委震撼结论)
""")
    if vote.verified:
        st.success(
            f"✅ 当前判定来源:**yaml 投票引擎**(`{getattr(vote, 'source', '—')}`)"
            "。yaml 阈值见 [.tools/rules/gold_paradigm.yaml](#)。"
            " 数据真实接入度:实际利率 / SPDR(若手填)/ 康波 / 地缘 / 央行购金 / 美元储备 / 全部 yaml manual_const。"
        )
        if hasattr(vote, "note") and vote.note:
            st.caption(f"💡 {vote.note}")
    else:
        st.info(
            "⚠️ 当前判定来源:**静态判定**(yaml 引擎未启用,可能 yaml 路径错或 PyYAML 缺)。"
            " 待接入项:VIX 实时数据 / 美股科技-金价相关性 / 美国生产力 YoY。"
        )


# ─── ② 实际利率定价 ─────────────────────────────────────────────────────


def _render_real_rate(snap: Snapshot, db_mtime: float) -> None:
    st.markdown("### ② 实际利率定价模型")
    st.caption(
        "📚 方法论:[02_实际利率定价模型.md]"
        f"({KNOWLEDGE_BASE}/02_实际利率定价模型.md)"
        " · 实际利率 = 名义利率 - 通胀预期"
    )

    # 三件套 metric
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        rr = f"{snap.real_rate:+.2f}%" if snap.real_rate is not None else "—"
        st.metric("实际利率(US 10Y - CPI YoY)", rr,
                  help="< 0 利好黄金 · > 0 压制黄金(2022 后失效期需查范式二/三)")
    with col_b:
        n10y = f"{snap.nominal_10y:.2f}%" if snap.nominal_10y is not None else "—"
        st.metric("名义利率(US 10Y)", n10y)
    with col_c:
        cpi = f"{snap.cpi_yoy:.2f}%" if snap.cpi_yoy is not None else "—"
        st.metric("CPI YoY", cpi)
    with col_d:
        gusd = f"${snap.gold_usd:.0f}/oz" if snap.gold_usd is not None else "—"
        st.metric("USD 金价(派生)", gusd, help="沪金 × USDCNY × 31.1g/oz")

    # 双轴时序图
    st.markdown("#### 实际利率 vs USD 金价(20 年视角)")
    rates = _ratios_cached(db_mtime, days=365 * 20)
    gold_usd = _indicator_cached("GOLD_USD_DERIVED", db_mtime, days=365 * 20)

    if not rates.empty and not gold_usd.empty:
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            rates = rates.dropna(subset=["real_rate"])
            gold_usd = gold_usd.dropna()

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(
                go.Scatter(x=gold_usd["date"], y=gold_usd["value"],
                           name="USD 金价", line=dict(color="#fbbf24", width=2)),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(x=rates["date"], y=rates["real_rate"],
                           name="实际利率(右轴 反向)",
                           line=dict(color="#1e3a8a", width=2, dash="dot")),
                secondary_y=True,
            )
            fig.update_layout(
                hovermode="x unified", height=400,
                margin=dict(l=20, r=20, t=20, b=20),
                legend=dict(orientation="h", y=1.05),
            )
            fig.update_yaxes(title="USD/oz", secondary_y=False)
            fig.update_yaxes(title="实际利率 %", secondary_y=True, autorange="reversed")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.warning(f"图表渲染失败:{e}")
    else:
        st.info("数据不足(实际利率或 USD 金价缺失)")

    # 四象限决策
    with st.expander("💡 四象限决策矩阵(实际利率 × 通胀)", expanded=False):
        st.markdown("""
| 象限 | 实际利率 | 通胀 | 黄金强度 | 配置 | 当前对照 |
|------|---------|------|---------|------|---------|
| I 通胀繁荣 | < 0 | 高 | ⭐⭐⭐⭐ | 15-20% | — |
| II 滞胀型 | < 0 | 高 | ⭐⭐⭐⭐⭐ | 20-25% | — |
| III 通缩衰退 | > 0 | 低 | ⭐⭐⭐ | 5-10% | — |
| **IV 通胀回落** | **> 0** | **正常** | **⭐⭐** | **0-5%(范式二/三激活时仍可持有)** | ✅ **当前位置** |

**当前(2026-05)**:实际利率 +1.63% / CPI YoY 2.73% → **象限 IV**
但范式二/三仍激活 → 黄金不应大幅减仓,维持战略配置
""")


# ─── ③ 周期定位(康波四阶段)──────────────────────────────────────────


def _render_cycle() -> None:
    st.markdown("### ③ 周期定位(康波四阶段)")
    st.caption(
        "📚 方法论:[03_配置比例量化.md]"
        f"({KNOWLEDGE_BASE}/03_配置比例量化.md)"
        " · 周金涛康波周期"
    )

    st.markdown("""
```text
┌─────────────────────────────────────────────────────────────────┐
│           康波四阶段:股票/商品/现金/黄金的轮动               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   回升期        繁荣期         衰退期         萧条期(当前)    │
│  2030/35-?    1991-2004    2004-2020       2020-2030/35        │
│      │            │              │              │              │
│      ▼            ▼              ▼              ▼              │
│   ┌──────┐    ┌──────┐      ┌──────┐      ┌──────────┐      │
│   │ 股票 │───►│ 商品 │─────►│ 现金 │─────►│   黄金   │      │
│   │ 优先 │    │ 优先 │      │ 优先 │      │   优先   │      │
│   └──────┘    └──────┘      └──────┘      └──────────┘      │
│      ✅           ❌            ⚠️            ⭐⭐⭐         │
│   黄金一般    黄金较差      黄金中性       黄金优异          │
│                                                                  │
│   配置:5-10%   0-5%          5-10%          15-25% ← 当前    │
│                                                                  │
│   【当前定位】第五次康波萧条期中后段(2020-2030/35)            │
└─────────────────────────────────────────────────────────────────┘
```
""")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("当前周期阶段", "第五次康波萧条期",
                  help="周金涛预测 2030-2035 切回升期")
    with col_b:
        st.metric("黄金战略权重", "15-25%",
                  help="萧条期对黄金最有利")
    with col_c:
        st.metric("预计切换时间", "2030-2035",
                  help="AI 商用化 + 新动能爆发 = 切换标志")

    st.markdown("#### 历史四次萧条期黄金回报对照")
    historical = pd.DataFrame({
        "康波": ["第一次", "第二次", "第三次", "第四次", "第五次(当前)"],
        "萧条期": ["1815-1849", "1873-1896", "1929-1949", "1973-1982", "2020-2030/35?"],
        "黄金表现": ["保值", "缓慢上行", "金本位崩溃后大涨", "+1300% (1971-1980)", "进行中"],
        "驱动因素": [
            "拿破仑战争结束 / 工业初期",
            "长萧条 / 银本位危机",
            "大萧条 / 二战 / 布雷顿森林",
            "石油危机 / 滞胀 / 美元脱金",
            "AI 革命 / 去美元化 / 地缘冲突",
        ],
    })
    st.dataframe(historical, use_container_width=True, hide_index=True)

    with st.expander("💡 配置比例公式(三层联动)", expanded=False):
        st.markdown("""
**第一步**:康波阶段 → 战略基础区间
- 萧条期 15-25% / 衰退期 5-10% / 回升期 5-10% / 繁荣期 0-5%

**第二步**:风险偏好乘数
- 低风险(股 < 10%):基础 × 0.1 → 黄金 1-2%
- 中风险(股 20-40%):基础 × 0.7 → 黄金 14-17%
- 高风险(股 ≥ 50%):基础 × 1.6 → 黄金 32-40% ⭐(鲁政委定律)

**第三步**:战术微调
- 三范式全开 + 实际利率 < -1%:+5%
- 钝化 + 实际利率 > +2%:-5%

**示例**(高风险偏好,2026-05):
- 战略基础 20%(萧条期中位)× 1.6 = 32% + 战术 +5% = **37%** ≈ 鲁政委 38% 上限
""")


# ─── ④ 关键比率(4 张时序 + 分位仪表盘)──────────────────────────────


def _render_ratios(snap: Snapshot, db_mtime: float) -> None:
    st.markdown("### ④ 关键比率与分位仪表盘")
    st.caption(
        "📚 方法论:[05_关键指标速查.md]"
        f"({KNOWLEDGE_BASE}/05_关键指标速查.md)"
    )

    # 顶部 4 列 metric
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        rr = f"{snap.real_rate:+.2f}%" if snap.real_rate is not None else "—"
        rrp = f"{snap.real_rate_pct_10y*100:.0f}% 分位" if snap.real_rate_pct_10y is not None else "—"
        st.metric("① 实际利率", rr, rrp)
    with col_b:
        go_v = f"{snap.gold_oil:.1f}" if snap.gold_oil is not None else "—"
        gop = f"{snap.gold_oil_pct_10y*100:.0f}% 分位" if snap.gold_oil_pct_10y is not None else "—"
        st.metric("② 金油比", go_v, gop)
    with col_c:
        gs_v = f"{snap.gold_silver:.1f}" if snap.gold_silver is not None else "—"
        gsp = f"{snap.gold_silver_pct_10y*100:.0f}% 分位" if snap.gold_silver_pct_10y is not None else "—"
        st.metric("③ 金银比(SGE)", gs_v, gsp,
                  help="SGE 国内口径,与 LBMA 国际(~88)不可直接对比")
    with col_d:
        spdr = f"{snap.spdr_holdings:.0f} 吨" if snap.spdr_holdings is not None else "未启用"
        st.metric("④ SPDR 持仓", spdr,
                  help="jin10.com 中国 IP 卡 → 走 .config/spdr_holdings_manual.csv 手填")

    # 4 张时序图
    st.markdown("#### 历史时序(10 年)")
    ratios = _ratios_cached(db_mtime, days=365 * 10)

    if not ratios.empty:
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            fig = make_subplots(rows=2, cols=2,
                                subplot_titles=("实际利率(%)", "金油比",
                                                "金银比(SGE)", "(SPDR 持仓 — 数据待接入)"))

            d = ratios["date"]
            for r, c, ycol, color in [
                (1, 1, "real_rate", "#1e3a8a"),
                (1, 2, "gold_oil",  "#b45309"),
                (2, 1, "gold_silver", "#dc2626"),
            ]:
                if ycol in ratios.columns:
                    yy = ratios[ycol]
                    fig.add_trace(
                        go.Scatter(x=d, y=yy, line=dict(color=color, width=2),
                                   showlegend=False),
                        row=r, col=c,
                    )

            # SPDR 占位(保留位置)
            spdr_df = _indicator_cached("SPDR_HOLDINGS", db_mtime, days=365 * 10)
            if not spdr_df.empty:
                fig.add_trace(
                    go.Scatter(x=spdr_df["date"], y=spdr_df["value"],
                               line=dict(color="#fbbf24", width=2), showlegend=False),
                    row=2, col=2,
                )
                fig.layout.annotations[3].text = "SPDR 持仓(吨)"

            fig.update_layout(height=520, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.warning(f"图表渲染失败:{e}")

    # 分位仪表盘
    st.markdown("#### 分位仪表盘(metric × window)")
    pct_df = _percentiles_cached(db_mtime)
    if not pct_df.empty:
        # pivot 成 metric × window
        pivot = pct_df.pivot_table(
            index="metric", columns="window_label",
            values="percentile", aggfunc="first",
        )

        def _pct_color(v):
            """0(绿)-50(黄)-100(红)线性渐变,纯 CSS 不依赖 matplotlib。"""
            if pd.isna(v):
                return ""
            v = max(0.0, min(1.0, float(v)))
            # RdYlGn_r:0=#1a9850(绿)/ 0.5=#ffffbf(黄)/ 1=#d73027(红)
            if v <= 0.5:
                # 绿 → 黄
                t = v * 2
                r = int(26 + (255 - 26) * t)
                g = int(152 + (255 - 152) * t)
                b = int(80 + (191 - 80) * t)
            else:
                # 黄 → 红
                t = (v - 0.5) * 2
                r = int(255 + (215 - 255) * t)
                g = int(255 + (48 - 255) * t)
                b = int(191 + (39 - 191) * t)
            return f"background-color: rgb({r},{g},{b}); color: #1a1a1a"

        st.dataframe(
            pivot.style.format("{:.1%}", na_rep="—").map(_pct_color),
            use_container_width=True,
        )
        st.caption("🟢 绿色 = 低分位(可能加仓机会)/ 🔴 红色 = 高分位(可能减仓信号)")
    else:
        st.info("分位数据未生成,先跑 `fetch_gold_ratios.py`")


# ─── ⑤ ETF 选择 ─────────────────────────────────────────────────────────


def _render_etf(db_mtime: float) -> None:
    st.markdown("### ⑤ 黄金 ETF 选择")
    st.caption(
        "📚 方法论:[04_黄金ETF选择.md]"
        f"({KNOWLEDGE_BASE}/04_黄金ETF选择.md)"
    )

    master = _etf_master_cached(db_mtime)
    if master.empty:
        st.warning("ETF master 未填,先跑 `fetch_gold_etf.py`")
        return

    # 4 列对比卡片
    cols = st.columns(len(master))
    for i, (_, etf) in enumerate(master.iterrows()):
        with cols[i]:
            highlight = "⭐ 推荐" if etf["etf_code"] == "518880" else ""
            st.markdown(
                f'<div style="padding:10px 12px;border-radius:8px;'
                f'border:1px solid #fbbf24;background:rgba(251,191,36,0.08);margin-bottom:6px">'
                f'<div style="font-size:11px;color:#888">{etf["exchange"]} · {etf["manager"]}</div>'
                f'<div style="font-size:16px;font-weight:700;margin-top:2px">{etf["etf_code"]}</div>'
                f'<div style="font-size:13px;margin-top:2px">{etf["etf_name"]}</div>'
                f'<div style="font-size:11px;color:#666;margin-top:6px">'
                f'费率 {etf["fee_rate"]:.2f}% / 跟踪 {etf["tracking"]}</div>'
                f'<div style="font-size:11px;color:#10b981;font-weight:600;margin-top:4px">{highlight}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # 归一化叠加图
    st.markdown("#### 归一化净值对比(3 年)")
    prices = _etf_prices_cached(db_mtime, days=365 * 3)
    if not prices.empty:
        try:
            import plotly.graph_objects as go

            fig = go.Figure()
            for code in master["etf_code"]:
                sub = prices[prices["etf_code"] == code].sort_values("date")
                if sub.empty:
                    continue
                base = sub["close"].iloc[0]
                fig.add_trace(go.Scatter(
                    x=sub["date"],
                    y=sub["close"] / base * 100,
                    mode="lines",
                    name=code,
                    line=dict(width=2),
                ))
            fig.update_layout(
                height=380, hovermode="x unified",
                margin=dict(l=20, r=20, t=20, b=20),
                yaxis_title="归一化净值(基期 = 100)",
                legend=dict(orientation="h", y=1.05),
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.warning(f"图表渲染失败:{e}")
    else:
        st.info("ETF 价格数据未填,先跑 `fetch_gold_etf.py`")

    with st.expander("💡 ETF 选择原则", expanded=False):
        st.markdown("""
**首选标的**:**华安黄金 ETF(518880)**
- 规模最大(~430 亿)→ 流动性最好 → 跟踪误差最小
- 上交所挂牌 → 国内券商均可交易
- 4 只费率均为 0.6%,**不在费率上选,而在流动性**

**工具组合(推荐)**:
- 70-80% **黄金 ETF(518880)** — 主仓 / 流动性 / 战术调整
- 10-20% **银行积存金** — 自动定投 / 强制储蓄
- 5-10% **实物金条** — 极端避险 / 长期 / 心理锚

**避坑提醒**:
- ❌ 黄金股(GDX/紫金矿业)— 短期受**大盘指数 > 金价**影响
- ❌ 黄金期货 / 期权 — 普通投资者爆仓概率 > 80%
- ❌ 银行纸黄金 — 费率比 ETF 高 5-10 倍
""")


# ─── 主入口 ─────────────────────────────────────────────────────────────


def render(companies: list[str] | None = None,
           selected: str | None = None,
           db_mtime: float = 0.0,
           decisions_db=None,
           folder_to_ticker_fn=None) -> None:
    """黄金分析法 Tab 入口。signature 与 lynch/graham 对齐,但黄金是资产类不针对单家公司。"""
    st.subheader("🥇 黄金分析法 · 三身份决策框架")

    # 顶部:刷新按钮(黄金没有公司选择)
    col_left, col_refresh = st.columns([5, 1])
    with col_left:
        st.caption(
            "📊 数据来源:沪金 SGE / 美国 10Y / CPI / WTI 油 / 4 只 ETF · "
            "理论:鲁政委《保卫财富》三大范式 + 周金涛康波"
        )
    with col_refresh:
        if st.button("🔄 刷新", key="gold_refresh", use_container_width=True):
            for cache_fn in (_snapshot_cached, _ratios_cached, _indicator_cached,
                             _percentiles_cached, _etf_master_cached, _etf_prices_cached):
                cache_fn.clear()
            st.rerun()

    # 加载 snapshot + 投票
    snap_dict = _snapshot_cached(db_mtime)
    if snap_dict is None or "_error" in (snap_dict or {}):
        err = snap_dict.get("_error") if snap_dict else "数据加载失败"
        st.error(f"⚠️ gold.duckdb 未就绪:{err}")
        st.info("请先跑 4 个 fetch 脚本:`fetch_gold_prices` / `fetch_real_rate` / `fetch_gold_etf` / `fetch_gold_ratios`")
        return

    snap = Snapshot(**snap_dict)

    # 投票:引擎优先,失败回落 static
    vote_dict = _vote_cached(db_mtime)
    # SimpleNamespace 适配:UI 用属性访问(.dominant_label / .suggested_pct 等)
    from types import SimpleNamespace
    # tuple 化 suggested_pct(yaml 出 list)
    if isinstance(vote_dict.get("suggested_pct"), list):
        vote_dict["suggested_pct"] = tuple(vote_dict["suggested_pct"])
    vote = SimpleNamespace(**vote_dict)

    # Banner
    _render_banner(snap, vote)

    # 5 sub-tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "① 三大范式投票",
        "② 实际利率定价",
        "③ 周期定位",
        "④ 关键比率",
        "⑤ ETF 选择",
    ])
    with tab1:
        _render_paradigm(snap, vote)
    with tab2:
        _render_real_rate(snap, db_mtime)
    with tab3:
        _render_cycle()
    with tab4:
        _render_ratios(snap, db_mtime)
    with tab5:
        _render_etf(db_mtime)


__all__ = ["render"]
