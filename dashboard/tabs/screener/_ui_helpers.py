"""tabs.screener._ui_helpers · 方法论卡 / 散点图等共享 UI(M2 优化复用).

从 screener_legacy 抽取,供 prelim / lynch_pick / graham_pick 共用。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from screening import screener

_ROOT = Path(__file__).resolve().parents[4]
_DASH = Path(__file__).resolve().parents[2]
_PORTFOLIO_YAML = _ROOT / ".config" / "portfolio.yaml"
if str(_DASH) not in sys.path:
    sys.path.insert(0, str(_DASH))


def portfolio_weights() -> dict[str, float]:
    """读 portfolio.yaml active 持仓 target_weight。"""
    if not _PORTFOLIO_YAML.exists():
        return {}
    try:
        import yaml
        cfg = yaml.safe_load(_PORTFOLIO_YAML.read_text(encoding="utf-8")) or {}
        out: dict[str, float] = {}
        for h in cfg.get("holdings", []) or []:
            if h.get("status") == "active" and h.get("ticker") and h.get("target_weight") is not None:
                out[str(h["ticker"]).zfill(6)] = float(h["target_weight"])
        return out
    except Exception:
        return {}


def preset_for_master(master_id: str) -> dict | None:
    """从 presets.yaml 按 rules_yaml 反查 preset meta。"""
    try:
        for p in screener.load_presets().get("presets", []):
            if p.get("rules_yaml") == master_id:
                return p
    except Exception:
        pass
    return None


def count_excellent(scored: pd.DataFrame, preset_meta: dict | None) -> int | None:
    """统计优秀级命中数;无评分体系时返回 None。"""
    if scored is None or scored.empty or "score" not in scored.columns:
        return None
    if preset_meta and preset_meta.get("use_classifier"):
        return int((scored["score"] >= 75).fillna(False).sum())
    rules_yaml_id = (preset_meta or {}).get("rules_yaml")
    if not rules_yaml_id:
        return None
    try:
        doc = screener.load_master_rules(rules_yaml_id)
        excellent_th = doc.get("threshold", {}).get("excellent")
        if excellent_th is not None:
            return int((scored["score"] >= excellent_th).fillna(False).sum())
    except Exception:
        pass
    return None


def render_lynch_classifier_methodology(preset: dict) -> None:
    """M6 林奇分类器方法论说明。"""
    try:
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
            for _cid, (cn_name, emoji, _) in CLASS_META.items():
                st.markdown(f"- {emoji} {cn_name}")

        st.divider()
        st.markdown("**📊 评估流程(每家公司)**")
        st.markdown(
            "1. **自动分类** — 基于行业 + CAGR + ROE + 现金/市值 + 负债率\n"
            "2. **类型专属 5 维评分** — 不同类型用不同维度组合 + 权重\n"
            "3. **加权综合分** — 0-100 + emoji 评级\n"
            "4. **优势/短板维度**自动浮现到候选清单"
        )

        st.divider()
        st.markdown("**🎯 类型 × 维度评估口径**")
        for cid, (cn_name, emoji, _) in CLASS_META.items():
            schema = LYNCH_DIM_SCHEMA.get(cid, [])
            if not schema:
                continue
            dims_str = " · ".join(
                f"{d['label']}({int(d['weight'] * 100)}%)" for d in schema
            )
            st.markdown(f"- {emoji} **{cn_name}**:{dims_str}")


def render_methodology_card(preset: dict | None) -> None:
    """方法论说明卡(M2 #2):tagline + 来源 + 阈值 + 规则列表。"""
    if not preset:
        return

    rules_yaml_id = preset.get("rules_yaml")
    tagline = preset.get("tagline") or preset.get("description", "")

    with st.container(border=True):
        st.markdown(f"**📖 一句话定位:** {tagline}")

        if preset.get("use_classifier"):
            render_lynch_classifier_methodology(preset)
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
                        for label, val in (
                            ("🟢 优秀", th.get("excellent")),
                            ("🟡 合格", th.get("good")),
                            ("🟠 警戒", th.get("warning")),
                        )
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
                    "⚠️ 神奇公式是**全 A 股 rank 体系**,"
                    "本自选池上仅作参考,不参与 per-company 评分。"
                )


def render_scatter(
    scored: pd.DataFrame,
    preset_meta: dict | None,
    *,
    has_score: bool,
    chart_key: str = "screener_scatter",
) -> None:
    """散点矩阵(M2 #5):有评分时 X=score,否则 X=PE 10y 分位。"""
    if scored is None or scored.empty:
        return

    plot_df = scored.copy()
    weights = portfolio_weights()
    plot_df["ticker"] = plot_df["ticker"].astype(str).str.zfill(6)
    plot_df["weight"] = plot_df["ticker"].map(weights).fillna(0.0)
    plot_df["weight_disp"] = plot_df["weight"].clip(lower=0.001) * 100

    preset_name = (preset_meta or {}).get("name", "评分")
    if has_score:
        st.markdown(
            f"##### 📍 散点矩阵 · X = {preset_name}评分 · Y = ROE · 色 = 评级 · 大小 = 持仓权重"
        )
        rating_order = [
            "🟢 优秀", "🟡 合格", "🟠 警戒", "🔴 不及格", "🚫 不适用", "⚪ 数据不足",
        ]
        rating_color = {
            "🟢 优秀": "#22c55e", "🟡 合格": "#eab308", "🟠 警戒": "#f97316",
            "🔴 不及格": "#ef4444", "🚫 不适用": "#9ca3af", "⚪ 数据不足": "#d1d5db",
        }
        plot_df["rating"] = plot_df.get("rating", pd.Series(dtype=str)).fillna("⚪ 数据不足")
        fig = px.scatter(
            plot_df, x="score", y="roe",
            color="rating", size="weight_disp",
            hover_name="name", text="name",
            category_orders={"rating": rating_order},
            color_discrete_map=rating_color,
            labels={
                "score": f"{preset_name}评分", "roe": "ROE",
                "rating": "评级", "weight_disp": "持仓权重 ×100",
            },
            size_max=40,
        )
        fig.update_traces(textposition="top center", textfont_size=11)
        rules_yaml_id = (preset_meta or {}).get("rules_yaml")
        if rules_yaml_id:
            try:
                doc = screener.load_master_rules(rules_yaml_id)
                ex_th = doc.get("threshold", {}).get("excellent")
                if ex_th is not None:
                    fig.add_vline(
                        x=ex_th, line_dash="dot", line_color="#22c55e",
                        annotation_text=f"优秀线 {ex_th}",
                    )
            except Exception:
                pass
        fig.add_hline(y=0.15, line_dash="dot", line_color="#9CA3AF", annotation_text="ROE 15%")
        fig.update_layout(height=420, margin=dict(l=40, r=20, t=10, b=40), yaxis_tickformat=".0%")
    else:
        st.markdown(
            "##### 📍 散点矩阵 · X = PE 10y 分位 · Y = ROE · 色 = F-Score · 大小 = 持仓权重"
        )
        plot_df["fscore_disp"] = plot_df["fscore"].fillna(-1).astype(int)
        fig = px.scatter(
            plot_df, x="pe_pct_10y", y="roe",
            color="fscore_disp", size="weight_disp",
            hover_name="name", text="name",
            color_continuous_scale="RdYlGn", range_color=[0, 9],
            labels={
                "pe_pct_10y": "PE 10y 分位", "roe": "ROE",
                "fscore_disp": "F-Score", "weight_disp": "持仓权重 ×100",
            },
            size_max=40,
        )
        fig.update_traces(textposition="top center", textfont_size=11)
        fig.update_layout(
            height=420, margin=dict(l=40, r=20, t=10, b=40),
            xaxis_tickformat=".0%", yaxis_tickformat=".0%",
        )
        fig.add_vline(x=0.30, line_dash="dot", line_color="#9CA3AF", annotation_text="低估线 30%")
        fig.add_hline(y=0.15, line_dash="dot", line_color="#9CA3AF", annotation_text="ROE 15%")

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=chart_key)


__all__ = [
    "portfolio_weights",
    "preset_for_master",
    "count_excellent",
    "render_methodology_card",
    "render_lynch_classifier_methodology",
    "render_scatter",
]
