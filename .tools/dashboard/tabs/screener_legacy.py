"""dash-02 公司筛选 Tab(L2 — 回答"15 家里哪些值得看?")。

M2 优化版(2026-05-05):
  - 顶部:4 大师预设(巴菲特护城河 / 格雷厄姆 / 林奇成长 / 格林布拉特)
  - 方法论说明卡(expander):tagline + 来源 + 阈值 + 7-9 项规则 + 适用/不适用
  - 候选清单按大师评分降序 + rating emoji + 加入观察池 checkbox(替代底部 multiselect)
  - 散点矩阵 X = 大师评分 / Y = ROE / 颜色 = rating
  - 命中数 / 通过率 实时显示
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from screening import screener  # 同 .tools/dashboard 目录,app.py 已 sys.path.insert

ROOT = Path(__file__).resolve().parents[3]
WATCHLIST = ROOT / ".temp" / "watchlist.md"
PORTFOLIO_YAML = ROOT / ".tools" / "portfolio" / "portfolio.yaml"


@st.cache_data(ttl=300)
def _load_screener_data(db_mtime: float, year: int) -> pd.DataFrame:
    return screener.load_all(fscore_year=year)


@st.cache_data(ttl=600)
def _load_presets_cached(_dummy: float) -> dict:
    return screener.load_presets()


@st.cache_data(ttl=3600, show_spinner=False)
def _score_with_master_cached(db_mtime: float, master_id: str, year: int,
                               tickers_key: str) -> pd.DataFrame:
    """缓存 1 小时:大师评分对 15 家公司,只在 db_mtime / master_id / year 变更时重算。

    tickers_key 仅用于使缓存绑定到当前 df 的 tickers(避免不同顺序复用旧缓存)。
    """
    df = _load_screener_data(db_mtime, year)
    return screener.score_with_master(df, master_id, year)


@st.cache_data(ttl=3600, show_spinner=False)
def _score_lynch_classifier_cached(db_mtime: float, year: int,
                                    tickers_key: str) -> pd.DataFrame:
    """M6 林奇分类器(最新方法)— 六类判定 + 类型驱动 5 维评分(0-100)。"""
    df = _load_screener_data(db_mtime, year)
    return screener.score_lynch_classifier_all(df)


def _portfolio_weights() -> dict[str, float]:
    """读 portfolio.yaml 里 active 持仓的 target_weight,失败返回空。"""
    if not PORTFOLIO_YAML.exists():
        return {}
    try:
        import yaml
        cfg = yaml.safe_load(PORTFOLIO_YAML.read_text(encoding="utf-8")) or {}
        out: dict[str, float] = {}
        for h in cfg.get("holdings", []) or []:
            if h.get("status") == "active" and h.get("ticker") and h.get("target_weight") is not None:
                out[str(h["ticker"])] = float(h["target_weight"])
        return out
    except Exception:
        return {}


def _format_value(v, fmt: str, scale: float = 1.0) -> str:
    if v is None or pd.isna(v):
        return "—"
    try:
        return fmt % (v * scale)
    except Exception:
        return str(v)


def _write_watchlist(selected_rows: pd.DataFrame, preset_label: str) -> None:
    WATCHLIST.parent.mkdir(parents=True, exist_ok=True)
    existing = WATCHLIST.read_text(encoding="utf-8") if WATCHLIST.exists() else ""
    existing_tickers: set[str] = set()
    for line in existing.splitlines():
        m = re.search(r"\((\d{5,6})\)", line)
        if m:
            existing_tickers.add(m.group(1))

    new_lines = []
    today = datetime.now().strftime("%Y-%m-%d")
    for _, row in selected_rows.iterrows():
        if str(row["ticker"]) in existing_tickers:
            continue
        score_part = ""
        if "score" in row and pd.notna(row.get("score")):
            mx = row.get("max_score")
            score_part = f" · 评分 {row['score']:.0f}" + (f"/{int(mx)}" if pd.notna(mx) else "")
        line = (
            f"- [ ] **{row['name']}** ({row['ticker']}) — {preset_label} 通过 · {today}"
            f"{score_part}"
            f" · PE 分位 {_format_value(row.get('pe_pct_10y'), '%.0f%%', 100)}"
            f" · ROE {_format_value(row.get('roe'), '%.1f%%', 100)}"
            f" · F-Score {row.get('fscore') if pd.notna(row.get('fscore')) else '—'}/9"
        )
        new_lines.append(line)

    if not new_lines:
        return

    if not existing.strip():
        existing = (
            "# 📋 观察池\n\n"
            "> 由 dash-02 公司筛选写入 · 勾选 ☑ 表示决策已闭环可移除\n\n"
        )
    WATCHLIST.write_text(existing.rstrip() + "\n" + "\n".join(new_lines) + "\n", encoding="utf-8")


def _read_watchlist() -> str:
    return WATCHLIST.read_text(encoding="utf-8") if WATCHLIST.exists() else ""


def _render_lynch_classifier_methodology(preset: dict) -> None:
    """M6 林奇分类器方法论说明 — 替代 GARP yaml 规则展示。"""
    try:
        sys_path_dash = str(ROOT / ".tools" / "dashboard")
        if sys_path_dash not in sys.path:
            sys.path.insert(0, sys_path_dash)
        from masters.lynch.classifier import CLASS_META, LYNCH_DIM_SCHEMA  # noqa: E402
    except Exception as e:
        st.caption(f"⚠️ 林奇分类器加载失败:{e}")
        return

    with st.expander("▼ 方法论详情(展开看完整框架)", expanded=False):
        cols = st.columns([2, 1])
        with cols[0]:
            st.markdown("- **大师**:彼得·林奇")
            st.markdown("- **方法**:六类公司分类 + 类型驱动 5 维评分(M6)")
            st.markdown("- **核心理念**:_先定性(分到哪一类),后定量(用对应类型的指标评估)_")
            if preset.get("book_origin"):
                st.markdown(f"- **来源**:{preset['book_origin']}")
            st.markdown("- **评分**:满分 100 · 阈值 🟢 ≥75 / 🟡 ≥60 / 🟠 ≥45 / 🔴 <45")
            if preset.get("knowledge_link"):
                st.markdown(f"- **知识库**:`{preset['knowledge_link']}`")

        with cols[1]:
            st.markdown("**🧩 六类公司**")
            for cid, (cn_name, emoji, _) in CLASS_META.items():
                st.markdown(f"- {emoji} {cn_name}")

        st.divider()
        st.markdown("**📊 评估流程(每家公司)**")
        st.markdown(
            "1. **自动分类**(`lynch_classifier.classify`)— 基于行业 + CAGR + ROE + 现金/市值 + 负债率,按"
            " 周期 → 困境反转 → 资产隐蔽 → 快速 → 稳健 → 缓慢 优先级判定\n"
            "2. **类型专属 5 维评分**(`compute_lynch_dims`)— 不同类型用不同维度组合 + 权重\n"
            "3. **加权综合分**(`overall_lynch`)— 0-100 + emoji 评级\n"
            "4. **优势/短板维度**自动浮现到候选清单"
        )

        st.divider()
        st.markdown("**🎯 类型 × 维度评估口径**")
        for cid, (cn_name, emoji, _) in CLASS_META.items():
            schema = LYNCH_DIM_SCHEMA.get(cid, [])
            if not schema:
                continue
            dims_str = " · ".join(
                f"{d['label']}({int(d['weight']*100)}%)" for d in schema
            )
            st.markdown(f"- {emoji} **{cn_name}**:{dims_str}")

        st.divider()
        st.caption(
            "💡 **vs 旧 GARP 5 项**:旧方法对所有公司套同一组规则(PEG / 负债 / FCF / 机构持仓 / 内部人买入)— "
            "把茅台和宁德按同样口径打分,误导大;新方法**先分类再评估**,茅台用 stalwart 维度(ROE 质量+股息+现金流),"
            "宁德用 fast_grower 维度(PEG+营收+净利+ROE),口径自适应。"
        )


def _render_methodology_card(preset: dict) -> None:
    """方法论说明卡(M2 #2):tagline + 来源 + 阈值 + 规则列表 + 适用/不适用。"""
    rules_yaml_id = preset.get("rules_yaml")
    tagline = preset.get("tagline") or preset.get("description", "")

    with st.container(border=True):
        st.markdown(f"**📖 一句话定位:** {tagline}")

        # ★ 林奇 use_classifier 模式 → 显示 M6 分类器方法论(不是旧 GARP yaml)
        if preset.get("use_classifier"):
            _render_lynch_classifier_methodology(preset)
            return

        if not rules_yaml_id:
            st.caption("(纯过滤模式 — 无评分体系)")
            return

        try:
            doc = screener.load_master_rules(rules_yaml_id)
        except FileNotFoundError:
            st.caption(f"⚠️ 未找到 `.tools/rules/{rules_yaml_id}.yaml`")
            return

        with st.expander("▼ 方法论详情(展开看完整框架)", expanded=False):
            cols = st.columns([2, 1])
            with cols[0]:
                if doc.get("master_cn"):
                    st.markdown(f"- **大师**:{doc['master_cn']}")
                if doc.get("method"):
                    st.markdown(f"- **方法**:{doc['method']}")
                if preset.get("book_origin"):
                    st.markdown(f"- **来源**:{preset['book_origin']}")
                if doc.get("max_score"):
                    th = doc.get("threshold", {})
                    th_text = " / ".join(
                        f"{label} {val}+"
                        for label, val in (("🟢 优秀", th.get("excellent")),
                                            ("🟡 合格", th.get("good")),
                                            ("🟠 警戒", th.get("warning")))
                        if val is not None
                    )
                    st.markdown(f"- **评分**:满分 {doc['max_score']} · 阈值 {th_text}")
                if preset.get("knowledge_link"):
                    st.markdown(f"- **知识库**:`{preset['knowledge_link']}`")

            with cols[1]:
                if doc.get("exclude_industries"):
                    st.markdown("**🚫 不适用**")
                    for i in doc["exclude_industries"]:
                        st.markdown(f"- {i}")

            rules = doc.get("rules") or []
            if rules:
                st.markdown(f"**📋 规则({len(rules)} 项)**")
                for i, r in enumerate(rules, 1):
                    name = r.get("name", r.get("id", f"rule_{i}"))
                    score = r.get("score_if_pass", 1)
                    formula = r.get("formula", "")
                    if "\n" in formula:
                        formula = formula.split("\n", 1)[0] + " ..."
                    st.markdown(f"{i}. **{name}**({score} 分) · `{formula}`")
            elif rules_yaml_id == "greenblatt":
                st.info(
                    "⚠️ 神奇公式是**全 A 股 rank 体系**(原版选 ROIC + EBIT/EV 双因子排名前 30),"
                    "本驾驶舱 15 家自选池上仅作参考,不参与 per-company 评分。"
                )


# ─── 主入口 ─────────────────────────────────────────────────────────

def render(companies: list[str], db_mtime: float) -> None:
    """app.py 调用:`from tabs.screener import render; render(companies, db_mtime)`。"""
    st.subheader("🔍 L2 公司筛选 — 哪些值得深看?")

    presets_cfg = _load_presets_cached(db_mtime)
    preset_options = [(p["id"], p) for p in presets_cfg.get("presets", [])]

    label_for: dict[str, str] = {}
    for pid, p in preset_options:
        if p:
            label_for[pid] = f"{p.get('icon','')} {p.get('name', pid)}"

    preset_id = st.radio(
        "筛选预设(一键应用)", list(label_for.keys()),
        format_func=lambda x: label_for[x],
        horizontal=True, key="screener_preset",
    )

    preset_meta = next((p for p in presets_cfg["presets"] if p["id"] == preset_id), None)

    # 方法论说明卡(M2 #2)
    if preset_meta:
        _render_methodology_card(preset_meta)

    # ─── 装载数据 ──────────────────────────────────────────────────
    fscore_year = pd.Timestamp.now().year - 1
    with st.spinner("加载 15 家公司全指标 + F-Score..."):
        df = _load_screener_data(db_mtime, fscore_year).copy()

    weights = _portfolio_weights()
    df["weight"] = df["ticker"].map(weights).fillna(0.0)

    # ─── 大师预设:硬过滤 + 评分 ───────────────────────────────────
    filtered = screener.apply_filters(df, preset_meta.get("filters") or [])
    active_filters = preset_meta.get("filters") or []

    rules_yaml_id = preset_meta.get("rules_yaml")
    use_classifier = bool(preset_meta.get("use_classifier"))
    tickers_key = ",".join(sorted(df["ticker"].astype(str).tolist()))

    if use_classifier and preset_id == "lynch":
        # ★ 最新方法:六类分类器 + per-class 5 维评分(M6 链路)
        with st.spinner(f"运行 {preset_meta['name']}(六类分类器)..."):
            full_scored = _score_lynch_classifier_cached(
                db_mtime, fscore_year, tickers_key
            )
        scored = full_scored[full_scored["ticker"].isin(filtered["ticker"])].copy()
        scored["weight"] = scored["ticker"].map(
            df.set_index("ticker")["weight"]
        ).fillna(0.0)
        scored = scored.sort_values("score", ascending=False, na_position="last")
    elif rules_yaml_id:
        # 旧:GARP / 各大师 yaml 硬规则评分(score_with_master)
        with st.spinner(f"运行 {preset_meta['name']} 评分..."):
            full_scored = _score_with_master_cached(
                db_mtime, rules_yaml_id, fscore_year, tickers_key
            )
        scored = full_scored[full_scored["ticker"].isin(filtered["ticker"])].copy()
        scored["weight"] = scored["ticker"].map(
            df.set_index("ticker")["weight"]
        ).fillna(0.0)
        scored = scored.sort_values("score", ascending=False, na_position="last")
    else:
        scored = filtered.copy()
        for col in ("score", "max_score", "rating", "valid_rules", "total_rules"):
            scored[col] = float("nan") if col in ("score", "max_score") else None

    # ─── 命中统计 ──────────────────────────────────────────────────
    hit_pct = len(filtered) / len(df) if len(df) else 0
    pass_excellent = 0
    is_lynch_classifier_mode = (preset_id == "lynch") and "lynch_type" in scored.columns

    if is_lynch_classifier_mode:
        # M6 分类器模式:阈值固定 ≥ 75 = 优秀
        pass_excellent = int((scored["score"] >= 75).fillna(False).sum())
    elif "score" in scored.columns and "max_score" in scored.columns:
        try:
            doc = screener.load_master_rules(preset_meta["rules_yaml"]) if preset_meta and preset_meta.get("rules_yaml") else None
            if doc:
                excellent_th = doc.get("threshold", {}).get("excellent")
                if excellent_th is not None:
                    pass_excellent = int((scored["score"] >= excellent_th).fillna(False).sum())
        except Exception:
            pass

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("总公司数", f"{len(df)}")
    m2.metric("通过条数", f"{len(filtered)}")
    m3.metric("通过率", f"{hit_pct:.0%}")
    m4.metric("🟢 优秀级", f"{pass_excellent}" if preset_meta and (preset_meta.get("rules_yaml") or is_lynch_classifier_mode) else "—")

    # ★ 林奇分类器模式:展示六类公司分布(用户秒看本批属于什么类型)
    if is_lynch_classifier_mode and len(scored) > 0:
        type_counts = scored.groupby(
            ["lynch_type_emoji", "lynch_type_cn"]
        ).size().reset_index(name="count").sort_values("count", ascending=False)
        if not type_counts.empty:
            badges = " · ".join(
                f"{row['lynch_type_emoji']} {row['lynch_type_cn']} **{row['count']}**"
                for _, row in type_counts.iterrows()
            )
            st.caption(f"📊 六类分布:{badges}")
            st.caption(
                "💡 这里的「评分 / 评级」= **加权综合分(连续 0-100)**,"
                "与 🌱 林奇分析法 Tab 内右侧的「加权综合分」**完全一致**。"
                "Tab 内左侧「五步通过 N/5」是 gate 式离散判定 — 口径不同,详见 Tab 内"
                "「两个视角对照」说明。"
            )

    # ─── 散点矩阵(M2 #5)─────────────────────────────────────────
    has_score = preset_meta and preset_meta.get("rules_yaml") and "score" in scored.columns and scored["score"].notna().any()
    if has_score:
        st.markdown(
            f"##### 📍 散点矩阵 · X = {preset_meta['name']}评分 · Y = ROE · 色 = 评级 · 大小 = 持仓权重"
        )
    else:
        st.markdown(
            "##### 📍 散点矩阵 · X = PE 10y 分位 · Y = ROE · 色 = F-Score · 大小 = 持仓权重"
        )
    plot_df = scored.copy()
    plot_df["weight_disp"] = plot_df["weight"].clip(lower=0.001) * 100

    if plot_df.empty:
        st.warning("当前筛选无任何公司命中,试试切换其他大师预设。")
    elif has_score:
        # 评分模式:X = score / 颜色 = rating(category)
        rating_order = ["🟢 优秀", "🟡 合格", "🟠 警戒", "🔴 不及格", "🚫 不适用", "⚪ 数据不足"]
        rating_color = {
            "🟢 优秀": "#22c55e", "🟡 合格": "#eab308", "🟠 警戒": "#f97316",
            "🔴 不及格": "#ef4444", "🚫 不适用": "#9ca3af", "⚪ 数据不足": "#d1d5db",
        }
        plot_df["rating"] = plot_df["rating"].fillna("⚪ 数据不足")
        fig = px.scatter(
            plot_df, x="score", y="roe",
            color="rating", size="weight_disp",
            hover_name="name", text="name",
            category_orders={"rating": rating_order},
            color_discrete_map=rating_color,
            labels={"score": f"{preset_meta['name']}评分", "roe": "ROE",
                    "rating": "评级", "weight_disp": "持仓权重 ×100"},
            size_max=40,
        )
        fig.update_traces(textposition="top center", textfont_size=11)
        try:
            doc = screener.load_master_rules(preset_meta["rules_yaml"])
            ex_th = doc.get("threshold", {}).get("excellent")
            if ex_th is not None:
                fig.add_vline(
                    x=ex_th, line_dash="dot", line_color="#22c55e",
                    annotation_text=f"优秀线 {ex_th}",
                )
        except Exception:
            pass
        fig.add_hline(y=0.15, line_dash="dot", line_color="#9CA3AF",
                      annotation_text="ROE 15%")
        fig.update_layout(
            height=500, margin=dict(l=40, r=20, t=10, b=40),
            yaxis_tickformat=".0%",
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    else:
        plot_df["fscore_disp"] = plot_df["fscore"].fillna(-1).astype(int)
        fig = px.scatter(
            plot_df, x="pe_pct_10y", y="roe",
            color="fscore_disp", size="weight_disp",
            hover_name="name", text="name",
            color_continuous_scale="RdYlGn", range_color=[0, 9],
            labels={"pe_pct_10y": "PE 10y 分位", "roe": "ROE",
                    "fscore_disp": "F-Score", "weight_disp": "持仓权重 ×100"},
            size_max=40,
        )
        fig.update_traces(textposition="top center", textfont_size=11)
        fig.update_layout(
            height=500, margin=dict(l=40, r=20, t=10, b=40),
            xaxis_tickformat=".0%", yaxis_tickformat=".0%",
        )
        fig.add_vline(x=0.30, line_dash="dot", line_color="#9CA3AF",
                      annotation_text="低估线 30%")
        fig.add_hline(y=0.15, line_dash="dot", line_color="#9CA3AF",
                      annotation_text="ROE 15%")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    # ─── 候选清单 + checkbox 加入观察池(M2 #1)──────────────────
    st.markdown("##### 📋 候选清单 · 按评分降序")
    if scored.empty:
        st.caption("(无候选)")
    else:
        # 构造展示用 DataFrame
        disp = scored.copy()
        disp["加入观察池"] = False  # checkbox 列默认 False

        if has_score:
            # 大师评分模式:score / rating 在前
            disp["评分"] = disp.apply(
                lambda r: f"{r['score']:.0f}/{int(r['max_score'])}" if pd.notna(r.get("score")) and pd.notna(r.get("max_score"))
                          else (f"{r['score']:.0f}" if pd.notna(r.get("score")) else "—"),
                axis=1,
            )
            disp["评级"] = disp["rating"].fillna("—")
            disp["可评/总规则"] = disp.apply(
                lambda r: f"{int(r['valid_rules'])}/{int(r['total_rules'])}"
                          if pd.notna(r.get("valid_rules")) and pd.notna(r.get("total_rules"))
                          else "—",
                axis=1,
            )

            # ★ M6 林奇分类器特有列:类型徽章 + 优势/短板维度
            is_lynch_classifier = "lynch_type" in disp.columns
            if is_lynch_classifier:
                disp["林奇类型"] = disp.apply(
                    lambda r: f"{r.get('lynch_type_emoji','⚪')} {r.get('lynch_type_cn','—')}"
                              + (f"({r['lynch_confidence']*100:.0f}%)"
                                 if pd.notna(r.get('lynch_confidence')) else ""),
                    axis=1,
                )
                disp["优势维度"] = disp["dim_top"].fillna("—")
                disp["短板维度"] = disp["dim_bot"].fillna("—")
                cols_order = [
                    "加入观察池", "name", "ticker", "林奇类型",
                    "评分", "评级", "优势维度", "短板维度",
                    "pe", "pe_pct_10y", "roe", "fscore",
                ]
            else:
                cols_order = [
                    "加入观察池", "name", "ticker", "评分", "评级", "可评/总规则",
                    "pe", "pe_pct_10y", "roe", "fscore",
                ]
            rename = {
                "name": "公司", "ticker": "代码",
                "pe": "PE-TTM", "pe_pct_10y": "PE 10y 分位",
                "roe": "ROE", "fscore": "F-Score",
            }
        else:
            cols_order = [
                "加入观察池", "name", "ticker", "pe", "pe_pct_10y",
                "pb", "dividend_yield", "roe", "rev_yoy", "cfo_to_ni",
                "debt_ratio", "fscore",
            ]
            rename = {
                "name": "公司", "ticker": "代码", "pe": "PE-TTM",
                "pe_pct_10y": "PE 10y 分位", "pb": "PB",
                "dividend_yield": "股息率", "roe": "ROE",
                "rev_yoy": "营收 YoY", "cfo_to_ni": "CFO/NI",
                "debt_ratio": "负债率", "fscore": "F-Score",
            }

        show = disp[[c for c in cols_order if c in disp.columns]].rename(columns=rename)

        edited = st.data_editor(
            show,
            width="stretch", hide_index=True,
            num_rows="fixed",
            disabled=[c for c in show.columns if c != "加入观察池"],
            column_config={
                "加入观察池":   st.column_config.CheckboxColumn(default=False, width="small"),
                "PE 10y 分位": st.column_config.NumberColumn(format="%.1f%%"),
                "股息率":      st.column_config.NumberColumn(format="%.2f%%"),
                "ROE":         st.column_config.NumberColumn(format="%.1f%%"),
                "营收 YoY":    st.column_config.NumberColumn(format="%.1f%%"),
                "负债率":      st.column_config.NumberColumn(format="%.0f%%"),
                "CFO/NI":      st.column_config.NumberColumn(format="%.2f"),
                "PE-TTM":      st.column_config.NumberColumn(format="%.1f"),
                "PB":          st.column_config.NumberColumn(format="%.2f"),
                "F-Score":     st.column_config.NumberColumn(format="%d"),
            },
            key="screener_table",
        )

        sel_count = int(edited["加入观察池"].sum()) if "加入观察池" in edited.columns else 0

        col_w1, col_w2 = st.columns([1, 4])
        with col_w1:
            if st.button(
                f"📥 加入勾选项 ({sel_count})",
                type="primary", disabled=sel_count == 0,
                key="screener_add_watch",
            ):
                preset_label = label_for.get(preset_id, preset_id)
                selected_names = edited.loc[edited["加入观察池"], "公司"].tolist()
                rows_to_add = scored[scored["name"].isin(selected_names)]
                _write_watchlist(rows_to_add, preset_label)
                st.success(f"✅ {len(rows_to_add)} 家已写入 .temp/watchlist.md")
                st.rerun()
        with col_w2:
            st.caption(f"观察池路径:`{WATCHLIST.relative_to(ROOT)}` · 已存在则跳过去重")

    # ─── 观察池预览 ─────────────────────────────────────────────────
    with st.expander("📋 观察池(.temp/watchlist.md)", expanded=False):
        wl = _read_watchlist()
        if wl.strip():
            st.markdown(wl)
            if st.button("🗑 清空观察池", key="screener_clear_watch"):
                if WATCHLIST.exists():
                    WATCHLIST.unlink()
                st.rerun()
        else:
            st.caption("(空)")
