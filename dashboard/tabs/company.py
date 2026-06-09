"""Tab: 🏢 单公司详情(SWS 风格 Hero + 雪花图 + 6 子 Tab + 横向对比 + dash-03 大师矩阵/同行雷达)。

由 .tools/dashboard/app.py 在 page == PAGE_COMPANY 时调用 render()。
"""
from __future__ import annotations

from importlib.machinery import SourceFileLoader
from pathlib import Path

_THIS = Path(__file__).resolve().parents[0]


# ─── v2.7 持仓档案 + 合理价格区间 ────────────────────────────────────
def _load_fair_price_module():
    """懒加载 fair_price 模块,与本文件其它模块加载方式保持一致。"""
    return SourceFileLoader("fair_price", str(_THIS.parent / "fair_price.py")).load_module()


def _render_position_card(ticker: str, st) -> None:
    """渲染「📌 我的持仓」卡(仅持仓股) + 2 个 expander(价格算法 / 选择标准)。

    非持仓 ticker 整个不渲染,Hero 直接接雪花图。
    """
    if not ticker:
        return
    try:
        fp = _load_fair_price_module()
    except Exception:
        return

    portfolio = fp.load_portfolio()
    entry = portfolio.get(ticker)
    if entry is None:
        return  # 非持仓:零渲染

    rng = fp.compute_fair_range(ticker, entry.name)
    bg, txt = fp.verdict_color(rng.verdict_code)

    # ── 主卡(紧凑两行)──
    if rng.verified and rng.graham_number is not None:
        price_line = (
            f'💰 {fp.format_price(rng.low)} - {fp.format_price(rng.high)}'
            f'&nbsp;&nbsp;&nbsp;&nbsp;当前 {fp.format_price(rng.current_price)}'
            f'&nbsp;&nbsp;&nbsp;&nbsp;'
            f'<span class="position-badge" style="background:{bg};color:{txt};">'
            f'{rng.verdict_label} ({rng.deviation_pct:+.1f}%)</span>'
        )
    else:
        price_line = (
            f'💰 — Graham Number 不适用'
            f'&nbsp;&nbsp;&nbsp;&nbsp;'
            f'<span class="position-badge" style="background:{bg};color:{txt};">'
            f'{rng.verdict_label}</span>'
        )

    st.markdown(
        f'<div class="position-card">'
        f'  <div class="position-card-title">📌 我的持仓 · {entry.name} '
        f'<span class="position-card-school">[{entry.school}]</span></div>'
        f'  <div class="position-card-row">💭 {entry.rationale}</div>'
        f'  <div class="position-card-row">{price_line}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── expander 1:价格计算方法 ──
    with st.expander("📐 价格计算方法", expanded=False):
        if rng.verified:
            st.markdown(
                f"**方法**:Graham Number(本杰明·格雷厄姆,1973)  \n"
                f"**公式**:`合理价 = √(22.5 × EPS × BPS)`  \n"
                f"**22.5 系数** = 15(PE 上限)× 1.5(PB 上限)\n\n"
                f"**当前数据**(数据日期 {rng.as_of}):\n"
                f"- PE-TTM = `{rng.pe_ttm:.2f}`\n"
                f"- PB = `{rng.pb:.2f}`\n"
                f"- EPS-TTM(反推)= 真实股价 / PE = `{fp.format_price(rng.eps_ttm)}`\n"
                f"- BPS(反推)= 真实股价 / PB = `{fp.format_price(rng.bps)}`\n"
                f"- 市值 = `¥{rng.market_cap/1e8:,.0f} 亿`\n"
                f"- 总股本(净利润/EPS 反推)= `{rng.shares_outstanding/1e8:.2f} 亿股`\n"
                f"- 真实股价 = 市值 / 总股本 = `{fp.format_price(rng.current_price)}`\n\n"
                f"**Graham Number** = √(22.5 × {rng.eps_ttm:.2f} × {rng.bps:.2f}) "
                f"= **{fp.format_price(rng.graham_number)}**\n\n"
                f"**区间生成**(基于格雷厄姆 ±15% 合理波动):\n"
                f"- 合理价下沿 = Graham × 0.85 = `{fp.format_price(rng.low)}`\n"
                f"- 合理价上沿 = Graham × 1.15 = `{fp.format_price(rng.high)}`\n\n"
                f"**适用范围**:盈利稳定 + 净资产为正的非金融公司  \n"
                f"**数据源**:preson.duckdb(valuation 表 + growth 表)"
            )
        else:
            st.markdown(
                f"**Graham Number 不适用**:{rng.skip_reason}\n\n"
                f"**当前状态**:\n"
                f"- PE-TTM = `{rng.pe_ttm if rng.pe_ttm is not None else '—'}`\n"
                f"- PB = `{rng.pb if rng.pb is not None else '—'}`\n"
                f"- 市值 = "
                + (f"`¥{rng.market_cap/1e8:,.0f} 亿`" if rng.market_cap else "`—`")
                + "\n\n"
                f"**说明**:Graham Number 假设公司盈利稳定 + 净资产为正,"
                f"对银行/保险/亏损公司不适用。  \n"
                f"v2.8 将加入 PB-based 估值法(BPS × 行业 PB 中枢)兜底。"
            )

    # ── expander 2:选择标准 ──
    with st.expander("🎯 选择标准(为什么选这只)", expanded=False):
        st.markdown(f"**📌 持仓流派**:{entry.school}")
        if entry.criteria_met:
            st.markdown("**✅ 入选硬门槛**(当时满足):")
            for c in entry.criteria_met:
                st.markdown(f"- [✓] {c}")
        st.markdown(f"\n**💭 一句话依据**:{entry.rationale}")
        if entry.review_triggers:
            st.markdown("\n**⚠️ 反向风险**(任一成立需重审):")
            for r in entry.review_triggers:
                st.markdown(f"- {r}")


def _classify_lynch(ticker: str):
    """跑 lynch_classifier。失败返回 None。"""
    if not ticker:
        return None
    try:
        lc = SourceFileLoader(
            "lynch_classifier", str(_THIS.parent / "lynch_classifier.py")
        ).load_module()
        return lc.classify_ticker(ticker)
    except Exception:
        return None


def _lynch_card_html(result) -> str:
    """生成彼得林奇分类卡片 HTML。"""
    pct = max(0, min(100, int(round((result.confidence or 0) * 100))))
    # 类别配色
    cls_colors = {
        "slow_grower":  "#94A3B8",  # 灰
        "stalwart":     "#3B82F6",  # 蓝
        "fast_grower":  "#10B981",  # 绿
        "cyclical":     "#F59E0B",  # 橙
        "asset_play":   "#8B5CF6",  # 紫
        "turnaround":   "#EF4444",  # 红
    }
    cls_color = cls_colors.get(result.cls_id, "#6B7280")

    # 关键数据 → 双列 grid
    metric_items = "".join(
        f'<div style="display:flex;justify-content:space-between;'
        f'padding:3px 0;border-bottom:1px solid #F3F4F6;font-size:13px;">'
        f'<span style="color:#6B7280;">{k}</span>'
        f'<span style="color:#111827;font-weight:600;">{v}</span>'
        f'</div>'
        for k, v in result.key_metrics.items()
    )

    notes_html = ""
    if result.notes:
        notes_items = "".join(
            f'<li style="margin:2px 0;color:#374151;font-size:13px;line-height:1.5;">{n}</li>'
            for n in result.notes
        )
        notes_html = (
            f'<div style="margin-top:8px;padding:8px 12px;'
            f'background:#F0F9FF;border-left:3px solid #0EA5E9;border-radius:6px;">'
            f'<div style="font-size:12px;color:#0369A1;font-weight:600;margin-bottom:3px;">'
            f'💡 投资提示</div>'
            f'<ul style="margin:0;padding-left:18px;">{notes_items}</ul>'
            f'</div>'
        )

    return (
        f'<div style="background:white;border:1px solid #E5E7EB;'
        f'border-radius:14px;padding:14px 18px;margin:6px 0 8px;'
        f'font-family:-apple-system,Inter,PingFang SC,sans-serif;">'
        # ═══ 单元 1:公司类型判断(类型 + 信心 + 自动分析理由 合并)═══
        f'<div style="font-size:11px;color:#6B7280;font-weight:600;'
        f'letter-spacing:0.06em;text-transform:uppercase;margin-bottom:6px;'
        f'line-height:1.2;">🧭 公司类型判断</div>'
        f'<div style="background:#F9FAFB;border-left:3px solid {cls_color};'
        f'border-radius:8px;padding:10px 12px;margin-bottom:10px;">'
        # 类型行:emoji + 类别 + 信心进度(同一行)
        f'<div style="display:flex;justify-content:space-between;'
        f'align-items:center;gap:16px;">'
        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'<div style="width:36px;height:36px;border-radius:9px;'
        f'background:{cls_color}26;color:{cls_color};'
        f'display:flex;align-items:center;justify-content:center;font-size:20px;">'
        f'{result.cls_emoji}</div>'
        f'<div>'
        f'<div style="font-size:18px;font-weight:700;color:#111827;line-height:1.2;">'
        f'{result.cls_name}</div>'
        f'<div style="font-size:11px;color:#6B7280;line-height:1.2;">'
        f'彼得林奇 6 类之一</div>'
        f'</div>'
        f'</div>'
        f'<div style="text-align:right;min-width:130px;">'
        f'<div style="font-size:11px;color:#6B7280;margin-bottom:2px;">'
        f'分类信心 <b style="color:{cls_color}">{pct}%</b></div>'
        f'<div style="background:#FFFFFF;height:6px;border-radius:3px;width:130px;'
        f'border:1px solid #E5E7EB;">'
        f'<div style="background:{cls_color};height:100%;width:{pct}%;'
        f'border-radius:3px;"></div></div>'
        f'</div>'
        f'</div>'
        # 自动分析理由(贴紧上面,用细线分隔,不再独立开块)
        f'<div style="border-top:1px dashed #E5E7EB;margin-top:8px;padding-top:6px;'
        f'font-size:13px;color:#374151;line-height:1.5;">'
        f'<span style="color:#6B7280;font-weight:600;">📋 自动分析:</span> '
        f'{result.reason}</div>'
        f'</div>'
        # ═══ 单元 2:关键数据 grid ═══
        f'<div style="font-size:11px;color:#6B7280;font-weight:600;'
        f'letter-spacing:0.06em;text-transform:uppercase;margin-bottom:4px;'
        f'line-height:1.2;">📊 关键数据</div>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr;'
        f'column-gap:24px;">{metric_items}</div>'
        # ═══ 单元 3:投资提示 notes ═══
        f'{notes_html}'
        f'</div>'
    )


_SECTION_GRADIENTS = {
    "A": ("#0d6efd", "rgba(13,110,253,0.05)"),  # 蓝 — 看结论
    "B": ("#0EA5E9", "rgba(14,165,233,0.05)"),  # 青 — 评分体系
    "C": ("#10B981", "rgba(16,185,129,0.05)"),  # 绿 — 数据深挖
    "D": ("#8B5CF6", "rgba(139,92,246,0.05)"),  # 紫 — 决策档案
}


def _section_banner(letter: str, emoji: str, title: str, subtitle: str = "") -> str:
    """4 大区块 banner — 渐变背景条,提示用户"看到第几段了"。"""
    main, _bg = _SECTION_GRADIENTS.get(letter, ("#6B7280", "rgba(0,0,0,0.02)"))
    return (
        f'<div style="background:linear-gradient(90deg,{main} 0%,rgba(255,255,255,0) 100%);'
        f'padding:14px 18px;border-radius:10px;margin:28px 0 14px;'
        f'border-left:4px solid {main};'
        f'font-family:-apple-system,Inter,PingFang SC,sans-serif;">'
        f'<span style="font-size:11px;font-weight:800;color:white;'
        f'background:{main};padding:2px 8px;border-radius:4px;letter-spacing:1px;">'
        f'区块 {letter}</span>'
        f'<span style="font-size:18px;font-weight:700;color:white;margin-left:12px;">'
        f'{emoji} {title}</span>'
        f'<span style="font-size:12px;color:rgba(255,255,255,0.85);margin-left:12px;">'
        f'{subtitle}</span>'
        f'</div>'
    )


def _dim_explanation(label: str, raw: float | None, score: float | None) -> str | None:
    """根据维度 + 原值 + 0-100 分给出 1-2 句话简要解释(雪花图下方 Top3 详解用)。"""
    if raw is None:
        return "数据缺失,无法解读。"
    if label == "估值":
        pct = int(raw * 100)
        if raw < 0.20:
            return f"PE 处于过去 10 年 {pct}% 分位,显著低于历史均值,安全边际充足。"
        if raw < 0.50:
            return f"PE 处于过去 10 年 {pct}% 分位,估值偏低,有一定安全边际。"
        if raw <= 0.80:
            return f"PE 处于过去 10 年 {pct}% 分位,估值中性,需结合成长性判断。"
        return f"PE 处于过去 10 年 {pct}% 分位,历史高位,估值偏贵需谨慎。"
    if label == "盈利":
        roe = raw * 100
        if raw >= 0.20:
            return f"ROE {roe:.1f}%,远超行业均值,盈利能力极强(优秀公司门槛 > 15%)。"
        if raw >= 0.15:
            return f"ROE {roe:.1f}%,达到优秀水平(巴菲特门槛 ≥ 15%)。"
        if raw >= 0.10:
            return f"ROE {roe:.1f}%,平均水平,盈利能力一般。"
        return f"ROE {roe:.1f}%,低于优秀公司门槛,盈利能力偏弱。"
    if label == "成长":
        yoy = raw * 100
        if raw >= 0.30:
            return f"营收 YoY {yoy:.1f}%,高速成长,典型成长股区间(>30%)。"
        if raw >= 0.15:
            return f"营收 YoY {yoy:.1f}%,稳健成长,优于多数蓝筹。"
        if raw >= 0:
            return f"营收 YoY {yoy:.1f}%,温和增长,成长动能不足。"
        return f"营收 YoY {yoy:.1f}%,负增长,需关注主业是否衰退。"
    if label == "现金流":
        if raw >= 1.0:
            return f"CFO/NI {raw:.2f},经营现金流覆盖净利润,盈利质量极高(健康下限 0.8)。"
        if raw >= 0.8:
            return f"CFO/NI {raw:.2f},盈利质量健康,现金流与账面利润匹配。"
        if raw >= 0.5:
            return f"CFO/NI {raw:.2f},现金流偏弱,可能存在应收/存货沉淀。"
        return f"CFO/NI {raw:.2f},警示水平,需排查应收账款或商业模式真实性。"
    if label == "安全":
        dr = raw * 100
        if raw <= 0.30:
            return f"资产负债率 {dr:.1f}%,极低杠杆,财务稳健。"
        if raw <= 0.50:
            return f"资产负债率 {dr:.1f}%,低杠杆,财务安全。"
        if raw <= 0.65:
            return f"资产负债率 {dr:.1f}%,中等杠杆(非金融业警戒线 65%)。"
        return f"资产负债率 {dr:.1f}%,高杠杆,需关注偿债能力(银行/保险除外)。"
    if label == "策略":
        # raw 已是 avg/100 比值,note 里已写"X/Y 大师可比 · 均 ZZ"
        return f"多大师综合得分 {(raw*100):.0f}/100,反映在价值/成长/质量等多维度的可投资性。"
    return None


def _viewpoint_placeholder_html(name: str) -> str:
    return (
        f'<div style="background:#F9FAFB;border:1px dashed #D1D5DB;'
        f'border-radius:14px;padding:24px;margin:14px 0;text-align:center;'
        f'font-family:-apple-system,Inter,PingFang SC,sans-serif;">'
        f'<div style="font-size:32px;margin-bottom:8px;">🚧</div>'
        f'<div style="font-size:15px;font-weight:600;color:#374151;">'
        f'「{name}」视角即将上线</div>'
        f'<div style="font-size:13px;color:#6B7280;margin-top:6px;">'
        f'当前已支持「通用」(默认)和「彼得林奇」两种视角</div>'
        f'</div>'
    )


def _lynch_radar(dims, name: str):
    """Lynch 专属 5 维雷达图(plotly Scatterpolar)。"""
    import plotly.graph_objects as go
    labels = [d.label for d in dims]
    scores = [(d.score if d.score is not None else 0) for d in dims]
    labels_closed = labels + [labels[0]]
    scores_closed = scores + [scores[0]]

    fig = go.Figure(go.Scatterpolar(
        r=scores_closed, theta=labels_closed, fill="toself",
        line=dict(color="#0EA5E9", width=2.4),
        fillcolor="rgba(14,165,233,0.15)",
        marker=dict(size=10, color="#0EA5E9", line=dict(color="white", width=2)),
        hovertemplate="<b>%{theta}</b><br>%{r:.0f}/100<extra></extra>",
        showlegend=False, name=name,
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100],
                            tickvals=[20, 40, 60, 80, 100],
                            ticktext=["", "", "", "", ""],
                            gridcolor="#EEF1F5", linecolor="#EEF1F5"),
            angularaxis=dict(gridcolor="#F3F4F6", linecolor="#E5E7EB",
                             tickfont=dict(size=13, color="#374151")),
            bgcolor="rgba(0,0,0,0)",
        ),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=400, margin=dict(l=60, r=60, t=20, b=20),
        showlegend=False,
    )
    return fig


def _load_industry_map() -> dict:
    """从 .config/companies.csv 读 (folder → {industry, industry_l2, ticker, name})。
    缓存在模块级,避免重复读。"""
    global _INDUSTRY_MAP
    if _INDUSTRY_MAP is not None:
        return _INDUSTRY_MAP
    import pandas as _pd
    csv = _THIS.parent.parent.parent / ".config" / "companies.csv"
    try:
        df = _pd.read_csv(csv, dtype={"stock": str})
        out = {}
        for _, r in df.iterrows():
            out[str(r["folder"])] = {
                "ticker": str(r["stock"]),
                "name":   str(r.get("name", "")),
                "industry":     str(r.get("industry", "") or ""),
                "industry_l2":  str(r.get("industry_l2", "") or ""),
            }
        _INDUSTRY_MAP = out
        return out
    except Exception:
        _INDUSTRY_MAP = {}
        return {}


_INDUSTRY_MAP = None


def _peers_same_industry(selected_folder: str, level: str = "l2",
                         all_companies: list[str] | None = None) -> tuple[list[str], str]:
    """返回 (同行业 folder 列表 含 selected, 行业标签)。
    level='l2' 申万二级;'l1' 申万一级。

    selected 不在表中 / 行业为空 → ([], '')。
    """
    imap = _load_industry_map()
    sel = imap.get(selected_folder)
    if not sel:
        return [], ""
    key = "industry_l2" if level == "l2" else "industry"
    target = sel.get(key, "").strip()
    if not target:
        return [], ""
    pool = all_companies or list(imap.keys())
    peers = [f for f in pool if imap.get(f, {}).get(key, "").strip() == target]
    return peers, target


def _lynch_dim_card_html(dim) -> str:
    """A5:维度评分卡(精简版)— 不带公式,仅分数+badge+note。"""
    score = dim.score
    score_str = f"{score:.0f}" if score is not None else "—"
    return (
        f'<div style="background:white;border:1px solid #E5E7EB;'
        f'border-radius:10px;padding:9px 12px;font-family:-apple-system,Inter,PingFang SC,sans-serif;">'
        f'<div style="font-size:11px;color:#6B7280;font-weight:600;'
        f'letter-spacing:0.04em;text-transform:uppercase;margin-bottom:2px;line-height:1.2;">'
        f'{dim.badge} {dim.label}</div>'
        f'<div style="font-size:22px;font-weight:700;color:#111827;line-height:1.1;">'
        f'{score_str}<span style="font-size:11px;color:#9CA3AF;font-weight:500;"> /100</span></div>'
        f'<div style="font-size:11px;color:#6B7280;margin-top:1px;line-height:1.35;">{dim.note}</div>'
        f'</div>'
    )


def render(app_globals: dict) -> None:
    """app.py 在 dispatch 时把 globals() 传过来,把这些名字注入到本模块 globals
    让原段代码无需改写即可访问 selected / DB_MTIME / _company_score / _radar_chart /
    render_radar / company_score / pr / dt 等。

    注:不能 `import app`,因为 streamlit testing 下 app.py 不在 sys.modules 中,
    会重新执行 app.py 顶部并触发 st.radio(key='nav') 重复键报错。
    """
    g = globals()
    for _k, _v in app_globals.items():
        if _k != "__builtins__":
            g[_k] = _v

    # ─── 段 1:SWS 风格 Hero + 雷达 + 五维 + Piotroski ─────────────
    st.markdown(_SWS_CSS, unsafe_allow_html=True)
    folder_to_ticker_home = _folder_to_ticker(DB_MTIME)
    ticker = folder_to_ticker_home.get(selected, "")
    home_window = st.radio(
        "PE 分位窗口", ["10y", "5y", "3y", "1y", "all"], index=0, horizontal=True,
        key="home_window",
        help="估值维度的 PE-TTM 分位口径,默认 10 年。窗口切换不影响其它维度。",
    )

    score_dict = _company_score(ticker, home_window, DB_MTIME)
    if score_dict is None:
        st.error(f"⚠️ 无法加载评分(ticker={ticker or '未映射'})")
    else:
        ov = score_dict["overall"] or 0.0
        ov_label, _ov_color = _sws_score_pill(ov)

        # ─── Hero(渐变 banner)─────────────────────────────
        st.markdown(
            f'<div class="sws-hero">'
            f'  <div class="sws-hero-row">'
            f'    <div>'
            f'      <h1 class="sws-hero-name">{score_dict["name"]}'
            f'<span class="sws-hero-ticker">{score_dict["ticker"]}</span></h1>'
            f'      <div class="sws-hero-cat">'
            f'{(score_dict["category"] or "通用").upper()} · 分位窗口 {home_window}</div>'
            f'    </div>'
            f'    <div class="sws-hero-score-block">'
            f'      <div class="sws-hero-score-label">★ Snowflake 综合评分</div>'
            f'      <div><span class="sws-hero-score-num">{ov:.0f}</span>'
            f'<span class="sws-hero-score-suffix">/100</span></div>'
            f'      <div class="sws-hero-score-pill">{ov_label}</div>'
            f'    </div>'
            f'  </div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ─── v2.7 持仓档案卡(仅持仓股渲染)─────────────────────────
        _render_position_card(ticker, st)

        # ─── A1+A3:投资视角切换 + 彼得林奇分类卡片 ────────────────
        VIEW_GENERIC = "⚪ 通用"
        VIEW_LYNCH   = "🔍 彼得林奇"
        VIEW_BUFFETT = "💎 巴菲特"
        VIEW_GRAHAM  = "🛡️ 格雷厄姆"
        viewpoint = st.radio(
            "投资视角",
            [VIEW_GENERIC, VIEW_LYNCH, VIEW_BUFFETT, VIEW_GRAHAM],
            index=0, horizontal=True, key="home_viewpoint",
            help="不同大师视角下,公司分类与五维口径不同。当前已支持通用 + 彼得林奇。",
        )

        if viewpoint == VIEW_LYNCH:
            try:
                lc = SourceFileLoader(
                    "lynch_classifier", str(_THIS.parent / "lynch_classifier.py")
                ).load_module()
                metrics = lc.load_metrics_from_db(ticker)
                lr = lc.classify(metrics)
            except Exception as _e:
                st.info(f"⚠️ 彼得林奇分类引擎调用失败:{_e}")
                lr = None

            if lr is not None:
                # 1) 分类卡片
                st.markdown(_lynch_card_html(lr), unsafe_allow_html=True)

                # 2) A4:专属 5 维 雷达 + 卡片 + 综合分
                lynch_dims = lc.compute_lynch_dims(metrics, lr.cls_id)
                lynch_overall, lynch_badge = lc.overall_lynch(lynch_dims)

                col_l, col_r = st.columns([3, 2], gap="medium")
                with col_l:
                    st.plotly_chart(
                        _lynch_radar(lynch_dims, score_dict["name"]),
                        use_container_width=True,
                        config={"displayModeBar": False},
                    )
                with col_r:
                    st.markdown(
                        f'<div style="background:white;border:1px solid #E5E7EB;'
                        f'border-radius:14px;padding:12px 16px;'
                        f'font-family:-apple-system,Inter,PingFang SC,sans-serif;">'
                        f'<div style="font-size:11px;color:#6B7280;font-weight:600;'
                        f'letter-spacing:0.06em;text-transform:uppercase;'
                        f'margin-bottom:4px;line-height:1.2;">'
                        f'{lr.cls_emoji} {lr.cls_name} · 专属 5 维</div>'
                        f'<div style="font-size:38px;font-weight:800;color:#111827;'
                        f'line-height:1.1;">{lynch_badge} {lynch_overall:.0f}'
                        f'<span style="font-size:14px;color:#9CA3AF;'
                        f'font-weight:500;"> /100</span></div>'
                        f'<div style="font-size:12px;color:#6B7280;margin-top:4px;line-height:1.4;">'
                        f'按 <b>{lr.cls_name}</b> 类别加权;权重见每维详情</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                # 3) 5 张评分卡(横向)
                cols = st.columns(5)
                for i, d in enumerate(lynch_dims):
                    with cols[i]:
                        st.markdown(_lynch_dim_card_html(d), unsafe_allow_html=True)

                # 4) A5:每维下钻 expander
                st.markdown(
                    '<div style="font-size:11px;color:#6B7280;font-weight:600;'
                    'letter-spacing:0.08em;text-transform:uppercase;'
                    'margin:8px 0 2px 0;">📐 每维评分明细(展开看公式)</div>',
                    unsafe_allow_html=True,
                )
                for d in lynch_dims:
                    s_str = f"{d.score:.0f}" if d.score is not None else "—"
                    title = (
                        f"{d.badge} {d.label} · {s_str}/100 · "
                        f"权重 {int(d.weight*100)}% · {d.note}"
                    )
                    with st.expander(title, expanded=False):
                        st.markdown(
                            f'<div style="font-size:13px;color:#374151;line-height:1.5;">'
                            f'<div style="margin-bottom:3px;">'
                            f'<b>📊 输入</b>'
                            + "".join(
                                f'<div style="margin-left:14px;">'
                                f'<span style="color:#6B7280;">{k}</span>'
                                f' = <span style="color:#111827;font-weight:600;">{v}</span>'
                                f'</div>' for k, v in d.inputs.items()
                            )
                            + f'</div>'
                            f'<div style="margin-bottom:3px;"><b>🧮 公式</b>'
                            f'<div style="margin-left:14px;color:#6B7280;'
                            f'font-family:ui-monospace,SFMono-Regular,monospace;'
                            f'font-size:12px;">{d.formula}</div></div>'
                            f'<div><b>🎯 结果</b>'
                            f'<div style="margin-left:14px;">'
                            f'<span style="font-size:18px;font-weight:700;color:#111827;">'
                            f'{s_str}/100</span> '
                            f'<span style="color:#6B7280;">— {d.note}</span></div></div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

        elif viewpoint in (VIEW_BUFFETT, VIEW_GRAHAM):
            st.markdown(
                _viewpoint_placeholder_html(viewpoint.split(" ", 1)[-1]),
                unsafe_allow_html=True,
            )

        # ─── v2.0 知识体系迭代:综合健康度卡片(Altman + Greenblatt + 中国警示)
        try:
            health = sc.health_score(ticker)
            verdict_color = {
                "🟢": "#10B981", "🟡": "#F59E0B",
                "🟠": "#F97316", "🔴": "#EF4444",
            }.get(health["badge"], "#9CA3AF")
            cmp = health["components"]
            warns = health["warnings"]["items"]
            alt = health["altman"]
            grb = health["greenblatt"]

            warns_html = ""
            if warns:
                rows = "".join(
                    f'<div style="margin:4px 0;font-size:12px;">'
                    f'<span style="font-size:14px;">{w["level"]}</span> '
                    f'<b>{w["title"]}</b> · '
                    f'<span style="color:#6B7280;">{w["detail"]}</span>'
                    f'</div>'
                    for w in warns
                )
                warns_html = (
                    f'<div style="margin-top:12px;padding:10px 12px;'
                    f'background:#FEF3C7;border-left:3px solid #F59E0B;border-radius:6px;">'
                    f'<div style="font-size:12px;color:#92400E;font-weight:600;'
                    f'margin-bottom:4px;">⚠️ 中国本土暴雷警示 · {len(warns)} 项</div>'
                    f'{rows}</div>'
                )

            comp_html = "".join(
                f'<div style="display:flex;justify-content:space-between;'
                f'font-size:12px;padding:3px 0;">'
                f'<span style="color:#6B7280;">{k}</span>'
                f'<span style="font-weight:600;color:'
                f'{("#EF4444" if v < 0 else "#111827")};">{v:+.2f}</span>'
                f'</div>'
                for k, v in cmp.items()
            )

            st.markdown(
                f'<div style="margin:18px 0;padding:18px 22px;'
                f'background:linear-gradient(135deg,#F9FAFB 0%,#F3F4F6 100%);'
                f'border-radius:14px;border:1px solid #E5E7EB;">'
                f'  <div style="display:flex;align-items:center;justify-content:space-between;">'
                f'    <div>'
                f'      <div style="font-size:11px;color:#6B7280;letter-spacing:1px;">'
                f'🏥 综合健康度 v2.0</div>'
                f'      <div style="font-size:32px;font-weight:800;color:{verdict_color};'
                f'line-height:1.2;margin-top:4px;">{health["score"]:.1f}<span style="font-size:18px;color:#9CA3AF;font-weight:500;">/10</span></div>'
                f'      <div style="font-size:13px;color:{verdict_color};font-weight:600;'
                f'margin-top:2px;">{health["badge"]} {health["verdict"]}</div>'
                f'    </div>'
                f'    <div style="display:flex;gap:18px;align-items:flex-end;">'
                f'      <div style="text-align:center;">'
                f'        <div style="font-size:11px;color:#6B7280;">Altman 风险</div>'
                f'        <div style="font-size:20px;">{alt["badge"]} {alt["score"]}/{alt["max"]}</div>'
                f'        <div style="font-size:11px;color:#9CA3AF;">{alt["rating"]}</div>'
                f'      </div>'
                f'      <div style="text-align:center;">'
                f'        <div style="font-size:11px;color:#6B7280;">Greenblatt</div>'
                f'        <div style="font-size:20px;">{grb["badge"]} {grb["score"]:.0f}</div>'
                f'        <div style="font-size:11px;color:#9CA3AF;">好生意+便宜</div>'
                f'      </div>'
                f'    </div>'
                f'  </div>'
                f'  <div style="margin-top:14px;padding-top:12px;border-top:1px dashed #D1D5DB;">'
                f'    <div style="font-size:11px;color:#6B7280;margin-bottom:4px;">'
                f'分项构成(满分 10):</div>'
                f'    {comp_html}'
                f'  </div>'
                f'  {warns_html}'
                f'</div>',
                unsafe_allow_html=True,
            )
        except Exception as _hs_exc:
            st.caption(f"(综合健康度加载失败:{_hs_exc})")

        # ─── 雷达 + 五维速读 ─────────────────────────────────
        left, right = st.columns([3, 2], gap="medium")
        with left:
            st.plotly_chart(
                _radar_chart(score_dict["dims"], score_dict["name"]),
                use_container_width=True,
                config={"displayModeBar": False},
            )
        with right:
            summary_lines = []
            for k in SWS_DIM_KEYS:
                d = score_dict["dims"][k]
                color = SWS_COLORS[k]
                icon = SWS_ICONS[k]
                score_str = f"{d['score']:.0f}" if d["score"] is not None else "—"
                note = d["note"] or ""
                summary_lines.append(
                    f'<div class="sws-summary-line">'
                    f'  <span class="sws-summary-icon">{icon}</span>'
                    f'  <span class="sws-summary-name">{d["label"]}</span>'
                    f'  <span class="sws-summary-note">{note}</span>'
                    f'  <span class="sws-summary-score" style="color:{color};">{score_str}</span>'
                    f'</div>'
                )
            st.markdown(
                f'<div class="sws-card">'
                f'  <div class="sws-summary-title">📌 五维速读</div>'
                f'  {"".join(summary_lines)}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ─── 五维详细卡片(图标 + 分数 + Pill + 进度条)───────
        st.markdown('<div class="sws-section-header">五维详细</div>', unsafe_allow_html=True)
        cards_html = "".join(
            _sws_dim_card_html(k, score_dict["dims"][k]) for k in SWS_DIM_KEYS
        )
        st.markdown(cards_html, unsafe_allow_html=True)

        # ─── Piotroski 子项展开 ─────────────────────────────
        with st.expander("🔬 Piotroski F-Score 9 项明细", expanded=False):
            year = st.number_input("评估年份", min_value=2018, max_value=2025, value=2024,
                                   step=1, key="home_fscore_year")
            fs, details = _fscore_for(ticker, year, DB_MTIME)
            if fs is None:
                st.caption("(F-Score 计算失败 — 可能数据缺失)")
            else:
                fs_color = "#10B981" if fs >= 7 else ("#F59E0B" if fs >= 5 else "#EF4444")
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">'
                    f'<span style="font-size:22px;font-weight:700;color:{fs_color};">{fs}/9</span>'
                    f'<span style="font-size:13px;color:#6B7280;">年份 {year}</span></div>',
                    unsafe_allow_html=True,
                )
                for d in details:
                    icon = "✅" if d["passed"] else ("❌" if d["passed"] is False else "⚪")
                    st.markdown(f"- {icon} `{d['id']}` {d['name']} · {d['score']:.0f} 分")

        st.markdown(
            '<div class="sws-mini-cap">'
            '映射规则:估值=PE 全周期分位反向 · 盈利=ROE · 成长=营收 YoY · '
            '现金流=CFO/NI · 安全=负债率反向 '
            '(详见 <a href="score_card.py" style="color:#6366F1;">score_card.py</a>)'
            '</div>',
            unsafe_allow_html=True,
        )

    write_context(selected)


    # ─── 段 2:V8/V9 雪花 + 6 子 Tab + dash-03 大师矩阵/同行雷达 ───
    # ═══ 区块 A · 看结论(雪花 + 优势短板)═══
    st.markdown(
        _section_banner("A", "🎯", "一眼看结论", "雪花图 · 优势短板 Top3 · 一句话定位"),
        unsafe_allow_html=True,
    )
    folder_to_ticker_local = _folder_to_ticker(DB_MTIME)
    selected_ticker = folder_to_ticker_local.get(selected, "")

    # ─── 区块 A-0:💡 vs 同行业建议卡(Phase C)─────────────────────
    if selected_ticker:
        try:
            import sys as _sys
            _here = str(Path(__file__).resolve().parent)
            if _here not in _sys.path:
                _sys.path.insert(0, _here)
            import peers.advisor as _pa
            _adv = _pa.advise(selected_ticker, name=selected)
            if _adv is not None and _adv.n_peers > 0:
                st.markdown(_pa.render_hero_card_html(_adv), unsafe_allow_html=True)
        except Exception as _pa_e:
            st.caption(f"⚠️ 同行建议引擎调用失败:{_pa_e}")

    # ─── V8 顶部:综合评分 + 雪花图(SWS 风格)+ 股价叠加全局 toggle ─
    score = company_score(selected_ticker, DB_MTIME) if selected_ticker else None
    head_left, head_mid = st.columns([1.0, 2.0])
    with head_left:
        st.markdown(f"### 🏢 {selected}")
        if score is not None and score.overall is not None:
            st.metric("★ 综合评分", f"{score.overall:.1f} / 100", help="6 维加权(估值/盈利/成长/现金流/安全/策略)")
            st.markdown(f"#### {score.overall_badge} {score.category or '—'}")
        else:
            st.caption("(评分不可用 — 数据缺失或 ticker 未映射)")
        st.toggle(
            "📈 在所有时序图叠加股价(右轴)", value=False, key="overlay_price",
            help="勾选后,公司详情下方的指标时序图会在右轴叠加 prices 表收盘价",
        )
        if decisions_db is not None:
            if st.button("➕ 一键补录决策", key="quick_add_decision",
                         help="带入当前公司,切换到「📝 决策日志」tab 即可填写表单"):
                st.session_state["dec_company"] = selected
                st.session_state["pending_decision_for"] = selected
                st.toast(f"已带入「{selected}」 → 切到「📝 决策日志」tab 即可", icon="➕")
    with head_mid:
        if score is not None:
            st.plotly_chart(render_radar(score), use_container_width=True)
        else:
            st.info("无法生成雪花图")

    # ─── 雷达下方:优势/短板 Top3 + 详解(每条 1-2 句话)──────────
    if score is not None:
        valid = [
            (sc.DIM_LABEL.get(k, k),
             score.dims[k].score,
             score.dims[k].badge or "⚪",
             score.dims[k].note or "",
             score.dims[k].raw)
            for k in SCORE_DIM_ORDER
            if score.dims.get(k) and score.dims[k].score is not None
        ]
        top = sorted(valid, key=lambda x: x[1], reverse=True)[:3]
        bot = sorted(valid, key=lambda x: x[1])[:3]

        col_top, col_bot = st.columns(2)
        with col_top:
            st.markdown("##### 🟢 优势 Top3 · 为什么强?")
            for label, val, badge, note, raw in top:
                with st.container(border=True):
                    st.markdown(
                        f"{badge} **{label}** · `{val:.0f}/100`"
                        + (f" · <span style='color:#6B7280;font-size:13px'>{note}</span>" if note else ""),
                        unsafe_allow_html=True,
                    )
                    explain = _dim_explanation(label, raw, val)
                    if explain:
                        st.caption(explain)
        with col_bot:
            st.markdown("##### 🔴 短板 Top3 · 为什么弱?")
            for label, val, badge, note, raw in bot:
                with st.container(border=True):
                    st.markdown(
                        f"{badge} **{label}** · `{val:.0f}/100`"
                        + (f" · <span style='color:#6B7280;font-size:13px'>{note}</span>" if note else ""),
                        unsafe_allow_html=True,
                    )
                    explain = _dim_explanation(label, raw, val)
                    if explain:
                        st.caption(explain)

        # 一句话定位
        if top and bot:
            t_label, _, _, t_note, _ = top[0]
            b_label, _, _, b_note, _ = bot[0]
            if t_label != b_label:
                st.caption(
                    f"💡 一句话定位:**{t_label}** 极强({t_note.split('·')[0].strip() if t_note else '—'})"
                    f",**{b_label}** 偏弱({b_note.split('·')[0].strip() if b_note else '—'})"
                )

    # ═══ 区块 B · 大师评分体系 ═══
    # 启用阵容由 master_philosophy.ACTIVE_MASTERS 决定(当前:格雷厄姆/巴菲特/林奇)
    try:
        import sys as _sys_b
        _dash_dir_b = str((DUCKDB_PATH.parent.parent / ".tools/dashboard").resolve())
        if _dash_dir_b not in _sys_b.path:
            _sys_b.path.insert(0, _dash_dir_b)
        import masters.philosophy as _mp_meta
        _active_n = len(_mp_meta.ACTIVE_MASTERS)
        _active_names = "/".join(_mp_meta.MASTERS[k]["name_cn"] for k in _mp_meta.ACTIVE_MASTERS)
    except Exception:
        _active_n = 3
        _active_names = "格雷厄姆/巴菲特/彼得林奇"

    st.markdown(
        _section_banner(
            "B", "🧪", "大师评分体系",
            f"多大师矩阵 · {_active_n} 大师投票({_active_names})· 同行雷达",
        ),
        unsafe_allow_html=True,
    )

    # ─── dash-03: N 大师矩阵 + 同行雷达 ───────────────────────────
    if selected_ticker:
        peer_pool_list = pr.peer_pool(selected_ticker, db_path=DUCKDB_PATH, max_n=4) if pr else []
        peer_tickers = [t for t, _ in peer_pool_list]

        st.markdown(f"#### 🧪 多大师评分矩阵 · {_active_n} 大师怎么看?· 通过几票?")
        render_master_matrix(selected_ticker, peer_tickers)

        # ─── N 大师投票 + 哲学速读(M3 #2:默认展开 + 方法论说明 + 全宽哲学速读)─
        try:
            import sys
            _dash_dir = str((DUCKDB_PATH.parent.parent / ".tools/dashboard").resolve())
            if _dash_dir not in sys.path:
                sys.path.insert(0, _dash_dir)
            import masters.philosophy as mp

            from datetime import date as _d
            _vote_year = _d.today().year - 1
            n_active = len(mp.ACTIVE_MASTERS)
            half = (n_active + 1) // 2  # 过半数(2/3 = 2,5/7 = 4)
            with st.expander(
                f"🗳️ {n_active} 大师投票 + 💡 哲学速读 · 各自评什么?",
                expanded=True,
            ):
                # M3 #2:嵌套 expander 顶部展示"评估方法说明"
                with st.expander(f"📖 评估方法说明 · {n_active} 大师评什么 / 投票口径", expanded=False):
                    method_rows = "".join(
                        f'<div style="display:flex;padding:6px 0;border-bottom:1px solid #f0f0f0;font-size:13px;">'
                        f'<span style="flex:0 0 90px;font-weight:600;color:{mp.MASTERS[k]["color"]};">{mp.MASTERS[k]["name_cn"]}</span>'
                        f'<span style="flex:1;color:#374151;line-height:1.55;">{mp.MASTERS[k]["thesis"]}</span>'
                        f'</div>'
                        for k in mp.ACTIVE_MASTERS
                    )
                    st.markdown(
                        f'<div style="background:#F9FAFB;border-left:3px solid #0EA5E9;'
                        f'padding:10px 14px;border-radius:6px;margin-bottom:10px;">'
                        f'<div style="font-size:12px;color:#0369A1;font-weight:600;'
                        f'margin-bottom:8px;">当前启用 {n_active} 大师 · 各自评什么</div>'
                        f'{method_rows}</div>',
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        '**🗳️ 投票口径**\n\n'
                        '- 每位大师独立评分(规则数与口径不同)→ 归一化到 0-100\n'
                        '- ≥75 强烈推荐 ✅ / ≥60 倾向买 🟢 / ≥45 观望 🟡 / ≥30 倾向卖 🟠 / <30 卖出 🔴\n'
                        f'- "倾向买"以上记一票通过;**≥{half} 票通过 = 中性 / {n_active} 票通过 = 强烈推荐**\n'
                        '- 数据缺(valid=0)的大师不计入投票分母\n'
                        '- 启用阵容由 `master_philosophy.ACTIVE_MASTERS` 控制,改这里即切换'
                    )
                    st.caption(
                        "📖 完整哲学说明:[01_knowledge/03_投资策略与选股/11_大师哲学_深化补充.md]"
                        "(../../01_knowledge/03_投资策略与选股/11_大师哲学_深化补充.md)"
                    )

                # 投票卡(全宽)
                _votes = mp.vote_card(selected_ticker, year=_vote_year)

                # 哲学速读(M3 #2:从 1:1 双栏挪到全宽,Tab 切换)
                st.markdown("##### 💡 哲学速读 · 切大师看深度解读")
                mp.philosophy_tabs(ticker=selected_ticker, year=_vote_year, votes=_votes)
        except Exception as _mp_exc:
            st.caption(f"(大师哲学模块加载失败:{_mp_exc})")

        with st.expander("🤝 同行 6 维雷达叠加", expanded=False):
            if pr is None:
                st.info("peer_radar 模块未加载")
            else:
                ps = peer_scores(selected_ticker, DB_MTIME, max_n=4)
                if not ps:
                    st.info("同行评分计算失败")
                else:
                    st.plotly_chart(
                        pr.peer_radar_chart(ps, selected_ticker),
                        use_container_width=True,
                    )
                    st.caption(f"同 category 同行({len(ps)-1} 家):" + ", ".join(s.name for s in ps if s.ticker != selected_ticker))

    # ═══ 区块 C · 数据深挖 ═══
    st.markdown(
        _section_banner("C", "📊", "数据深挖", "6 维子 Tab · K 线 · 行业 PE · 横向对比"),
        unsafe_allow_html=True,
    )

    # ─── 6 子 Tab(深度区):每维一卡 + 主图 + 共享股价叠加 ────────
    # M3 优化项 #5:6 子 Tab 默认展开
    detail_expander = st.expander(
        "📊 6 维数据深挖 · 哪些指标最值得看?(主图 + CSV 导出)", expanded=True,
    )
    DIM_TO_MODULE = {
        "valuation": "估值", "profitability": "盈利", "growth": "成长",
        "cashflow": "现金流", "safety": "安全性", "strategies": None,
    }
    sub_labels = [f"{(score.dims[k].badge if score and score.dims.get(k) else '⚪') or '⚪'} {sc.DIM_LABEL.get(k, k)}"
                  for k in SCORE_DIM_ORDER]
    with detail_expander:
        sub_tabs = st.tabs(sub_labels)
    last_module = None
    last_picked: list = []
    last_window = None

    for idx, dim_key in enumerate(SCORE_DIM_ORDER):
        with sub_tabs[idx]:
            d = score.dims.get(dim_key) if score else None
            sl, sr = st.columns([1, 3])
            with sl:
                badge = (d.badge if d else "⚪") or "⚪"
                val = f"**{d.score:.0f}** / 100" if d and d.score is not None else "**N/A**"
                st.markdown(f"### {badge} {sc.DIM_LABEL.get(dim_key, dim_key)}\n#### {val}")
                if d and d.note:
                    st.caption(d.note)
            with sr:
                if dim_key == "strategies":
                    render_strategies_detail(score) if score else st.info("评分不可用")
                    continue
                module = DIM_TO_MODULE[dim_key]
                df = load_metric(selected, module, DB_MTIME)
                if df.empty:
                    st.warning(f"{selected} / {module} 数据缺失")
                    continue
                cols = numeric_cols(df)
                window_label = st.select_slider(
                    "时间窗", options=["近 1 年", "近 3 年", "近 5 年", "全部"],
                    value="近 5 年", key=f"win_{dim_key}",
                )
                window_days = {"近 1 年": 365, "近 3 年": 365 * 3, "近 5 年": 365 * 5, "全部": None}[window_label]
                df_view = df if window_days is None else df[df["date"] >= df["date"].max() - pd.Timedelta(days=window_days)]
                last_module, last_window = module, window_label

                if dim_key == "valuation":
                    pct_options = [m for m in PERCENTILE_TRIPLES if m in cols]
                    pct_metric = st.selectbox("分位带指标", pct_options, key=f"pct_metric_{dim_key}") if pct_options else None
                    if pct_metric:
                        fig = percentile_band_chart(df_view, pct_metric, f"{selected} · {pct_metric} 分位带")
                        if fig is not None:
                            fig = overlay_price(fig, selected_ticker, df_view["date"].min(), df_view["date"].max())
                            st.plotly_chart(fig, use_container_width=True)
                    last_picked = [pct_metric] if pct_metric else []

                    # 林奇 PEG 时间曲线(理杏仁口径)— M6-#5 子任务先落地
                    with st.expander("📈 PEG 时间曲线(林奇五步法第 4 步 · 理杏仁口径)", expanded=False):
                        if not selected_ticker:
                            st.caption("(未找到 ticker 映射,无法计算 PEG)")
                        else:
                            try:
                                _peg_mod = SourceFileLoader(
                                    "peg_curve", str(_THIS.parent / "peg_curve.py"),
                                ).load_module()
                                _peg_mod.render_peg_curve(
                                    ticker=selected_ticker,
                                    name=selected,
                                    lookback_years=5,
                                )
                            except Exception as e:
                                st.warning(f"PEG 曲线渲染失败:{e}")
                else:
                    defaults_map = {
                        "profitability": ("净资产收益率(ROE)", "毛利率(GM)"),
                        "growth": ("营业收入", "净利润"),
                        "cashflow": ("自由现金流量", "经营活动产生的现金流量净额"),
                        "safety": ("资产负债率", "流动比率"),
                    }
                    pref = defaults_map.get(dim_key, ())
                    default = [c for c in pref if c in cols][:2] or cols[:2]
                    picked = st.multiselect("指标", cols, default=default, key=f"picked_{dim_key}")
                    if picked:
                        fig = px.line(df_view, x="date", y=picked, title=f"{selected} · {module}")
                        fig.update_layout(height=420, hovermode="x unified")
                        fig = overlay_price(fig, selected_ticker, df_view["date"].min(), df_view["date"].max())
                        st.plotly_chart(fig, use_container_width=True)
                    last_picked = picked

                with st.expander("⬇️ 原始数据(末 50 行)+ CSV 导出"):
                    st.dataframe(df_view.tail(50), use_container_width=True, hide_index=True)
                    st.download_button(
                        f"下载 {selected}/{module} CSV",
                        df_view.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"{selected}_{module}.csv",
                        mime="text/csv", key=f"dl_{dim_key}",
                    )

    # ─── 股价 K 线 + 行业 PE(M3 优化项 #4:右侧栏拆出 → 区块 D)──────
    st.divider()
    st.markdown("#### 📈 股价走势怎么样?· 跑赢行业了吗?")

    if not selected_ticker:
        st.caption("(未找到 ticker 映射)")
    else:
        prices = load_prices(selected_ticker, DB_MTIME)
        if prices.empty:
            st.caption("(prices 表无此 ticker · 可能是港股或未抓取)")
        else:
            price_window = st.select_slider(
                "股价时间窗", options=["近 1 月", "近 3 月", "近 1 年", "近 3 年", "全部"],
                value="近 1 年", key="price_win",
            )
            wd = {"近 1 月": 30, "近 3 月": 90, "近 1 年": 365, "近 3 年": 1095, "全部": None}[price_window]
            pv = prices if wd is None else prices[prices["date"] >= prices["date"].max() - pd.Timedelta(days=wd)]
            kfig = go.Figure(data=[go.Candlestick(
                x=pv["date"], open=pv["open"], high=pv["high"], low=pv["low"], close=pv["close"], name=selected_ticker,
            )])
            kfig.update_layout(
                height=420, hovermode="x unified", xaxis_rangeslider_visible=False,
                title=f"{selected} ({selected_ticker}) · {price_window} K 线",
            )
            st.plotly_chart(kfig, use_container_width=True)

    # ─── 📊 行业 ETF 对标(基准化叠加 · 35 只 ETF, 2 年 K 线)─────────
    st.markdown("##### 📊 行业 ETF 对标 · 跑赢 / 跑平 / 跑输?")
    _etf_window_days = {
        "近 1 月": 30, "近 3 月": 90, "近 1 年": 365, "近 3 年": 1095, "全部": None
    }.get(st.session_state.get("price_win", "近 1 年"), 365)
    if selected_ticker:
        try:
            render_etf_overlay(selected, selected_ticker, _etf_window_days)
        except Exception as _etf_exc:
            st.caption(f"(ETF 对标加载失败:{_etf_exc})")

    st.markdown("##### 🏭 行业 PE 中位数(industry_pe)")
    industries = list_industries(DB_MTIME)
    if industries:
        options = [f"{c} · {n}" for c, n in industries]
        opt_idx = st.selectbox("行业", range(len(options)), format_func=lambda i: options[i], key="ind_idx")
        ind_code, ind_name = industries[opt_idx]
        ind_df = load_industry_pe(ind_code, DB_MTIME)
        if ind_df.empty:
            st.caption("(无数据)")
        else:
            ifig = px.line(ind_df, x="date", y=["pe_median", "pe_weighted", "pe_arith"],
                           title=f"{ind_name} · PE 中位/加权/算术")
            ifig.update_layout(height=320, hovermode="x unified")
            st.plotly_chart(ifig, use_container_width=True)

    write_context(
        selected,
        module=last_module,
        metric=", ".join([p for p in last_picked if p]) if last_picked else None,
        window=last_window,
    )


    # ─── 横向对比(原段 3 → 合并到区块 C 内,评分对比一族)─────────
    st.divider()
    st.markdown("### ⚖️ 横向对比 · 跟同行/历史比 · 当前贵不贵?")
    cmp_mode = st.radio(
        "模式", ["📈 单指标时间序列", "🧪 F-Score 9 项跨公司矩阵"],
        horizontal=True, key="cmp_mode",
    )
    if cmp_mode.startswith("🧪"):
        eng = _score_engine()
        if eng is None:
            st.warning("评分引擎不可用 — `.tools/score/engine.py` import 失败")
        else:
            colf1, colf2 = st.columns([1, 3])
            with colf1:
                f_year = st.number_input("年份", min_value=2018, max_value=pd.Timestamp.now().year,
                                          value=pd.Timestamp.now().year - 1, step=1, key="f_year")
                f_targets = st.multiselect("公司", companies,
                                           default=companies[: min(8, len(companies))], key="f_targets")
            with colf2:
                if f_targets:
                    fmap = _folder_to_ticker(DB_MTIME)
                    matrix_rows = []
                    rule_names: list[tuple[str, str]] = []
                    for c in f_targets:
                        ticker = fmap.get(c, "")
                        det = piotroski_detail(ticker, int(f_year), DB_MTIME)
                        if det is None:
                            matrix_rows.append({"公司": c, "合计": "—"})
                            continue
                        if not rule_names:
                            rule_names = [(rid, name) for rid, name, _ in det["items"]]
                        row = {"公司": c}
                        for rid, _, passed in det["items"]:
                            row[rid] = "✅" if passed is True else ("❌" if passed is False else "⚠️")
                        row["合计"] = f"{det['total']}/{det['max']}"
                        matrix_rows.append(row)
                    cols_order = ["公司"] + [rid for rid, _ in rule_names] + ["合计"]
                    matrix = pd.DataFrame(matrix_rows).reindex(columns=cols_order, fill_value="—")
                    st.dataframe(matrix, use_container_width=True, hide_index=True)
                    if rule_names:
                        with st.expander("规则 ID → 名称对照"):
                            for rid, name in rule_names:
                                st.caption(f"`{rid}` — {name}")
                    st.download_button(
                        "⬇️ 下载 F-Score 矩阵 CSV",
                        matrix.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"compare_fscore_{f_year}.csv",
                        mime="text/csv", key="dl_fscore_matrix",
                    )
        write_context(selected, compare_targets=st.session_state.get("f_targets", []),
                      compare_metric=f"F-Score/{st.session_state.get('f_year', '')}")
    else:
        col_a, col_b = st.columns([1, 2])
        with col_a:
            cmp_module = st.selectbox("模块", list(MODULES.keys()), key="cmp_mod")
            sample_df = next(
                (load_metric(c, cmp_module, DB_MTIME) for c in companies if not load_metric(c, cmp_module, DB_MTIME).empty),
                pd.DataFrame(),
            )
            cmp_metrics = numeric_cols(sample_df)
            cmp_metric = st.selectbox("指标", cmp_metrics, key="cmp_metric") if cmp_metrics else None

            st.markdown("**🏢 对比企业**")
            # B2:同行业自动推荐预设
            peers_l2, ind_l2 = _peers_same_industry(selected, "l2", companies)
            peers_l1, ind_l1 = _peers_same_industry(selected, "l1", companies)
            preset_options = ["自定义", "全 15 家", "前 5 家", "我的持仓"]
            if len(peers_l2) >= 2:
                preset_options.append(f"🌳 同行业 SW2「{ind_l2}」({len(peers_l2)}家)")
            elif len(peers_l1) >= 2:
                preset_options.append(f"🌳 同行业 SW1「{ind_l1}」({len(peers_l1)}家)")
            preset = st.radio(
                "快速预设", preset_options,
                horizontal=True, key="cmp_preset",
                help="选预设会重置下面的多选框。「同行业」基于当前公司的申万分类自动推荐",
            )

            preset_default_map = {
                "全 15 家": list(companies),
                "前 5 家": companies[: min(5, len(companies))],
                "我的持仓": companies[: min(5, len(companies))],
                "自定义": st.session_state.get("cmp_targets", companies[: min(5, len(companies))]),
            }
            if preset.startswith("🌳 同行业 SW2"):
                preset_default = peers_l2
            elif preset.startswith("🌳 同行业 SW1"):
                preset_default = peers_l1
            else:
                preset_default = preset_default_map[preset]

            # B2:同行业推荐补充信息
            if preset.startswith("🌳"):
                lvl = "二级" if "SW2" in preset else "一级"
                ind_name = ind_l2 if "SW2" in preset else ind_l1
                st.caption(f"📍 已自动选入同申万{lvl}「{ind_name}」的 {len(preset_default)} 家")
            else:
                # 即便不选同行业预设,也显示一行"建议"
                if peers_l2 and len(peers_l2) > 1:
                    sug = ", ".join(_load_industry_map().get(f, {}).get("name", f) for f in peers_l2 if f != selected)
                    st.caption(f"💡 建议同行业对比({ind_l2}):{sug}")
                elif peers_l1 and len(peers_l1) > 1:
                    sug = ", ".join(_load_industry_map().get(f, {}).get("name", f) for f in peers_l1 if f != selected)
                    st.caption(f"💡 建议同行业对比({ind_l1},申万一级):{sug}")
                elif _load_industry_map().get(selected):
                    st.caption("💡 当前公司在清单内**无同行业**可比 — 跨行业对比注意指标可比性")

            targets = st.multiselect(
                "选公司(支持多选/搜索)", companies,
                default=preset_default, key="cmp_targets",
            )

            st.markdown("**📊 行业均值**")
            show_industry = st.toggle(
                "叠加行业均值线", value=False, key="cmp_show_industry",
                help="在图上叠加一条粗灰虚线,代表整体行业水平",
            )
            # B3:加"同行业"两档(基于 selected 公司的申万)
            pool_choices = ["当前选中公司", "全 15 家"]
            if peers_l2 and len(peers_l2) >= 2:
                pool_choices.append(f"同 SW2「{ind_l2}」({len(peers_l2)}家)")
            if peers_l1 and len(peers_l1) >= 2 and ind_l1 != ind_l2:
                pool_choices.append(f"同 SW1「{ind_l1}」({len(peers_l1)}家)")
            ind_pool_choice = st.radio(
                "均值口径", pool_choices,
                horizontal=True, disabled=not show_industry, key="cmp_ind_pool",
                help="「同 SW2/SW1」基于当前公司的申万分类自动选同行业公司聚合",
            )
            ind_agg = st.radio(
                "聚合方式", ["中位数", "均值"],
                horizontal=True, disabled=not show_industry, key="cmp_ind_agg",
                help="中位数对极端值更鲁棒(推荐);均值会被龙头/亏损公司拉偏",
            )

            normalize = st.toggle(
                "基准化(=100 起点)", value=False,
                help="把每家公司的首个有效值归一到 100,便于跨量级对比",
            )
        with col_b:
            if not cmp_metrics:
                st.warning("无可对比指标")
            elif targets:
                frames = []
                for c in targets:
                    d = load_metric(c, cmp_module, DB_MTIME)
                    if not d.empty and cmp_metric in d.columns:
                        frames.append(d[["date", cmp_metric]].assign(公司=c))
                if frames:
                    merged = pd.concat(frames, ignore_index=True)

                    # ─── 行业均值线:基于公司池在每个 date 聚合 ──────────
                    industry_label = None
                    if show_industry:
                        # B3:口径 → pool
                        if ind_pool_choice.startswith("同 SW2"):
                            pool = peers_l2
                            pool_tag = f"同 SW2「{ind_l2}」"
                        elif ind_pool_choice.startswith("同 SW1"):
                            pool = peers_l1
                            pool_tag = f"同 SW1「{ind_l1}」"
                        elif ind_pool_choice == "当前选中公司":
                            pool = list(targets)
                            pool_tag = "当前选中"
                        else:
                            pool = list(companies)
                            pool_tag = "全 15 家"

                        if len(pool) < 2:
                            st.caption(f"⚠️ 行业均值口径「{pool_tag}」可比公司不足 2 家,已跳过聚合")
                        else:
                            pool_frames = []
                            for c in pool:
                                d = load_metric(c, cmp_module, DB_MTIME)
                                if not d.empty and cmp_metric in d.columns:
                                    pool_frames.append(d[["date", cmp_metric]].dropna(subset=[cmp_metric]))
                            if pool_frames:
                                big = pd.concat(pool_frames, ignore_index=True)
                                big["date"] = pd.to_datetime(big["date"])
                                agg_func = "median" if ind_agg == "中位数" else "mean"
                                ind_series = big.groupby("date")[cmp_metric].agg(agg_func).reset_index()
                                industry_label = f"📊 {pool_tag} {ind_agg}({len(pool)}家)"
                                ind_series["公司"] = industry_label
                                merged = pd.concat([merged, ind_series], ignore_index=True)

                    if normalize:
                        parts = []
                        for c, g in merged.groupby("公司"):
                            g = g.sort_values("date").dropna(subset=[cmp_metric])
                            if g.empty:
                                continue
                            first = g[cmp_metric].iloc[0]
                            if first and first != 0:
                                g = g.assign(**{cmp_metric: g[cmp_metric] / first * 100})
                            parts.append(g)
                        merged = pd.concat(parts, ignore_index=True) if parts else merged
                        y_label = f"{cmp_metric}(基准 100)"
                    else:
                        y_label = cmp_metric
                    fig = px.line(
                        merged, x="date", y=cmp_metric, color="公司",
                        title=f"{cmp_module} · {y_label}",
                    )
                    # 行业线特殊样式:粗深灰虚线
                    if industry_label:
                        for trace in fig.data:
                            if trace.name == industry_label:
                                trace.update(line=dict(width=3.2, dash="dash", color="#374151"))
                    fig.update_layout(height=480, hovermode="x unified")
                    if normalize:
                        fig.add_hline(y=100, line_dash="dot", line_color="#999",
                                      annotation_text="基准 100")
                    st.plotly_chart(fig, use_container_width=True)

                    latest = (
                        merged.sort_values("date").groupby("公司", as_index=False)
                        .tail(1)[["公司", "date", cmp_metric]].sort_values(cmp_metric, ascending=False)
                    )
                    st.dataframe(latest, use_container_width=True, hide_index=True)
                    st.download_button(
                        "⬇️ 下载对比数据 CSV",
                        merged.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"compare_{cmp_module}_{cmp_metric}.csv",
                        mime="text/csv", key="dl_compare",
                    )
        if cmp_metrics:
            write_context(selected, compare_targets=targets, compare_metric=f"{cmp_module}/{cmp_metric}")

    # ─── 区块 C-3:🏭 行业横评(Phase B2/B3)─────────────────────────
    _icv = globals().get("icv")
    if selected_ticker and _icv is not None:
        st.divider()
        try:
            _icv.render_industry_compare(selected_ticker, score_dict["name"] if score_dict else selected)
        except Exception as _icv_e:
            st.caption(f"⚠️ 行业横评渲染失败:{_icv_e}")

    # ═══ 区块 D · 决策档案 ═══
    st.markdown(
        _section_banner("D", "📁", "决策档案", "决策时间线 · 投资决策 · 券商研报 · 财报"),
        unsafe_allow_html=True,
    )

    # ─── 区块 D-1:本公司决策时间线(原 区块 B 内 expander 挪过来)──
    if selected_ticker:
        with st.expander("🕒 本公司决策时间线", expanded=False):
            if dt is None:
                st.info("decision_timeline 模块未加载")
            elif decisions_db is None:
                st.info("decisions_db 不可用")
            else:
                ds = dt.load_decisions(selected_ticker)
                if not ds:
                    st.info(f"{selected} 暂无决策记录 — 点顶部「➕ 一键补录决策」开始")
                else:
                    prices_df = load_prices(selected_ticker, DB_MTIME)
                    fig_tl = dt.timeline_chart(ds, price_df=prices_df if not prices_df.empty else None)
                    if fig_tl is not None:
                        st.plotly_chart(fig_tl, use_container_width=True)
                    st.dataframe(dt.render_summary_table(ds), hide_index=True, use_container_width=True)

    # ─── 区块 D-2:投资决策 / 券商研报 / 财报 PDF — 3 列并排全宽 ───
    doc_col_decision, doc_col_broker, doc_col_report = st.columns(3, gap="medium")
    with doc_col_decision:
        st.markdown("##### 📝 投资决策")
        decisions = list_decision_docs(selected)
        if not decisions:
            st.caption("(暂无决策文档)")
        else:
            for p in decisions:
                rel = p.relative_to(COMPANIES_DIR / selected)
                with st.expander(str(rel), expanded=False):
                    try:
                        body = p.read_text(encoding="utf-8")
                        st.markdown(body[:4000] + ("\n\n... (截断,完整见源文件)" if len(body) > 4000 else ""))
                    except Exception as e:
                        st.error(f"读取失败:{e}")

    with doc_col_broker:
        st.markdown("##### 🏦 券商研报")
        broker = list_broker_docs(selected)
        if not broker:
            st.caption("(暂无)")
        else:
            for p in broker[:8]:
                st.caption(f"`{p.relative_to(COMPANIES_DIR / selected)}`")

    with doc_col_report:
        st.markdown("##### 📄 财报 PDF")
        reports = list_reports(selected)
        if not reports:
            st.caption("(暂无 PDF)")
        else:
            st.caption(f"共 {len(reports)} 份 · 最新:")
            for p in reports[:5]:
                st.caption(f"• {p.name}")
