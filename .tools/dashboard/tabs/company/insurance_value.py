"""公司研究 · 保险价值修复法子模块。"""
from __future__ import annotations

import sys
from datetime import date as _date_cls
from pathlib import Path


def _next_report_window(today: _date_cls | None = None) -> tuple[str, _date_cls]:
    today = today or _date_cls.today()
    y = today.year
    if today <= _date_cls(y, 4, 30):
        return f"{y}Q1/年报", _date_cls(y, 4, 30)
    if today <= _date_cls(y, 8, 31):
        return f"{y}中报", _date_cls(y, 8, 31)
    if today <= _date_cls(y, 10, 31):
        return f"{y}Q3", _date_cls(y, 10, 31)
    return f"{y + 1}Q1/年报", _date_cls(y + 1, 4, 30)


def is_insurance_company(ticker: str, name: str = "") -> bool:
    if "保险" in (name or ""):
        return True
    if not ticker:
        return False
    ticker6 = ticker.strip()[:6]
    try:
        con = get_conn(str(DB_PATH))
        row = con.execute(
            """
            SELECT category, name
            FROM companies
            WHERE ticker = ?
            LIMIT 1
            """,
            [ticker6],
        ).fetchone()
    except Exception:
        return False
    if not row:
        return False
    text = " ".join(str(x or "") for x in row)
    return "insurance" in text.lower() or "保险" in text


def render_price_range(ticker: str, name: str) -> bool:
    """保险公司返回 True 并渲染专属价格区间;非保险返回 False。"""
    if not is_insurance_company(ticker, name):
        return False
    ticker6 = ticker.strip()[:6]

    dashboard_dir = Path(__file__).resolve().parents[2]
    if str(dashboard_dir) not in sys.path:
        sys.path.insert(0, str(dashboard_dir))
    try:
        from valuation.insurance_value import compute_insurance_value_range, format_price
    except Exception as exc:
        st.caption(f"⚠️ 保险估值模块加载失败:{exc}")
        return True

    rng = compute_insurance_value_range(ticker6, name=name)
    window_label, deadline = _next_report_window()

    st.markdown("---")
    st.markdown("### 🛡️ 保险价值修复价格区间")
    st.caption(
        f"参考窗口:今天至 {deadline:%Y-%m-%d}({window_label} 披露前后)。"
        "本模块只用于保险公司:PB 历史估值带给价格纪律,EV/NBV 做第二层校验。"
    )

    if not rng.verified:
        st.info(f"{rng.verdict_label} · {rng.note}")
        return True

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("当前价", format_price(rng.current_price))
    col2.metric("买入线", f"≤ {format_price(rng.buy_price)}")
    col3.metric("合理中枢", format_price(rng.fair_price))
    col4.metric("减仓/卖出线", f"≥ {format_price(rng.sell_price)}")

    st.info(f"{rng.verdict_label} · {rng.note}")

    metric_cols = st.columns(4)
    metric_cols[0].metric("当前 PB", f"{rng.pb:.2f}" if rng.pb is not None else "—")
    metric_cols[1].metric("PB 10y P20", f"{rng.pb_p20:.2f}" if rng.pb_p20 is not None else "—")
    metric_cols[2].metric("PB 10y 中位", f"{rng.pb_median:.2f}" if rng.pb_median is not None else "—")
    metric_cols[3].metric("PB 10y P80", f"{rng.pb_p80:.2f}" if rng.pb_p80 is not None else "—")

    ev_cols = st.columns(3)
    ev_cols[0].metric("P/EV", f"{rng.p_ev:.2f}" if rng.p_ev is not None else "—")
    ev_cols[1].metric("内含价值 EV", _fmt_amount(rng.embedded_value))
    ev_cols[2].metric("新业务价值 NBV", _fmt_amount(rng.new_business_value))

    foot = []
    if rng.roe is not None:
        foot.append(f"ROE {rng.roe * 100:.1f}%")
    if rng.dividend_yield is not None:
        dy = rng.dividend_yield * 100 if rng.dividend_yield <= 1 else rng.dividend_yield
        foot.append(f"股息率 {dy:.2f}%")
    if rng.as_of is not None:
        foot.append(f"数据日 {rng.as_of}")
    if foot:
        st.caption(" ｜ ".join(foot))
    for detail in rng.details:
        st.caption(detail)
    return True


def render_page(ticker: str, name: str) -> None:
    """公司研究顶层子 tab:保险公司专属评估页。"""
    st.subheader("🛡️ 保险价值修复法")
    if not is_insurance_company(ticker, name):
        st.info("当前公司不是保险公司,此方法不适用。")
        return
    render_price_range(ticker, name)
    _render_peer_compare(ticker, name)
    st.markdown("#### 后续需要补齐的数据")
    st.caption("新业务价值增速、综合偿付能力充足率、核心偿付能力充足率、投资收益率。")


def _fmt_pct(v: float | None, digits: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.{digits}f}%" if abs(v) <= 1 else f"{v:.{digits}f}%"


def _fmt_num(v: float | None, digits: int = 2) -> str:
    return "—" if v is None else f"{v:.{digits}f}"


def _fmt_amount(v: float | None) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1e8:
        return f"{v / 1e8:,.0f}亿"
    return f"{v:,.0f}"


def _render_peer_compare(ticker: str, name: str) -> None:
    dashboard_dir = Path(__file__).resolve().parents[2]
    if str(dashboard_dir) not in sys.path:
        sys.path.insert(0, str(dashboard_dir))
    try:
        import pandas as pd
        from valuation.insurance_value import compare_insurance_peers, format_price
    except Exception as exc:
        st.caption(f"⚠️ 保险同行比较加载失败:{exc}")
        return

    rows = compare_insurance_peers(ticker, name=name, peer_limit=3)
    st.markdown("#### 同业横评 · 新华保险 vs 3 个保险同行")
    st.caption("初筛逻辑:低于自身 PB 历史中位越多越便宜;ROE/PB 越高代表每单位估值买到的盈利能力越强。")

    data = []
    for r in rows:
        data.append({
            "公司": r.name,
            "当前价": format_price(r.current_price),
            "买入线": format_price(r.buy_price),
            "合理中枢": format_price(r.fair_price),
            "卖出线": format_price(r.sell_price),
            "PB": _fmt_num(r.pb),
            "PB vs 10y中位": _fmt_pct(r.pb_discount_pct),
            "P/EV": _fmt_num(r.p_ev),
            "NBV": _fmt_amount(r.new_business_value),
            "ROE": _fmt_pct(r.roe),
            "股息率": _fmt_pct(r.dividend_yield, 2),
            "ROE/PB": _fmt_num(r.roe_to_pb, 3),
            "位置": r.verdict_label.replace("🟢 ", "").replace("🟡 ", "").replace("🔴 ", ""),
            "初筛分": _fmt_num(r.score, 3),
        })
    st.dataframe(pd.DataFrame(data), width="stretch", hide_index=True)

    ranked = [r for r in rows if r.score is not None]
    ranked.sort(key=lambda r: r.score or -999, reverse=True)
    if ranked:
        leader = ranked[0]
        selected = next((r for r in ranked if r.ticker == ticker.strip()[:6]), None)
        if selected and leader.ticker == selected.ticker:
            st.success(f"按当前 PB/ROE/股息初筛,{selected.name} 暂时排在这组保险股前列。")
        elif selected:
            st.info(
                f"按当前 PB/ROE/股息初筛,{leader.name} 更靠前;"
                f"{selected.name} 的优势需要由 NBV 修复、偿付能力和投资收益率进一步证明。"
            )
        else:
            st.info(f"按当前 PB/ROE/股息初筛,{leader.name} 暂时更靠前。")
    st.caption("可信度:PB/ROE/股息/EV/NBV 已有理杏仁数据,适合做同业初筛;保险最终结论仍需补偿付能力与投资收益率。")


__all__ = ["is_insurance_company", "render_page", "render_price_range"]
