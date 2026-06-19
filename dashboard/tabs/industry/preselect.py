"""tabs.industry.preselect · 行业预选(勾选 → 草稿).

数据流:
  industry_master.yaml 全部 L2(去掉已 focus) → 用户勾选/打类型/写备注
    → funnel.session.set_draft(FUNNEL_INDUSTRY_DRAFT, [...])
  不写 yaml。
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
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

# 林奇 6 类
_TYPE_OPTIONS = [
    "stalwart", "fast_grower", "cyclical", "slow_grower", "bank", "insurance",
]

# 康波进攻层覆盖缺口(计划硬编码)
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
    body = "\n".join(f"- {b}" for b in bullets)
    st.markdown("**段1 · 筛选指引**")
    st.info(body)


def render() -> None:
    st.markdown("### 🎯 行业预选 · 勾选感兴趣的行业")
    st.caption("勾选 → 确认后到「✅ 行业确定」落盘到 focus_industries.yaml")

    # 数据
    try:
        from funnel import layers as _layers
        from funnel import session as _session
    except Exception as e:
        st.error(f"funnel 模块加载失败:{e}")
        return

    try:
        import state as _state
        master = _state.industry_master() or {}
    except Exception as e:
        st.error(f"industry_master 加载失败:{e}")
        return

    focus_names = _layers.get_focus_names() or set()
    _render_guidance(focus_names)

    layer_map = _industry_layer_map()
    held_industries = _industries_with_holdings()

    # 候选池 — 全 L2 去掉已 focus
    candidates: dict[str, list[dict]] = defaultdict(list)
    for name, meta in sorted(master.items()):
        if name in focus_names:
            continue
        candidates[(meta.get("sw_l1") or "—")].append(meta)

    if not candidates:
        st.info("所有行业已 focus,无可预选项")
        return

    # 旧草稿(在 UI 之间保持)
    draft = _session.get_draft(_session.FUNNEL_INDUSTRY_DRAFT, []) or []
    draft_idx = _build_draft_index(list(draft))

    new_draft: list[dict] = []

    for sw_l1, items in sorted(candidates.items()):
        with st.expander(f"📂 {sw_l1} · {len(items)} 个 L2 行业", expanded=False):
            for meta in items:
                name = meta.get("name")
                if not name:
                    continue
                default_type = (
                    draft_idx.get(name, {}).get("type") or meta.get("type") or "stalwart"
                )
                default_weight = float(draft_idx.get(name, {}).get("weight") or 1.0)
                default_note = str(draft_idx.get(name, {}).get("note") or "")
                checked_default = name in draft_idx

                pct = _cached_percentile(name)
                cyc = _cached_cycle(name)
                pe_pct = pct.get("pe_percentile_10y")
                signals = format_industry_signals(
                    name,
                    pe_pct=pe_pct,
                    phase=cyc.get("phase"),
                    layer=layer_map.get(name),
                    has_holding=name in held_industries,
                )
                summary = (meta.get("summary") or "")[:40]

                cols = st.columns([0.5, 2.8, 1.4, 1, 2.5])
                checked = cols[0].checkbox(
                    "勾选", value=checked_default,
                    key=f"preselect_chk_{name}",
                    label_visibility="collapsed",
                )
                cols[1].markdown(
                    f"**{name}** {signals}"
                    f"<br><small style='color:#6b7280'>{summary}…</small>",
                    unsafe_allow_html=True,
                )
                t_idx = _TYPE_OPTIONS.index(default_type) if default_type in _TYPE_OPTIONS else 0
                type_ = cols[2].selectbox(
                    "type",
                    _TYPE_OPTIONS,
                    index=t_idx,
                    key=f"preselect_type_{name}",
                    label_visibility="collapsed",
                )
                weight = cols[3].number_input(
                    "weight",
                    min_value=0.0, max_value=10.0, value=default_weight, step=0.5,
                    key=f"preselect_w_{name}",
                    label_visibility="collapsed",
                )
                note = cols[4].text_input(
                    "note", value=default_note, key=f"preselect_note_{name}",
                    label_visibility="collapsed", placeholder="备注/理由",
                )
                if checked:
                    new_draft.append({
                        "industry": name,
                        "type": type_,
                        "weight": float(weight),
                        "note": note,
                    })

    # 同步草稿 → session
    _session.set_draft(_session.FUNNEL_INDUSTRY_DRAFT, new_draft)
    st.markdown("---")
    st.success(f"📝 当前草稿:**{len(new_draft)}** 个行业 — 切到「✅ 行业确定」点「确认新增」落盘")


__all__ = [
    "render",
    "build_guidance_bullets",
    "format_industry_signals",
    "pe_badge_html",
    "layer_badge",
]
