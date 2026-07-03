"""黄金 sub-tab ⑨ 实际持仓建议(v2.7 持仓档案基础版)。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ._helpers import *  # noqa: F401,F403


# ─── ⑨ 持仓建议 ────────────────────────────────────────────────────────


POSITION_FILE = ROOT / ".config" / "gold_position.yaml"

# 仓位走廊折扣(同 gold_overheat.yaml position_corridor)
_CORRIDOR_DISCOUNT = {
    "add": 1.00, "add_caution": 0.95, "hold": 0.85,
    "pause_partial": 0.70, "pause": 0.60,
}


def _load_position() -> dict:
    """读 .config/gold_position.yaml,无文件走默认值。"""
    import yaml
    default = {
        "total_assets": 1_231_337,
        "real_etf": {"code": "518660", "name": "黄金 ETF 工银",
                     "value_yuan": 158_246},
        "stock_etf": {"code": "159562", "name": "永赢黄金股",
                      "value_yuan": 81_764, "beta": 1.18},
        "strategic_pct": 20.0,
        "internal_real_pct": 70.0,
    }
    if not POSITION_FILE.exists():
        return default
    try:
        with open(POSITION_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for k, v in default.items():
            if k not in data:
                data[k] = v
        return data
    except Exception:
        return default


def _save_position(d: dict) -> None:
    """写 .config/gold_position.yaml(带 updated_at 时间戳)。"""
    import yaml
    from datetime import date as _date
    POSITION_FILE.parent.mkdir(exist_ok=True)
    d = dict(d)
    d["updated_at"] = str(_date.today())
    with open(POSITION_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(d, f, allow_unicode=True, sort_keys=False)


def _beta_multiplier(verdict_id: str, beta: float) -> tuple[float, str]:
    """β 矩阵命中 — 单一权威读 `gold_overheat.yaml: stock_etf_position`。

    返回 (multiplier, rule_id)。yaml 缺失时回落 1.0 / "unmatched"。
    旧版硬编码 2.0/1.5 阈值在实测 β 范围(0.28~1.20)下永不触发高 β 分支 — 已废弃。
    """
    import yaml
    cfg_path = ROOT / ".tools" / "rules" / "gold_overheat.yaml"
    try:
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        matrix = cfg.get("stock_etf_position", {}).get("matrix", [])
    except Exception:
        matrix = []

    for rule in matrix:
        if verdict_id not in rule.get("when_verdict", []):
            continue
        lt = rule.get("when_beta_lt")
        gte = rule.get("when_beta_gte")
        if lt is not None and not (beta < lt):
            continue
        if gte is not None and not (beta >= gte):
            continue
        return (float(rule.get("position_multiplier", 1.0)),
                rule.get("id", "unmatched"))
    return (1.0, "unmatched")


def _compute_targets(verdict_id: str, strategic_pct: float,
                     total: float, base_real_w: float,
                     stock_beta: float) -> dict:
    """给定 verdict + 战略目标 + 总资产 + β,算实物金/金股的目标占比和金额。"""
    discount = _CORRIDOR_DISCOUNT.get(verdict_id, 1.0)
    base_stock_w = 1.0 - base_real_w
    beta_mult, _ = _beta_multiplier(verdict_id, stock_beta)
    adj_stock_w = base_stock_w * beta_mult
    total_w = base_real_w + adj_stock_w
    after_discount = strategic_pct / 100.0 * discount
    real_pct = after_discount * (base_real_w / total_w)
    stock_pct = after_discount * (adj_stock_w / total_w)
    return {
        "discount": discount,
        "beta_mult": beta_mult,
        "total_gold_pct": after_discount,
        "real_pct": real_pct,
        "stock_pct": stock_pct,
        "real_val": real_pct * total,
        "stock_val": stock_pct * total,
    }


def _render_position_advisor(overheat: dict | None, db_mtime: float) -> None:
    st.markdown("### ⑨ 实际持仓建议 · 红绿灯 × β矩阵 × 战略目标")
    st.caption(
        "📌 输入实际持仓金额,自动按当前红绿灯档位 + 仓位走廊 + β 矩阵给出操作建议。"
        f"保存到 `.config/gold_position.yaml`,下次自动加载。"
    )

    saved = _load_position()

    # ─── 输入区 ───────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        total = st.number_input(
            "💰 总资产(元)", value=int(saved["total_assets"]),
            step=10_000, min_value=10_000, key="pa_total",
        )
        strategic = st.slider(
            "🎯 黄金大类战略目标(%)", min_value=10, max_value=35,
            value=int(saved["strategic_pct"]), step=1, key="pa_strategic",
            help="长期判断下黄金大类占总资产目标比例。看好默认 20%。",
        )
    with c2:
        real_code = st.text_input(
            "实物金 ETF 代码", value=str(saved["real_etf"]["code"]),
            key="pa_real_code",
            help="518880 华安 / 518800 国投 / 518660 工银 等",
        )
        real_val = st.number_input(
            "实物金持仓金额(元)", value=int(saved["real_etf"]["value_yuan"]),
            step=1_000, min_value=0, key="pa_real_val",
        )
    with c3:
        stock_code = st.text_input(
            "金股 ETF 代码", value=str(saved["stock_etf"]["code"]),
            key="pa_stock_code",
        )
        stock_val = st.number_input(
            "金股持仓金额(元)", value=int(saved["stock_etf"]["value_yuan"]),
            step=1_000, min_value=0, key="pa_stock_val",
        )
        stock_beta = st.number_input(
            "金股 β", value=float(saved["stock_etf"].get("beta", 1.18)),
            step=0.05, min_value=0.0, max_value=5.0, key="pa_stock_beta",
            help="金股 ETF 对金价日级回归 β。永赢 159562 实测 1.18(命中 low_beta 1.2× 规则)。",
        )

    save_col, _ = st.columns([1, 5])
    with save_col:
        if st.button("💾 保存持仓配置", key="pa_save"):
            new_data = {
                "total_assets": int(total),
                "real_etf": {
                    "code": real_code,
                    "name": saved["real_etf"].get("name", ""),
                    "value_yuan": int(real_val),
                },
                "stock_etf": {
                    "code": stock_code,
                    "name": saved["stock_etf"].get("name", ""),
                    "value_yuan": int(stock_val),
                    "beta": float(stock_beta),
                },
                "strategic_pct": float(strategic),
                "internal_real_pct": float(saved["internal_real_pct"]),
            }
            try:
                _save_position(new_data)
                st.success(f"✅ 已保存到 .config/gold_position.yaml")
            except Exception as e:
                st.error(f"保存失败:{type(e).__name__}: {e}")

    # ─── 派生量 ───────────────────────────────────────
    real_pct = real_val / total if total > 0 else 0
    stock_pct = stock_val / total if total > 0 else 0
    gold_pct = real_pct + stock_pct
    gold_val = real_val + stock_val
    internal_real_in_gold = real_val / gold_val if gold_val > 0 else 0.0

    # 当前 verdict(从 overheat 拉,失败兜底 add_caution)
    verdict_id = "add_caution"
    verdict_label = "🟡 add_caution(默认兜底)"
    if overheat and "_error" not in overheat:
        verdict_id = overheat.get("verdict_id", "add_caution")
        verdict_label = overheat.get("verdict_label", verdict_id)

    base_real_w = float(saved["internal_real_pct"]) / 100.0
    cur = _compute_targets(verdict_id, float(strategic), float(total),
                           base_real_w, float(stock_beta))
    _, rule_id = _beta_multiplier(verdict_id, float(stock_beta))

    # ─── 当前持仓换算 metrics ───────────────────────
    st.markdown("---")
    st.markdown("#### 📊 当前持仓 vs 目标")

    mA, mB, mC = st.columns(3)
    mA.metric(f"{real_code} 实物金", f"{real_pct*100:.2f}%",
              f"{real_val:,} 元")
    mB.metric(f"{stock_code} 金股", f"{stock_pct*100:.2f}%",
              f"{stock_val:,} 元")
    mC.metric("黄金大类合计", f"{gold_pct*100:.2f}%",
              f"{gold_val:,} 元")

    st.caption(
        f"内部拆分: 实物金 **{internal_real_in_gold*100:.1f}%** / 金股 **{(1-internal_real_in_gold)*100:.1f}%**  ·  "
        f"当前 verdict: **{verdict_label}** · "
        f"走廊折扣 **×{cur['discount']:.2f}**  ·  "
        f"金股 β 矩阵命中: **{rule_id}** (multiplier {cur['beta_mult']:.1f}×)"
    )

    # ─── 对比表 ───────────────────────────────────────
    import pandas as pd
    cmp_rows = [
        {
            "标的": f"{real_code} 实物金",
            "实际占比": f"{real_pct*100:.2f}%",
            "实际金额": f"{real_val:,.0f}",
            "目标占比": f"{cur['real_pct']*100:.2f}%",
            "目标金额": f"{cur['real_val']:,.0f}",
            "缺口 pp": f"{(real_pct - cur['real_pct'])*100:+.2f}",
            "缺口元": f"{(real_val - cur['real_val']):+,.0f}",
        },
        {
            "标的": f"{stock_code} 金股",
            "实际占比": f"{stock_pct*100:.2f}%",
            "实际金额": f"{stock_val:,.0f}",
            "目标占比": f"{cur['stock_pct']*100:.2f}%",
            "目标金额": f"{cur['stock_val']:,.0f}",
            "缺口 pp": f"{(stock_pct - cur['stock_pct'])*100:+.2f}",
            "缺口元": f"{(stock_val - cur['stock_val']):+,.0f}",
        },
        {
            "标的": "黄金大类合计",
            "实际占比": f"{gold_pct*100:.2f}%",
            "实际金额": f"{gold_val:,.0f}",
            "目标占比": f"{cur['total_gold_pct']*100:.2f}%",
            "目标金额": f"{cur['real_val']+cur['stock_val']:,.0f}",
            "缺口 pp": f"{(gold_pct - cur['total_gold_pct'])*100:+.2f}",
            "缺口元": f"{(gold_val - cur['real_val'] - cur['stock_val']):+,.0f}",
        },
    ]
    st.dataframe(pd.DataFrame(cmp_rows), hide_index=True, width="stretch")

    # ─── 操作建议 banner ─────────────────────────────
    def _advice(gap_pp: float, gap_yuan: float, label: str) -> str:
        if abs(gap_pp) < 1.0:
            return f"✅ <b>{label} 持有不动</b>(缺口 {gap_pp:+.2f}pp,在 ±1pp 容忍带内)"
        if abs(gap_pp) < 2.0:
            verb = "减" if gap_yuan > 0 else "加"
            return (f"🟡 <b>{label} 容忍带边缘</b>: 可选 {verb} "
                    f"{abs(gap_yuan):,.0f} 元(缺口 {gap_pp:+.2f}pp)")
        if gap_yuan > 0:
            return (f"🔴 <b>减 {label}</b>: 卖出 {gap_yuan:,.0f} 元 "
                    f"(超目标 {gap_pp:.2f}pp)")
        return (f"🟢 <b>加 {label}</b>: 买入 {-gap_yuan:,.0f} 元 "
                f"(差目标 {-gap_pp:.2f}pp)")

    adv_real = _advice((real_pct - cur['real_pct']) * 100,
                       real_val - cur['real_val'],
                       f"实物金 {real_code}")
    adv_stock = _advice((stock_pct - cur['stock_pct']) * 100,
                        stock_val - cur['stock_val'],
                        f"金股 {stock_code}")
    adv_total = _advice((gold_pct - cur['total_gold_pct']) * 100,
                        gold_val - cur['real_val'] - cur['stock_val'],
                        "黄金大类合计")

    st.markdown(
        f'<div style="padding:14px 18px;border-radius:8px;'
        f'border-left:4px solid #f59e0b;background:rgba(245,158,11,0.08);'
        f'margin-top:12px">'
        f'<div style="font-size:13px;color:#888">📌 当前 {verdict_label} 下的操作建议</div>'
        f'<div style="font-size:14px;margin-top:8px">{adv_real}</div>'
        f'<div style="font-size:14px;margin-top:4px">{adv_stock}</div>'
        f'<div style="font-size:14px;margin-top:4px">{adv_total}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ─── 切档预案 ─────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 📅 切档预案 · 红绿灯切到其他档位时该怎么做")
    st.caption("基于当前持仓和战略目标,预测红绿灯切到 5 档时的目标 + 需要操作。")

    plan_rows = []
    for v in ["add", "add_caution", "hold", "pause_partial", "pause"]:
        t = _compute_targets(v, float(strategic), float(total),
                             base_real_w, float(stock_beta))
        plan_rows.append({
            "切档": f"{'⭐ ' if v == verdict_id else '   '}{v}",
            "走廊折扣": f"×{t['discount']:.2f}",
            "实物金目标": f"{t['real_pct']*100:.2f}% / {t['real_val']:,.0f}",
            "金股目标": f"{t['stock_pct']*100:.2f}% / {t['stock_val']:,.0f}",
            "实物金调整": f"{(t['real_val'] - real_val):+,.0f}",
            "金股调整": f"{(t['stock_val'] - stock_val):+,.0f}",
            "总和调整": f"{(t['real_val'] + t['stock_val'] - real_val - stock_val):+,.0f}",
        })
    st.dataframe(pd.DataFrame(plan_rows), hide_index=True, width="stretch")
    st.caption("⭐ 标记当前档位 · 调整列正数 = 加仓 / 负数 = 减仓")


__all__ = ["render"]
