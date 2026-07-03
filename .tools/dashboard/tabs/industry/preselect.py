"""tabs.industry.preselect · 行业预选(深度研判 + 加入自选).

数据流:
  段1 筛选指引 → 初步筛选行业(只读,来自「行业分析」勾选/L2 加入预选)
  → 行业深度研判(ETF/龙头 Top5 加入 watchlist) → 「行业确定」落盘。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[4]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
PORTFOLIO_DIR = ROOT / ".tools" / "portfolio"
KONDRATIEFF_YAML = DASHBOARD_DIR / "data" / "kondratieff.yaml"
ETF_MAPPING_YAML = ROOT / ".tools" / "rules" / "industry_etf_mapping.yaml"
COMPANIES_CSV = ROOT / ".config" / "companies.csv"

if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))
if str(PORTFOLIO_DIR) not in sys.path:
    sys.path.insert(0, str(PORTFOLIO_DIR))

try:
    from tabs.industry_focus import PHASE_EMOJI, _cached_cycle, _cached_percentile
except ImportError:
    PHASE_EMOJI = {
        "rising": "📈", "topping": "🔻", "falling": "📉",
        "bottoming": "🟢", "sideways": "🔄",
    }

    @st.cache_data(ttl=3600)
    def _cached_percentile(industry: str) -> dict:
        from industry.percentile_engine import compute
        r = compute(industry)
        return {
            "pe_median": r.pe_median,
            "pe_percentile_10y": r.pe_percentile_10y,
            "pb_median": r.pb_median,
            "pb_percentile_10y": r.pb_percentile_10y,
            "member_count": r.member_count,
            "data_source": r.data_source,
        }

    @st.cache_data(ttl=3600)
    def _cached_cycle(industry: str) -> dict:
        from industry.cycle import diagnose
        r = diagnose(industry)
        return {
            "phase": r.phase, "phase_cn": r.phase_cn,
            "cycle_type": r.cycle_type,
            "kondratieff_position": r.kondratieff_position,
            "confidence": float(r.confidence),
            "rationale": r.rationale,
        }

_COVERAGE_GAPS = ("半导体", "光伏")
_LAYER_EMOJI = {"defensive": "🛡️", "offensive": "🚀", "auxiliary": "⚙️"}


def _build_draft_index(draft: list[dict]) -> dict[str, dict]:
    return {d["industry"]: d for d in draft if d.get("industry")}


@st.cache_data(ttl=3600, show_spinner=False)
def _load_kondratieff() -> dict:
    if not KONDRATIEFF_YAML.exists():
        return {}
    try:
        return yaml.safe_load(KONDRATIEFF_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def _industry_layer_map() -> dict[str, str]:
    if not ETF_MAPPING_YAML.exists():
        return {}
    try:
        data = yaml.safe_load(ETF_MAPPING_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    out: dict[str, str] = {}
    for row in data.get("mapping") or []:
        ind = row.get("industry")
        layer = row.get("layer")
        if ind and layer:
            out[str(ind)] = str(layer)
    return out


def _ticker_match_keys(ticker: str) -> set[str]:
    t = str(ticker).strip()
    keys = {t, t.lstrip("0") or "0"}
    if t.isdigit():
        keys.add(t.zfill(6))
    return keys


@st.cache_data(ttl=600, show_spinner=False)
def _industries_with_holdings() -> set[str]:
    """返回 portfolio(active+watch) 有持仓的行业 L2 名集合."""
    try:
        from loader import load_portfolio
        pf = load_portfolio()
        portfolio_keys: set[str] = set()
        for h in pf.holdings:
            if h.status in ("active", "watch") and h.ticker:
                portfolio_keys |= _ticker_match_keys(h.ticker)
    except Exception:
        return set()

    if not COMPANIES_CSV.exists():
        return set()
    try:
        import csv
        out: set[str] = set()
        with COMPANIES_CSV.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                stock = str(row.get("stock") or "").strip()
                ind = str(row.get("industry_l2") or "").strip()
                if not stock or not ind:
                    continue
                if _ticker_match_keys(stock) & portfolio_keys:
                    out.add(ind)
        return out
    except Exception:
        return set()


def pe_badge_html(pct: float | None) -> str:
    """PE 10y 分位 badge: 绿 <30% / 黄 30-70% / 红 >70%."""
    if pct is None:
        return "<span style='color:#6b7280;font-size:0.75rem'>PE —</span>"
    v = float(pct)
    if v < 30:
        bg, fg = "#dcfce7", "#14532d"
    elif v <= 70:
        bg, fg = "#fef9c3", "#713f12"
    else:
        bg, fg = "#fee2e2", "#7f1d1d"
    return (
        f"<span style='background:{bg};color:{fg};padding:0.1rem 0.35rem;"
        f"border-radius:4px;font-size:0.75rem;white-space:nowrap'>PE {v:.0f}%</span>"
    )


def layer_badge(layer: str | None) -> str:
    if not layer:
        return ""
    return _LAYER_EMOJI.get(layer, "")


def build_guidance_bullets(kdf: dict, focus_names: set[str]) -> list[str]:
    """段1 筛选指引 bullet 列表."""
    bullets: list[str] = []
    phase = kdf.get("phase") or "—"
    phase_emoji = kdf.get("phase_emoji") or "🔴"
    strategy = kdf.get("strategy_summary") or "防御为主 65-75% / 进攻 25-35%"
    eq_lo = kdf.get("equity_target_pct")
    eq_hi = kdf.get("equity_target_pct_max")
    eq_hint = ""
    if eq_lo is not None and eq_hi is not None:
        eq_hint = f" · 进攻权益 {eq_lo}-{eq_hi}%"
    bullets.append(
        f"{phase_emoji} **当前康波** {phase} — {strategy}{eq_hint}"
    )
    bullets.append(
        "**估值优先**: PE 10y 分位 **< 30%** 的行业优先纳入预选(绿色 PE 标记)"
    )
    gaps = [g for g in _COVERAGE_GAPS if g not in focus_names]
    if gaps:
        bullets.append(
            f"**覆盖缺口**: 进攻层建议关注 **{' / '.join(gaps)}**(尚未 focus)"
        )
    return bullets


def format_industry_signals(
    industry: str,
    *,
    pe_pct: float | None,
    phase: str | None,
    layer: str | None,
    has_holding: bool,
) -> str:
    """L2 行内联 badge 字符串(HTML)."""
    parts: list[str] = []
    le = layer_badge(layer)
    if le:
        parts.append(le)
    if phase:
        parts.append(PHASE_EMOJI.get(phase, "❓"))
    parts.append(pe_badge_html(pe_pct))
    if has_holding:
        parts.append("<span style='font-size:0.75rem'>🌟已持</span>")
    return " ".join(parts)


def _render_guidance(focus_names: set[str]) -> None:
    kdf = _load_kondratieff()
    bullets = build_guidance_bullets(kdf, focus_names)
    bullets[0] = bullets[0] + " · 完整解读见「📊 市场研判」"
    body = "\n".join(f"- {b}" for b in bullets)
    st.markdown("**段1 · 筛选指引**")
    st.info(body)


def _render_preliminary_screened_table(
    draft: list[dict],
    master: dict[str, dict],
    rank_df: pd.DataFrame,
    focus_list: list[dict] | None = None,
) -> list[str]:
    """初步筛选行业 — 展示草稿 L2 + 已确认 focus L2(合并视图,状态列区分)."""
    focus_list = focus_list or []
    focus_by_ind: dict[str, dict] = {
        f.get("industry"): f for f in focus_list if f.get("industry")
    }

    # 合并:draft 在前,focus 中尚未出现在 draft 的补在后
    draft_inds = {d.get("industry") for d in draft if d.get("industry")}
    combined: list[tuple[dict, str]] = [(d, "草稿") for d in draft if d.get("industry")]
    for ind, f in focus_by_ind.items():
        if ind not in draft_inds:
            combined.append((f, "✅ 已确认"))

    if not combined:
        return []

    rank_idx: dict[str, float | None] = {}
    if not rank_df.empty:
        for _, r in rank_df.iterrows():
            rank_idx[str(r["行业"])] = r.get("PE 分位(10y)")

    rows: list[dict] = []
    for d, status in combined:
        l2 = d.get("industry")
        if not l2:
            continue
        meta = master.get(l2, {})
        pe_pct = rank_idx.get(l2)
        # 草稿条目若同时已在 focus,状态升级为 已确认
        if status == "草稿" and l2 in focus_by_ind:
            status = "✅ 已确认"
        rows.append({
            "L2 行业": l2,
            "申万一级": meta.get("sw_l1", "—"),
            "PE 10y 分位": float(pe_pct) if pe_pct is not None and pd.notna(pe_pct) else None,
            "type": d.get("type") or meta.get("type") or "stalwart",
            "状态": status,
            "来源": d.get("note") or "—",
        })

    if not rows:
        return []

    view = pd.DataFrame(rows).sort_values(
        ["状态", "PE 10y 分位"],
        ascending=[False, True],  # "草稿" 在前,"✅ 已确认" 在后
        na_position="last",
    )
    st.dataframe(
        view,
        hide_index=True,
        width="stretch",
        column_config={
            "PE 10y 分位": st.column_config.ProgressColumn(
                "PE 10y 分位",
                format="%.0f%%",
                min_value=0,
                max_value=100,
            ),
        },
    )
    return [str(r["L2 行业"]) for _, r in view.iterrows()]


def _render_footer(draft_count: int) -> None:
    st.markdown("---")
    st.markdown("**底部 · 下一步**")
    c1, c2, c3 = st.columns([2, 1, 1])
    if draft_count:
        c1.info(f"📝 已有 **{draft_count}** 个行业草稿(来自「行业分析」加入预选) → 「✅ 行业确定」落盘")
    else:
        c1.caption("🌟 ETF / 龙头点「加入自选」→ 「🔍 选股 · 选股确定」查看 watchlist")
    with c2:
        if st.button("→ 去行业确定", width="stretch", key="preselect_goto_confirm"):
            try:
                from navigation import goto, PAGE_MARKET_HUB, SUB_INDUSTRY_CONFIRM
                goto(PAGE_MARKET_HUB, sub_tab=SUB_INDUSTRY_CONFIRM)
            except ImportError as e:
                st.error(f"跳转失败:navigation 常量缺失 — {e}(检查 SUB_INDUSTRY_CONFIRM)")
            except Exception as e:
                st.error(f"跳转失败:{e}")
    with c3:
        if st.button("→ 去选股确定", type="primary", width="stretch", key="preselect_goto_screener_confirm"):
            try:
                from navigation import goto, PAGE_SCREENER, SUB_SCREENER_CONFIRM
                goto(PAGE_SCREENER, sub_tab=SUB_SCREENER_CONFIRM)
            except ImportError as e:
                st.error(f"跳转失败:navigation 常量缺失 — {e}(检查 SUB_SCREENER_CONFIRM)")
            except Exception as e:
                st.error(f"跳转失败:{e}")


def render() -> None:
    st.markdown("### 🎯 行业预选 · 深度研判")
    st.caption("选行业 → 看 ETF / 龙头 → 加入自选 → 「选股确定」查看")

    try:
        from funnel import layers as _layers
    except Exception as e:
        st.error(f"funnel 模块加载失败:{e}")
        return

    try:
        import state as _state
        master = _state.industry_master() or {}
    except Exception as e:
        st.error(f"industry_master 加载失败:{e}")
        return

    from tabs.industry._draft_helpers import get_industry_draft
    from tabs.industry._drilldown import build_industry_rank_df, render_industry_drilldown

    focus_names = _layers.get_focus_names() or set()
    focus_list = _layers.get_focus_industries() or []
    _render_guidance(focus_names)

    st.markdown("**初步筛选行业**")
    st.caption(
        "展示「🏭 行业分析」勾选申万一级或点「加入预选」筛选出的 L2 行业 "
        "+ 已在「✅ 行业确定」确认的 focus(标 ✅ 已确认)"
    )

    draft = get_industry_draft()
    draft_idx = _build_draft_index(list(draft))

    rank_df = build_industry_rank_df(master)

    draft_l2 = _render_preliminary_screened_table(draft, master, rank_df, focus_list)

    if not draft_l2:
        st.info("尚无初步筛选 / 已确认行业 — 请到「🏭 行业分析」勾选申万一级或点「加入预选」")
        c1, _ = st.columns([1, 3])
        with c1:
            if st.button("→ 去行业分析", key="preselect_goto_analysis", width="stretch"):
                try:
                    from navigation import goto, PAGE_MARKET_HUB, SUB_INDUSTRY_ANALYSIS
                    goto(PAGE_MARKET_HUB, sub_tab=SUB_INDUSTRY_ANALYSIS)
                except ImportError as e:
                    st.error(f"跳转失败:navigation 常量缺失 — {e}(检查 SUB_INDUSTRY_ANALYSIS)")
                except Exception as e:
                    st.error(f"跳转失败:{e}")
        _render_footer(0)
        return

    st.markdown("**段3 · 行业深度研判**")
    st.caption("PE 速览 + ETF Top3 + 代表公司介绍 + 行业知识")

    def _pe_pct(name: str) -> float:
        if rank_df.empty:
            return 999.0
        try:
            row = rank_df.loc[rank_df["行业"] == name, "PE 分位(10y)"]
            if row.empty:
                return 999.0
            v = row.iloc[0]
            return float(v) if pd.notna(v) else 999.0
        except Exception:
            return 999.0

    pick_options = sorted(draft_l2, key=_pe_pct)

    # options 变化时用 shadow 重水化 widget key,避免 Streamlit 静默重置为首项
    _pick_sig = tuple(pick_options)
    _pick_shadow = st.session_state.get("_persist_preselect_drill_pick")
    if st.session_state.get("_sig_preselect_drill_pick") != _pick_sig:
        st.session_state["_sig_preselect_drill_pick"] = _pick_sig
        if _pick_shadow in pick_options:
            st.session_state["preselect_drill_pick"] = _pick_shadow
        elif st.session_state.get("preselect_drill_pick") not in pick_options:
            st.session_state.pop("preselect_drill_pick", None)

    cur = st.session_state.get("preselect_drill_pick")
    try:
        default_idx = pick_options.index(cur) if cur in pick_options else 0
    except (ValueError, TypeError):
        default_idx = 0

    pick = st.selectbox(
        "🎯 选择 L2 行业研判",
        pick_options,
        index=default_idx,
        key="preselect_drill_pick",
    )
    if pick:
        st.session_state["_persist_preselect_drill_pick"] = pick
    if pick:
        type_for_pick = (
            draft_idx.get(pick, {}).get("type")
            or master.get(pick, {}).get("type")
            or "stalwart"
        )
        render_industry_drilldown(
            pick,
            type_=type_for_pick,
            rank_df=rank_df if not rank_df.empty else None,
            interactive_watchlist=True,
            leaders_mode="intro",
            key_prefix="preselect_drill",
        )

    _render_footer(len(get_industry_draft()))


__all__ = [
    "render",
    "build_guidance_bullets",
    "format_industry_signals",
    "pe_badge_html",
    "layer_badge",
]
