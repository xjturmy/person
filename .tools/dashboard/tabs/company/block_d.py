"""区块 D · 决策档案:决策时间线 + 投资决策 / 券商研报 / 财报 PDF 三列。"""
from __future__ import annotations

from ._helpers import _section_banner


def render() -> None:
    st.markdown('<div id="block-d"></div>', unsafe_allow_html=True)
    folder_to_ticker_local = _folder_to_ticker(DB_MTIME)
    selected_ticker = folder_to_ticker_local.get(selected, "")

    # ═══ 区块 D · 决策档案 ═══
    st.markdown(
        _section_banner("D", "📁", "决策档案", "决策时间线 · 投资决策 · 券商研报 · 财报"),
        unsafe_allow_html=True,
    )

    # ─── 📝 记此决策 — 跳转决策中心并预填当前价 ─────────────────
    try:
        from navigation import goto, PAGE_DC, SUB_DC_LOG
        col_btn, col_hint = st.columns([1, 4])
        with col_btn:
            if st.button("📝 记此决策", key="block_d_to_dc",
                         help="跳到决策中心 · 自动预填公司 + 当前价 + 理由模板"):
                _cur_price = None
                try:
                    from valuation.price_range import compute_next_quarter_range
                    _pr = compute_next_quarter_range(selected_ticker)
                    _cur_price = _pr.current_price
                except Exception:
                    _cur_price = None
                _prefill = {
                    "reason_template": f"[来自公司研究 · {selected}] ",
                }
                if _cur_price is not None:
                    try:
                        _prefill["price"] = float(_cur_price)
                    except (TypeError, ValueError):
                        pass
                goto(PAGE_DC, company=selected, sub_tab=SUB_DC_LOG, prefill=_prefill)
        with col_hint:
            st.caption("跳到决策中心 · 自动带入当前价与公司,补 rationale 即可保存。")
    except Exception as _btn_exc:
        st.caption(f"(📝 记此决策 不可用:{_btn_exc})")

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
