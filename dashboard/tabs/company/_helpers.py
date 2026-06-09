"""Shared helpers / constants / cached path roots for tabs/company sub-package."""
from __future__ import annotations

from importlib.machinery import SourceFileLoader
from pathlib import Path

# 路径常量(原 tabs/company.py 里的 _THIS 指向 tabs/;
# 现在文件位于 tabs/company/,所以 _TABS = parents[1])
_THIS = Path(__file__).resolve().parents[1]  # 兼容原代码语义:tabs/
_DASH = Path(__file__).resolve().parents[2]  # dashboard/
_PRESON = Path(__file__).resolve().parents[4]  # preson/


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


_INDUSTRY_MAP = None


def _load_industry_map() -> dict:
    """从 .config/companies.csv 读 (folder → {industry, industry_l2, ticker, name})。
    缓存在模块级,避免重复读。"""
    global _INDUSTRY_MAP
    if _INDUSTRY_MAP is not None:
        return _INDUSTRY_MAP
    import pandas as _pd
    csv = _PRESON / ".config" / "companies.csv"
    try:
        df = _pd.read_csv(csv, dtype={"stock": str})
        out = {}
        for _, r in df.iterrows():
            out[str(r["folder"])] = {
                "ticker": str(r["stock"]),
                "name":   str(r.get("name", "")),
                "category":     str(r.get("category", "") or ""),
                "industry":     str(r.get("industry", "") or ""),
                "industry_l2":  str(r.get("industry_l2", "") or ""),
            }
        _INDUSTRY_MAP = out
        return out
    except Exception:
        _INDUSTRY_MAP = {}
        return {}


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
