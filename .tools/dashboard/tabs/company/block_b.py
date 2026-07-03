"""区块 B · 大师评分体系:多大师矩阵 + 投票 + 哲学速读 + 同行雷达。"""
from __future__ import annotations

from ._helpers import _section_banner


def render() -> None:
    st.markdown('<div id="block-b"></div>', unsafe_allow_html=True)
    folder_to_ticker_local = _folder_to_ticker(DB_MTIME)
    selected_ticker = folder_to_ticker_local.get(selected, "")

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
        st.caption("查看估值依据 ➡ [Block A 价格区间](#block-a)")

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
                        width="stretch",
                    )
                    st.caption(f"同 category 同行({len(ps)-1} 家):" + ", ".join(s.name for s in ps if s.ticker != selected_ticker))
