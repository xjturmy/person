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
    head_left, head_mid = st.columns([0.82, 1.55], vertical_alignment="center")
    with head_left:
        st.markdown(_conclusion_panel_html(selected, score, _adv), unsafe_allow_html=True)
    with head_mid:
        if score is not None:
            st.plotly_chart(render_radar(score, height=280), width="stretch")
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

        # 一句话定位
        if top and bot:
            t_label, _, _, t_note, _ = top[0]
            b_label, _, _, b_note, _ = bot[0]
            if t_label != b_label:
                st.caption(
                    f"💡 一句话定位:**{t_label}** 极强({t_note.split('·')[0].strip() if t_note else '—'})"
                    f",**{b_label}** 偏弱({b_note.split('·')[0].strip() if b_note else '—'})"
                )

        st.caption("横向对比同行 ➡ [Block C 行业横评](#block-c)")

    # ─── 区块 A 收尾:🎯 下季度合理价格区间(多模型加权)─────────────
    if selected_ticker:
        if insurance_value.render_price_range(selected_ticker, selected):
            return
        _render_price_range_card(selected_ticker, selected)


def _category_label(category: str | None) -> str:
    labels = {
        "non_financial": "普通非金融公司",
        "bank": "银行",
        "insurance": "保险",
        "hk": "港股",
    }
    key = str(category or "").strip().lower()
    return labels.get(key, key or "未分类")


def _conclusion_panel_html(selected_folder: str, score, advice) -> str:
    imap = _load_industry_map()
    meta = imap.get(selected_folder, {})
    industry = meta.get("industry_l2") or meta.get("industry") or "—"
    badge = str(getattr(score, "overall_badge", "") or "⚪")
    score_value = getattr(score, "overall", None)
    score_line = f"{score_value:.1f} / 100" if score_value is not None else "评分不可用"
    conclusion = "暂无同行结论"
    peer_line = f"{industry}"
    if advice is not None and getattr(advice, "n_peers", 0) > 0:
        conclusion = f"{advice.overall_emoji} {advice.overall_label} · 综合{advice.quality_label}"
        peer_line = f"「{advice.industry}」{advice.n_peers} 家"

    return (
        '<div style="font-size:14px;line-height:1.9;color:#111827;margin:2px 0 10px 0;">'
        f'<div>结论：{escape(conclusion)}</div>'
        f'<div>评分：{escape(badge)} {escape(score_line)}</div>'
        f'<div>同行：{escape(peer_line)}</div>'
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


def _render_price_range_card(ticker: str, name: str) -> None:
    """渲染下季度合理价格区间卡:三模型公允价 + 区间标尺 + verdict。"""
    # 优先读预计算 bundle.price_range(<5ms);缺失降级 live 计算。
    pr = None
    try:
        import analytics_store as _store
        pr = _store.price_range(ticker)
    except Exception:
        pr = None

    # lynch_type 在 if 块外(下方 caption)也会引用,必须无条件初始化,
    # 否则走预计算分支(pr 非 None)时 lynch_type 未定义 → UnboundLocalError。
    lynch_type = None
    if pr is None:
        try:
            from valuation.price_range import compute_next_quarter_range
        except Exception as e:
            st.caption(f"⚠️ price_range 加载失败:{e}")
            return
        # 取 lynch_type 用于权重 — 只算当前这一家(按 mtime 缓存),
        # 不再对全市场跑 score_lynch_classifier_all(load_all())(实测 17.5s)。
        try:
            from masters.lynch.classifier import lynch_type_of
            lynch_type = lynch_type_of(ticker, DB_MTIME)
        except Exception:
            pass
        pr = compute_next_quarter_range(ticker, name=name, lynch_type=lynch_type)

    st.markdown("---")
    st.markdown("### 🎯 下季度合理价格区间")
    st.caption(
        "三模型加权聚合:Graham(账面安全) · PEG=1(成长公允) · Gordon DDM(股息折现)。"
        + (f" · 林奇分类:`{lynch_type}`" if lynch_type else " · 林奇分类:未知,使用等权")
    )

    if pr.floor is None or pr.ceiling is None:
        st.warning(f"{pr.verdict_label}({'; '.join(pr.notes) or '三模型均不可得'})")
        return

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📉 下沿 floor", f"¥{pr.floor:,.2f}", help="三模型公允价最小值")
    col2.metric("🎯 中枢 mid", f"¥{pr.mid:,.2f}", help="按林奇分类加权后的目标价")
    col3.metric("📈 上沿 ceiling", f"¥{pr.ceiling:,.2f}", help="三模型公允价最大值")
    if pr.current_price is not None:
        deviation = (pr.current_price - pr.mid) / pr.mid * 100
        col4.metric("当前价",
                    f"¥{pr.current_price:,.2f}",
                    delta=f"{deviation:+.1f}% vs 中枢",
                    delta_color="inverse")
    else:
        col4.metric("当前价", "—")

    # 一句话 verdict
    if pr.current_price is not None:
        st.markdown(
            f"#### {pr.verdict_label} · 当前 ¥{pr.current_price:.2f} ∈ "
            f"[¥{pr.floor:.2f}, ¥{pr.ceiling:.2f}]"
        )

    # 三模型明细表
    import pandas as _pd
    rows = []
    for m in pr.models:
        rows.append({
            "模型": m.name,
            "公允价": f"¥{m.fair_price:,.2f}" if m.fair_price is not None else "—",
            "权重": f"{m.weight*100:.0f}%" if m.weight > 0 else "—",
            "校验": "✓" if m.verified else "—",
            "说明": m.note,
        })
    st.dataframe(_pd.DataFrame(rows), width="stretch", hide_index=True)

    if pr.notes:
        with st.expander("⚠️ 降级说明"):
            for n in pr.notes:
                st.caption("• " + n)
