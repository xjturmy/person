"""区块 A · 看结论:雪花 + 同行业建议卡 + 优势/短板 Top3 + 一句话定位。"""
from __future__ import annotations

from html import escape
import sys
from pathlib import Path

from ._helpers import _dim_explanation, _load_industry_map


def render() -> None:
    st.markdown('<div id="block-a"></div>', unsafe_allow_html=True)
    # ═══ 区块 A · 看结论(雪花 + 优势短板)═══
    st.markdown(
        '<div style="margin:18px 0 8px 0;">'
        '<span style="font-size:13px;font-weight:800;color:#2563EB;">区块 A</span>'
        '<span style="margin-left:10px;font-size:17px;font-weight:850;color:#111827;">🎯 一眼看结论</span>'
        '<span style="margin-left:10px;font-size:12px;color:#6B7280;">雪花图 · 优势短板 · 一句话定位</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    folder_to_ticker_local = _folder_to_ticker(DB_MTIME)
    selected_ticker = folder_to_ticker_local.get(selected, "")

    _adv = None
    if selected_ticker:
        try:
            _here = str(Path(__file__).resolve().parents[1])
            if _here not in sys.path:
                sys.path.insert(0, _here)
            import peers.advisor as _pa
            _adv = _pa.advise(selected_ticker, name=selected)
        except Exception as _pa_e:
            st.caption(f"⚠️ 同行建议引擎调用失败:{_pa_e}")

    # ─── V8 顶部:综合评分 + 雪花图(SWS 风格)+ 股价叠加全局 toggle ─
    score = company_score(selected_ticker, DB_MTIME) if selected_ticker else None
    head_left, head_mid = st.columns([1.02, 1.35], vertical_alignment="center")
    with head_left:
        st.markdown(_conclusion_panel_html(selected, score, _adv), unsafe_allow_html=True)
    with head_mid:
        if score is not None:
            st.plotly_chart(render_radar(score, height=280), width="stretch")
            st.markdown(
                '<div style="margin-top:-8px;font-size:11px;color:#9CA3AF;">'
                '六维:估值 / 盈利 / 成长 / 现金流 / 安全 / 策略'
                '</div>',
                unsafe_allow_html=True,
            )
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

        st.markdown(_top_bottom_html(top, bot), unsafe_allow_html=True)

        if top and bot:
            t_label, _, _, t_note, _ = top[0]
            b_label, _, _, b_note, _ = bot[0]
            if t_label != b_label:
                st.markdown(
                    _insight_footer_html(
                        t_label,
                        t_note.split("·")[0].strip() if t_note else "—",
                        b_label,
                        b_note.split("·")[0].strip() if b_note else "—",
                    ),
                    unsafe_allow_html=True,
                )

def _conclusion_panel_html(selected_folder: str, score, advice) -> str:
    imap = _load_industry_map()
    meta = imap.get(selected_folder, {})
    industry = meta.get("industry_l2") or meta.get("industry") or "—"
    badge = str(getattr(score, "overall_badge", "") or "⚪")
    score_value = getattr(score, "overall", None)
    score_line = f"{score_value:.1f} / 100" if score_value is not None else "评分不可用"
    score_width = max(0, min(100, float(score_value or 0)))
    if score_value is None:
        score_color = "#6B7280"
    elif score_value >= 75:
        score_color = "#16A34A"
    elif score_value >= 60:
        score_color = "#CA8A04"
    else:
        score_color = "#DC2626"
    conclusion = "暂无同行结论"
    peer_line = f"{industry}"
    peer_meta = "行业资料"
    if advice is not None and getattr(advice, "n_peers", 0) > 0:
        conclusion = f"{advice.overall_emoji} {advice.overall_label} · 综合{advice.quality_label}"
        peer_line = f"「{advice.industry}」{advice.n_peers} 家"
        peer_meta = "同行样本"

    return (
        '<div style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:8px;'
        'padding:14px 14px 13px 14px;margin:0 0 10px 0;'
        'box-shadow:0 1px 2px rgba(15,23,42,.04);font-family:-apple-system,Inter,'
        'PingFang SC,sans-serif;">'
        '<div style="font-size:12px;color:#6B7280;">当前结论</div>'
        f'<div style="font-size:22px;font-weight:860;color:#111827;line-height:1.25;margin-top:2px;">{escape(conclusion)}</div>'
        '<div style="margin-top:12px;">'
        '<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">'
        '<span style="font-size:12px;color:#6B7280;">综合评分</span>'
        f'<span style="font-size:13px;font-weight:800;color:{score_color};">{escape(badge)} {escape(score_line)}</span>'
        '</div>'
        '<div style="height:7px;background:#EEF2F7;border-radius:999px;margin-top:6px;overflow:hidden;">'
        f'<div style="height:100%;width:{score_width:.0f}%;background:{score_color};border-radius:999px;"></div>'
        '</div>'
        '</div>'
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px;">'
        '<div style="background:#F9FAFB;border:1px solid #EEF2F7;border-radius:7px;padding:8px;">'
        '<div style="font-size:11px;color:#6B7280;">行业</div>'
        f'<div style="font-size:13px;font-weight:760;color:#111827;margin-top:2px;">{escape(str(industry))}</div>'
        '</div>'
        '<div style="background:#F9FAFB;border:1px solid #EEF2F7;border-radius:7px;padding:8px;">'
        f'<div style="font-size:11px;color:#6B7280;">{escape(peer_meta)}</div>'
        f'<div style="font-size:13px;font-weight:760;color:#111827;margin-top:2px;">{escape(peer_line)}</div>'
        '</div>'
        '</div>'
        '</div>'
    )


def _insight_footer_html(top_label: str, top_note: str, bot_label: str, bot_note: str) -> str:
    return (
        '<div style="display:flex;align-items:center;justify-content:space-between;gap:14px;'
        'margin:10px 0 4px 0;padding:10px 12px;background:#F8FAFC;border:1px solid #E5E7EB;'
        'border-radius:8px;font-family:-apple-system,Inter,PingFang SC,sans-serif;">'
        '<div style="min-width:0;">'
        '<span style="font-size:12px;font-weight:780;color:#2563EB;margin-right:8px;">一句话定位</span>'
        f'<span style="font-size:13px;color:#111827;">强项: <b>{escape(top_label)}</b>'
        f'<span style="color:#6B7280;">({escape(top_note)})</span>'
        f' · 待验证: <b>{escape(bot_label)}</b>'
        f'<span style="color:#6B7280;">({escape(bot_note)})</span></span>'
        '</div>'
        '<a href="#block-c" style="flex:0 0 auto;font-size:12px;font-weight:760;color:#2563EB;'
        'text-decoration:none;">看同行横评 -></a>'
        '</div>'
    )


def _top_bottom_html(top: list[tuple], bot: list[tuple]) -> str:
    def _score_color(val: float) -> tuple[str, str]:
        if val >= 75:
            return "#16A34A", "🟢"
        if val >= 55:
            return "#CA8A04", "🟡"
        if val >= 35:
            return "#EA580C", "🟠"
        return "#DC2626", "🔴"

    def _items(rows: list[tuple]) -> str:
        out = []
        for label, val, _badge, note, raw in rows:
            explain = _dim_explanation(label, raw, val)
            note_text = (note or "").split("·")[0].strip()
            detail = explain or note_text or "—"
            color, dot = _score_color(float(val))
            out.append(
                '<div style="display:grid;grid-template-columns:82px 1fr;gap:8px;'
                'align-items:start;padding:7px 0;border-top:1px solid #EEF2F7;">'
                f'<div style="font-weight:750;color:#111827;">{dot} {escape(str(label))}</div>'
                '<div>'
                f'<span style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;'
                f'font-size:12px;color:{color};background:#F9FAFB;border-radius:5px;'
                f'padding:2px 5px;">{float(val):.0f}/100</span>'
                f'<span style="margin-left:8px;color:#6B7280;font-size:12px;">{escape(note_text)}</span>'
                f'<div style="color:#4B5563;font-size:12px;line-height:1.45;margin-top:4px;">{escape(detail)}</div>'
                '</div></div>'
            )
        return "".join(out)

    return (
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin:6px 0 4px 0;">'
        '<div>'
        '<div style="font-weight:800;font-size:15px;margin-bottom:2px;color:#111827;">优势 Top3</div>'
        f'{_items(top)}'
        '</div>'
        '<div>'
        '<div style="font-weight:800;font-size:15px;margin-bottom:2px;color:#111827;">相对短板 Top3</div>'
        f'{_items(bot)}'
        '</div>'
        '</div>'
    )
