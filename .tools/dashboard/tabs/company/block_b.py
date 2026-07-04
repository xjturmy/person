"""区块 B · 同行业比较:结论 + 同行雷达。"""
from __future__ import annotations

from html import escape

from ._helpers import _section_banner


def _score_value(score) -> float | None:
    try:
        if score is None:
            return None
        return float(score)
    except (TypeError, ValueError):
        return None


def _dim_score(score, key: str) -> float | None:
    try:
        return _score_value(score.dims.get(key).score)
    except Exception:
        return None


def _comparison_tag(delta: float | None) -> tuple[str, str, str]:
    if delta is None:
        return "⚪", "暂无足够同行数据", "#6B7280"
    if delta >= 8:
        return "🟢", "整体高于同行均值", "#16A34A"
    if delta >= 3:
        return "🟢", "略高于同行均值", "#16A34A"
    if delta > -3:
        return "🟡", "整体接近同行均值", "#CA8A04"
    if delta > -8:
        return "🟠", "略低于同行均值", "#EA580C"
    return "🔴", "整体低于同行均值", "#DC2626"


def _peer_comparison_html(scores: list, self_ticker: str) -> str:
    self_score = next((s for s in scores if str(s.ticker) == str(self_ticker)), None)
    peers = [s for s in scores if str(s.ticker) != str(self_ticker)]
    if self_score is None or not peers:
        return (
            '<div style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px;'
            'padding:12px 13px;color:#6B7280;font-size:13px;">同行比较暂不可用:缺少本公司或同行评分。</div>'
        )

    self_overall = _score_value(getattr(self_score, "overall", None))
    peer_overalls = [_score_value(getattr(p, "overall", None)) for p in peers]
    peer_overalls = [v for v in peer_overalls if v is not None]
    peer_avg = sum(peer_overalls) / len(peer_overalls) if peer_overalls else None
    delta = self_overall - peer_avg if self_overall is not None and peer_avg is not None else None
    icon, verdict, color = _comparison_tag(delta)

    dim_deltas: list[tuple[str, float]] = []
    for key in pr.DIM_ORDER if pr is not None else SCORE_DIM_ORDER:
        self_dim = _dim_score(self_score, key)
        peer_vals = [_dim_score(p, key) for p in peers]
        peer_vals = [v for v in peer_vals if v is not None]
        if self_dim is None or not peer_vals:
            continue
        dim_deltas.append((sc.DIM_LABEL.get(key, key), self_dim - sum(peer_vals) / len(peer_vals)))
    lead = max(dim_deltas, key=lambda x: x[1], default=("—", 0.0))
    lag = min(dim_deltas, key=lambda x: x[1], default=("—", 0.0))
    lead_text = f"{lead[0]} {lead[1]:+.1f}" if lead[1] > 1 else "无明显领先维度"
    lag_text = f"{lag[0]} {lag[1]:+.1f}" if lag[1] < -1 else "无明显短板"
    delta_text = "—" if delta is None else f"{delta:+.1f} 分"
    peer_text = "—" if peer_avg is None else f"{peer_avg:.1f}"
    self_text = "—" if self_overall is None else f"{self_overall:.1f}"

    return (
        '<div style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:8px;'
        'padding:13px 14px;margin:8px 0 12px 0;font-family:-apple-system,Inter,PingFang SC,sans-serif;">'
        '<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">'
        '<div>'
        '<div style="font-size:12px;color:#6B7280;font-weight:700;">雷达图读法</div>'
        f'<div style="font-size:22px;font-weight:860;color:#111827;line-height:1.25;margin-top:4px;">'
        f'{escape(icon)} {escape(verdict)}</div>'
        '<div style="font-size:12px;color:#6B7280;margin-top:5px;">只说明相对同行的位置,不代表买卖判断。</div>'
        '</div>'
        f'<div style="font-size:12px;color:#6B7280;text-align:right;">本公司 {escape(self_text)} / 同行均值 {escape(peer_text)}'
        f'<br><span style="font-weight:800;color:{color};">{escape(delta_text)}</span></div>'
        '</div>'
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px;">'
        '<div style="background:#F9FAFB;border:1px solid #EEF2F7;border-radius:7px;padding:8px;">'
        '<div style="font-size:11px;color:#6B7280;">相对优势</div>'
        f'<div style="font-size:13px;font-weight:760;color:#111827;margin-top:2px;">{escape(lead_text)}</div>'
        '</div>'
        '<div style="background:#F9FAFB;border:1px solid #EEF2F7;border-radius:7px;padding:8px;">'
        '<div style="font-size:11px;color:#6B7280;">相对短板</div>'
        f'<div style="font-size:13px;font-weight:760;color:#111827;margin-top:2px;">{escape(lag_text)}</div>'
        '</div>'
        '</div>'
        '</div>'
    )


def _peer_radar_notes_html(scores: list, self_ticker: str) -> str:
    self_score = next((s for s in scores if str(s.ticker) == str(self_ticker)), None)
    peers = [s for s in scores if str(s.ticker) != str(self_ticker)]
    if self_score is None or not peers:
        return ""

    rows: list[tuple[str, float, float, float]] = []
    for key in pr.DIM_ORDER if pr is not None else SCORE_DIM_ORDER:
        self_dim = _dim_score(self_score, key)
        peer_vals = [_dim_score(p, key) for p in peers]
        peer_vals = [v for v in peer_vals if v is not None]
        if self_dim is None or not peer_vals:
            continue
        peer_avg = sum(peer_vals) / len(peer_vals)
        rows.append((sc.DIM_LABEL.get(key, key), self_dim, peer_avg, self_dim - peer_avg))

    strengths = [r for r in sorted(rows, key=lambda x: x[3], reverse=True) if r[3] > 1][:2]
    watches = [r for r in sorted(rows, key=lambda x: x[3]) if r[3] < -1][:2]

    def _items(items: list[tuple[str, float, float, float]], empty: str) -> str:
        if not items:
            return f'<div style="color:#6B7280;font-size:12px;line-height:1.45;">{escape(empty)}</div>'
        return "".join(
            '<div style="display:flex;justify-content:space-between;gap:10px;'
            'padding:5px 0;border-top:1px solid #EEF2F7;">'
            f'<span style="font-size:12px;color:#111827;font-weight:720;">{escape(label)}</span>'
            f'<span style="font-size:12px;color:#2563EB;font-weight:760;">本公司 {self_v:.0f} / 同行 {peer_v:.0f}</span>'
            '</div>'
            for label, self_v, peer_v, _delta in items
        )

    return (
        '<div style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:8px;'
        'padding:12px 13px;font-family:-apple-system,Inter,PingFang SC,sans-serif;">'
        '<div style="font-size:12px;color:#6B7280;font-weight:760;">雷达图怎么看</div>'
        '<div style="font-size:18px;font-weight:850;color:#111827;margin:4px 0 10px;">主要优势</div>'
        f'{_items(strengths, "没有明显领先同行的维度。")}'
        '<div style="font-size:18px;font-weight:850;color:#111827;margin:14px 0 10px;">需要留意</div>'
        f'{_items(watches, "没有明显落后同行的维度。")}'
        '<div style="font-size:12px;color:#6B7280;line-height:1.45;margin-top:12px;'
        'background:#F8FAFC;border:1px solid #EEF2F7;border-radius:7px;padding:8px;">'
        '读图方式:蓝色是本公司,虚线是同行。离外圈越近表示该维度相对越强;这里只看同行位置,不替代 A 区买卖判断。'
        '</div>'
        '</div>'
    )


def render() -> None:
    st.markdown('<div id="block-b"></div>', unsafe_allow_html=True)
    folder_to_ticker_local = _folder_to_ticker(DB_MTIME)
    selected_ticker = folder_to_ticker_local.get(selected, "")

    st.markdown(
        _section_banner(
            "B", "🤝", "同行业比较",
            "同行雷达 · 相对优势 · 相对短板",
        ),
        unsafe_allow_html=True,
    )

    if selected_ticker:
        if pr is None:
            st.info("peer_radar 模块未加载")
            return
        ps = peer_scores(selected_ticker, DB_MTIME, max_n=4)
        if not ps:
            st.info("同行评分计算失败")
        elif len(ps) <= 1:
            st.info("暂无同细分行业同行。请先刷新同行数据后再显示雷达对比。")
        else:
            st.markdown(_peer_comparison_html(ps, selected_ticker), unsafe_allow_html=True)
            note_col, radar_col = st.columns([0.88, 1.45], gap="medium")
            with note_col:
                st.markdown(_peer_radar_notes_html(ps, selected_ticker), unsafe_allow_html=True)
            with radar_col:
                st.plotly_chart(
                    pr.peer_radar_chart(ps, selected_ticker, height=430),
                    width="stretch",
                )
            st.caption(pr.peer_group_label(selected_ticker, max_n=4))
