"""段 1 Hero:SWS Hero banner + 持仓卡 + 投资视角(林奇) + 健康度 + 雪花/五维 + Piotroski。"""
from __future__ import annotations

from importlib.machinery import SourceFileLoader

import watchlist as _wl

try:
    import streamlit as st
    if st.runtime.exists():
        _cache_data = st.cache_data
    else:
        raise RuntimeError("no streamlit runtime")
except Exception:
    def _cache_data(*a, **kw):
        def deco(fn):
            return fn
        return deco


@_cache_data(ttl=600, show_spinner=False)
def _cached_buffett_classify(ticker: str, _mtime: float):
    """巴菲特分类缓存包装 — classify() 接 dict 不便 hash,改入口为 ticker。"""
    from masters.lynch.classifier import load_metrics_from_db
    from masters.buffett.classifier import classify
    m = load_metrics_from_db(ticker)
    return classify(m)

from ._helpers import (
    _THIS,
    _render_position_card,
    _lynch_card_html,
    _lynch_dim_card_html,
    _lynch_radar,
    _viewpoint_placeholder_html,
)


def _peg_label(peg: float | None) -> str | None:
    """PEG 档位标签。<1 低估 / 1-1.5 合理 / >1.5 偏贵;None → None 静默跳过。"""
    if peg is None:
        return None
    try:
        v = float(peg)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v < 1:
        tag = "低估"
    elif v <= 1.5:
        tag = "合理"
    else:
        tag = "偏贵"
    return f"PEG {v:.2f} {tag}"


def _pe_pct_label(pe_pct: float | None) -> str | None:
    """PE-TTM 10y 分位标签 (raw 0-1)。"""
    if pe_pct is None:
        return None
    try:
        p = float(pe_pct)
    except (TypeError, ValueError):
        return None
    pct = p * 100
    if pct < 30:
        tag = "低估区"
    elif pct <= 70:
        tag = "合理"
    else:
        tag = "高位"
    return f"行业 PE {pct:.0f}% {tag}"


def _deviation_label(current: float | None, mid: float | None) -> str | None:
    """距合理价偏离 % = (current - mid) / mid。"""
    if current is None or mid is None or mid <= 0:
        return None
    try:
        dev = (float(current) - float(mid)) / float(mid) * 100
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    sign = "+" if dev >= 0 else ""
    return f"距合理价 {sign}{dev:.0f}%"


def _render_locator_badge(ticker: str, score_dict: dict) -> None:
    """💡 当前定位 一行 badge — 林奇 / 巴菲特 / PEG / 行业 PE / 距合理价。

    任何一项缺失则静默跳过,不显示 N/A。
    """
    segs: list[str] = []

    # 1) 林奇分类 + 2) 巴菲特分类(共用 lynch loader 装配的 metrics)
    lynch_metrics = None
    lynch_cls_id = None
    try:
        from masters.lynch import classifier as lc_mod
        lr = lc_mod.classify_ticker(ticker)
        if lr is not None and lr.cls_name:
            segs.append(f"林奇·{lr.cls_name}")
            lynch_cls_id = lr.cls_id
        lynch_metrics = lc_mod.load_metrics_from_db(ticker)
    except Exception:
        pass

    try:
        if lynch_metrics is not None:
            from dashboard_helpers import _db_mtime
            br = _cached_buffett_classify(ticker, _db_mtime())
            if br is not None and br.cls_name:
                segs.append(f"巴菲特·{br.cls_name}")
    except Exception:
        pass

    # 3) PEG 档位(理杏仁口径)
    if lynch_metrics is not None:
        peg_seg = _peg_label(lynch_metrics.get("peg_lixinger"))
        if peg_seg:
            segs.append(peg_seg)

    # 4) 行业(全周期)PE 分位 — 取 score_dict valuation.raw (0-1)
    try:
        pe_pct = score_dict["dims"]["valuation"].get("raw")
    except Exception:
        pe_pct = None
    pe_seg = _pe_pct_label(pe_pct)
    if pe_seg:
        segs.append(pe_seg)

    # 5) 距合理价偏离
    try:
        from valuation.price_range import compute_next_quarter_range
        lynch_type = (lynch_cls_id or "").lower() or None
        pr = compute_next_quarter_range(ticker, lynch_type=lynch_type)
        dev_seg = _deviation_label(pr.current_price, pr.mid)
        if dev_seg:
            segs.append(dev_seg)
    except Exception:
        pass

    if not segs:
        return

    body = " │ ".join(segs)
    st.markdown(
        f'<div style="margin:6px 0 12px 0;padding:8px 14px;'
        f'background:#F3F4F6;border:1px solid #E5E7EB;border-radius:8px;'
        f'font-family:-apple-system,Inter,PingFang SC,sans-serif;'
        f'font-size:13px;color:#374151;line-height:1.5;white-space:nowrap;'
        f'overflow-x:auto;">'
        f'<span style="font-weight:600;color:#111827;">💡 当前定位</span>'
        f' │ {body}</div>',
        unsafe_allow_html=True,
    )


def render() -> None:
    # ─── 段 1:SWS 风格 Hero + 雷达 + 五维 + Piotroski ─────────────
    st.markdown(_SWS_CSS, unsafe_allow_html=True)
    folder_to_ticker_home = _folder_to_ticker(DB_MTIME)
    ticker = folder_to_ticker_home.get(selected, "")
    # ─── PE 分位口径(统一为 10y 全周期) ────────────────────────────
    # 主显示固定 10y(权威口径,与 graham/lynch/决策中心/screener 完全一致;
    # 与理杏仁内置「PE-TTM_分位点」差异 < 1pp,实测对齐)。
    # 5y/3y/1y 仅作"近 N 年"对照参考,显示在 expander 内,不影响主评分。
    home_window = "10y"
    st.session_state["home_window"] = home_window
    with st.expander("📐 PE 分位口径说明(默认 10y 全周期,可查看近 N 年对照)", expanded=False):
        st.markdown(
            "**主口径**:PE-TTM 10 年全周期分位(自算,与理杏仁内置 `PE-TTM_分位点` 差异 < 1pp)。\n\n"
            "**为什么固定 10y**:跨 Tab 一致性 — graham/lynch/决策中心/screener 全部以 10y 为基准,"
            "避免同一公司在不同卡片显示不同分位造成误判。\n\n"
            "若想看「近 5 年贵不贵」,可使用估值 sub-tab 内的 5y 分位带图(显式标注口径)。"
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

        # ─── 💡 当前定位 一行 badge(整合 4-5 维信息)──────────────────
        try:
            _render_locator_badge(ticker, score_dict)
        except Exception as _badge_exc:
            st.caption(f"(💡 当前定位 渲染失败:{_badge_exc})")

        # ─── 观察池徽章(若 ticker 在 .config/watchlist.yaml 的 pending 中)─
        try:
            _wl_entry = _wl.get_entry(ticker) if ticker else None
        except Exception:
            _wl_entry = None
        if _wl_entry is not None and _wl_entry.status == "pending":
            _src = _wl_entry.preset or "—"
            _at = _wl_entry.added_at or "—"
            st.markdown(
                f"<div style='display:inline-block;background:#fef3c7;color:#92400e;"
                f"padding:0.35rem 0.75rem;border-radius:6px;border-left:3px solid #f59e0b;"
                f"font-size:0.85rem;margin:0.4rem 0;'>"
                f"🔔 <b>在观察池中</b> · 来源:{_src} · 加入:{_at}</div>",
                unsafe_allow_html=True,
            )

        # ─── 持仓确认开关:勾选 → 写入 .config/portfolio.yaml.positions ──
        #     决策中心「📌 已宣告持仓」段会自动读这份 yaml 显示。
        if ticker:
            try:
                _fp_mod = SourceFileLoader(
                    "fair_price", str(_THIS.parent / "fair_price.py")
                ).load_module()
                _is_held = _fp_mod.is_in_portfolio(ticker)
                _toggle_key = f"position_toggle_{ticker}"
                _new = st.toggle(
                    "📌 确认持仓(纳入决策中心持仓概览)",
                    value=_is_held, key=_toggle_key,
                    help="勾选 → 写入 .config/portfolio.yaml.positions(自动 .bak 备份);"
                         "取消 → 移除。该清单驱动「公司详情持仓卡」与「决策中心 · 已宣告持仓」。",
                )
                if _new and not _is_held:
                    if _fp_mod.add_to_portfolio(ticker, score_dict["name"]):
                        st.success(f"✅ 已加入持仓:{score_dict['name']} ({ticker})  ·  备份 portfolio.yaml.bak")
                        st.rerun()
                elif (not _new) and _is_held:
                    if _fp_mod.remove_from_portfolio(ticker):
                        st.info(f"📤 已移出持仓:{score_dict['name']} ({ticker})")
                        st.rerun()
            except Exception as _e:
                st.caption(f"⚠️ 持仓开关不可用:{_e}")

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
            from datetime import datetime as _dt
            _cur_year = _dt.now().year
            year = st.number_input("评估年份", min_value=2018, max_value=_cur_year,
                                   value=_cur_year - 1,
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
