"""区块 C · 数据深挖:6 维子 Tab + PEG + K 线 + ETF + 行业 PE + 横向对比 + 行业横评。"""
from __future__ import annotations

from importlib.machinery import SourceFileLoader

from ._helpers import (
    _THIS,
    _section_banner,
    _load_industry_map,
    _peers_same_industry,
)
from ui.chart_meta import render_chart_meta
from ui.table_view import render_smart_dataframe


def render() -> None:
    folder_to_ticker_local = _folder_to_ticker(DB_MTIME)
    selected_ticker = folder_to_ticker_local.get(selected, "")
    score = company_score(selected_ticker, DB_MTIME) if selected_ticker else None
    score_dict = _company_score(selected_ticker,
                                st.session_state.get("home_window", "10y"),
                                DB_MTIME) if selected_ticker else None

    # ═══ 区块 C · 数据深挖 ═══
    st.markdown(
        _section_banner("C", "📊", "数据深挖", "6 维子 Tab · K 线 · 行业 PE · 横向对比"),
        unsafe_allow_html=True,
    )

    tab_financial, tab_price, tab_industry, tab_compare, tab_peer = st.tabs([
        "① 财务指标",
        "② 股价 & ETF",
        "③ 行业估值",
        "④ 横向对比",
        "⑤ 行业横评",
    ])

    with tab_financial:
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
        # 惰性渲染:st.tabs 会一次性构建全部 6 维的图(用户只看 1 个),改 radio +
        # 只渲染选中维度 → 进页面只画 1 张图。维度间切换走 rerun,但每次只建当前 1 张。
        _dim_labels = dict(zip(SCORE_DIM_ORDER, sub_labels))
        if st.session_state.get("company_dim_subtab") not in SCORE_DIM_ORDER:
            st.session_state["company_dim_subtab"] = SCORE_DIM_ORDER[0]
        with detail_expander:
            active_dim = st.radio(
                "数据深挖维度", SCORE_DIM_ORDER,
                format_func=lambda k: _dim_labels.get(k, k),
                horizontal=True, key="company_dim_subtab", label_visibility="collapsed",
            )
        last_module = None
        last_picked: list = []
        last_window = None

        for idx, dim_key in enumerate(SCORE_DIM_ORDER):
            if dim_key != active_dim:
                continue
            with detail_expander:
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
                        # P3 #15:港股窗口短提示(数据 < 3 年的港股 ticker 显式标注)
                        try:
                            _imap = _load_industry_map()
                            _is_hk = str(_imap.get(selected, {}).get("category", "")).lower() == "hk"
                            _span_days = (df["date"].max() - df["date"].min()).days if not df.empty else 0
                            if _is_hk and _span_days < 365 * 3:
                                _yrs = _span_days / 365.0
                                st.warning(
                                    f"⚠️ 港股窗口短:{selected} 估值数据仅近 {_yrs:.1f} 年"
                                    f"(共 {len(df)} 条),分位口径(10y/5y)参考价值有限,"
                                    f"请结合行业 PE 中位数横向对比解读。"
                                )
                        except Exception:
                            pass
                        pct_options = [m for m in PERCENTILE_TRIPLES if m in cols]
                        pct_metric = st.selectbox("分位带指标", pct_options, key=f"pct_metric_{dim_key}") if pct_options else None
                        if pct_metric:
                            fig = percentile_band_chart(df_view, pct_metric, f"{selected} · {pct_metric} 分位带")
                            if fig is not None:
                                fig = overlay_price(fig, selected_ticker, df_view["date"].min(), df_view["date"].max())
                                render_chart_meta(
                                    st,
                                    window=window_label,
                                    source="本地 DuckDB / 理杏仁",
                                    updated=df_view["date"].max().date() if "date" in df_view else None,
                                    note=f"{pct_metric} 分位带;叠加股价为右轴",
                                    estimate=True,
                                )
                                st.plotly_chart(fig, width="stretch")
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
                            render_chart_meta(
                                st,
                                window=window_label,
                                source="本地 DuckDB / 理杏仁",
                                updated=df_view["date"].max().date() if "date" in df_view else None,
                                note="指标来自历史数据表;叠加股价为右轴",
                            )
                            st.plotly_chart(fig, width="stretch")
                        last_picked = picked

                    with st.expander("⬇️ 原始数据(末 50 行)+ CSV 导出"):
                        render_smart_dataframe(
                            st,
                            df_view.tail(50),
                            priority_cols=["date"] + list(last_picked or []),
                            max_default_cols=8,
                        )
                        st.download_button(
                            f"下载 {selected}/{module} CSV",
                            df_view.to_csv(index=False).encode("utf-8-sig"),
                            file_name=f"{selected}_{module}.csv",
                            mime="text/csv", key=f"dl_{dim_key}",
                        )
        write_context(
            selected,
            module=last_module,
            metric=", ".join([p for p in last_picked if p]) if last_picked else None,
            window=last_window,
        )

    with tab_price:
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
                render_chart_meta(
                    st,
                    window=price_window,
                    source="本地 prices 表",
                    updated=pv["date"].max().date() if "date" in pv else None,
                )
                st.plotly_chart(kfig, width="stretch")

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

    with tab_industry:
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
                render_chart_meta(
                    st,
                    window="全量行业历史",
                    source="industry_pe",
                    updated=ind_df["date"].max().date() if "date" in ind_df else None,
                    note="行业 PE 中位/加权/算术口径",
                )
                st.plotly_chart(ifig, width="stretch")

    with tab_compare:
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
                        render_smart_dataframe(
                            st,
                            matrix,
                            priority_cols=cols_order,
                        )
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
                        render_chart_meta(
                            st,
                            window="所选公司共同历史",
                            source=f"{cmp_module} 历史数据",
                            updated=merged["date"].max().date() if "date" in merged else None,
                            note=("已基准化为 100 起点" if normalize else "原始指标值"),
                            estimate=bool(show_industry),
                        )
                        st.plotly_chart(fig, width="stretch")

                        latest = (
                            merged.sort_values("date").groupby("公司", as_index=False)
                            .tail(1)[["公司", "date", cmp_metric]].sort_values(cmp_metric, ascending=False)
                        )
                        render_smart_dataframe(
                            st,
                            latest,
                            priority_cols=["公司", "date", cmp_metric],
                        )
                        st.download_button(
                            "⬇️ 下载对比数据 CSV",
                            merged.to_csv(index=False).encode("utf-8-sig"),
                            file_name=f"compare_{cmp_module}_{cmp_metric}.csv",
                            mime="text/csv", key="dl_compare",
                        )
            if cmp_metrics:
                write_context(selected, compare_targets=targets, compare_metric=f"{cmp_module}/{cmp_metric}")

    with tab_peer:
        # ─── 区块 C-3:🏭 行业横评(Phase B2/B3)─────────────────────────
        _icv = globals().get("icv")
        if selected_ticker and _icv is not None:
            st.divider()
            try:
                _icv.render_industry_compare(selected_ticker, score_dict["name"] if score_dict else selected)
            except Exception as _icv_e:
                st.caption(f"⚠️ 行业横评渲染失败:{_icv_e}")
