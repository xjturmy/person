"""Phase B2/B3 · 公司 Tab 内「行业横评」区块渲染。

入口:`render_industry_compare(ticker, name)`,在 Streamlit 上下文调用。
依赖 industry_percentile.industry_percentile / all_metrics_summary。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

import industry_percentile as ipx  # noqa: E402


# 6 张卡片用的指标:估值 / 盈利 / 成长 / PEG / F-Score / 规模
CARD_METRICS = [
    ("PE", "估值", "倍"),
    ("PB", "估值", "倍"),
    ("ROE", "盈利", "%"),
    ("毛利率", "盈利", "%"),
    ("营收YoY", "成长", "%"),
    ("净利YoY", "成长", "%"),
    ("PEG", "估值", ""),
    ("F-Score lite", "质量", "/4"),
]


def _fmt_value(v: float | None, unit: str) -> str:
    if v is None:
        return "—"
    if unit == "%":
        return f"{v:.1f}%"
    if unit == "/4":
        return f"{v:.0f}/4"
    if unit == "倍":
        return f"{v:.1f}×"
    if unit == "":
        return f"{v:.2f}"
    return f"{v:.2f}{unit}"


def _percentile_bar_html(pct: float | None, label: str, direction: str) -> str:
    """30%/70% 三分阶段彩色条形;label 显示在右侧。"""
    if pct is None:
        return f'<div style="color:#9CA3AF;font-size:12px;">分位 —</div>'
    pct_clamped = max(0, min(100, pct))
    # 颜色规则:high_good 高分位绿色,low_good 低分位绿色
    if direction == "high_good":
        color = "#10B981" if pct >= 70 else ("#F59E0B" if pct >= 30 else "#EF4444")
    else:
        color = "#10B981" if pct <= 30 else ("#F59E0B" if pct <= 70 else "#EF4444")
    return (
        f'<div style="display:flex;align-items:center;gap:8px;font-size:12px;">'
        f'<div style="flex:1;background:#F3F4F6;height:8px;border-radius:4px;position:relative;">'
        f'<div style="position:absolute;left:0;top:0;height:100%;width:{pct_clamped:.0f}%;background:{color};border-radius:4px;"></div>'
        f'<div style="position:absolute;left:30%;top:-2px;height:12px;width:1px;background:#9CA3AF;"></div>'
        f'<div style="position:absolute;left:70%;top:-2px;height:12px;width:1px;background:#9CA3AF;"></div>'
        f'</div>'
        f'<div style="color:{color};font-weight:600;width:48px;text-align:right;">{pct:.0f}%</div>'
        f'<div style="color:#6B7280;width:40px;">{label}</div>'
        f'</div>'
    )


def _card_html(title: str, ip: ipx.IndustryPercentile | None, unit: str) -> str:
    """单指标卡片 HTML。"""
    if ip is None or ip.self_value is None:
        return (
            f'<div style="border:1px solid #E5E7EB;border-radius:8px;padding:12px 14px;'
            f'background:#FAFAFA;height:130px;">'
            f'<div style="font-size:12px;color:#6B7280;">{title}</div>'
            f'<div style="font-size:18px;color:#9CA3AF;margin-top:4px;">—</div>'
            f'<div style="font-size:11px;color:#9CA3AF;margin-top:8px;">无数据</div>'
            f'</div>'
        )
    self_s = _fmt_value(ip.self_value, unit)
    p25_s = _fmt_value(ip.peer_p25, unit)
    p50_s = _fmt_value(ip.peer_p50, unit)
    p75_s = _fmt_value(ip.peer_p75, unit)
    bar = _percentile_bar_html(ip.percentile, ip.label, ip.direction)
    return (
        f'<div style="border:1px solid #E5E7EB;border-radius:8px;padding:12px 14px;'
        f'background:#FFFFFF;height:130px;">'
        f'<div style="font-size:12px;color:#6B7280;">{title}</div>'
        f'<div style="font-size:22px;font-weight:700;color:#111827;margin-top:2px;">{self_s}</div>'
        f'<div style="font-size:11px;color:#6B7280;margin-top:4px;">'
        f'同行 P25/中位/P75: {p25_s} / {p50_s} / {p75_s}({ip.n_peers} 家)'
        f'</div>'
        f'<div style="margin-top:10px;">{bar}</div>'
        f'</div>'
    )


def render_industry_compare(ticker: str, name: str) -> None:
    """
    在公司 Tab 内渲染「行业横评」区块。

    布局:
      - 顶部:6 卡片(估值2 + 盈利2 + 成长2 + PEG + F-Score)4×2 网格
      - 下方:同行表格(self 高亮)
    """
    st.markdown(f"### 🏭 行业横评 · 同行业 N 家并排 + 分位")

    # 一次性查所有指标,避免多次开关连接
    summary = ipx.all_metrics_summary(ticker)
    if summary.empty:
        st.info("当前公司无同行数据(港股或 peers.duckdb 未更新)")
        return

    # 取行业名(从任一指标的 IndustryPercentile 拿)
    sample = ipx.industry_percentile(ticker, "PE")
    industry = sample.industry if sample else ""
    n_peers = sample.n_peers if sample else 0

    st.caption(f"行业:**{industry}**  ·  同行 {n_peers} 家  ·  数据源 peers.duckdb")

    # 6 卡片网格(2 行 4 列)
    rows = [CARD_METRICS[:4], CARD_METRICS[4:]]
    for row in rows:
        cols = st.columns(4)
        for col, (m, _cat, unit) in zip(cols, row):
            ip = ipx.industry_percentile(ticker, m)
            with col:
                st.markdown(_card_html(m, ip, unit), unsafe_allow_html=True)

    st.markdown("")  # 间距

    # 同行明细表(B3)
    with st.expander(f"📊 同行 {n_peers} 家明细数据", expanded=False):
        # 取任一指标的 peer_rows + 所有指标横扩展
        rows_all = []
        for r in (sample.peer_rows.itertuples(index=False) if sample else []):
            d = r._asdict()
            row_data = {
                "公司": d.get("peer_name", ""),
                "代码": d.get("peer_ticker", ""),
                "市值(亿)": round(d.get("peer_market_cap", 0) / 1e8, 0) if d.get("peer_market_cap") else None,
            }
            # 补充其他指标(从 all_metrics_summary 已有的不重复查)
            rows_all.append(row_data)

        # 用 industry_percentile 的 peer_rows 拼:每指标查一次,合并
        merged = pd.DataFrame()
        for m, _cat, unit in CARD_METRICS:
            ip2 = ipx.industry_percentile(ticker, m)
            if ip2 is None or ip2.peer_rows.empty:
                continue
            sub = ip2.peer_rows[["peer_ticker", "peer_name", "value"]].copy()
            sub = sub.rename(columns={"value": m})
            if merged.empty:
                merged = sub
            else:
                merged = merged.merge(sub.drop(columns=["peer_name"]),
                                       on="peer_ticker", how="outer")

        if not merged.empty:
            # 加 self 行
            self_row = {"peer_ticker": ticker, "peer_name": name + " ⭐"}
            for m, _, _ in CARD_METRICS:
                if m == "市值(亿)":
                    continue
                ip3 = ipx.industry_percentile(ticker, m)
                self_row[m] = ip3.self_value if ip3 else None
            merged_full = pd.concat([pd.DataFrame([self_row]), merged], ignore_index=True)
            merged_full = merged_full.rename(columns={"peer_ticker": "代码", "peer_name": "公司"})
            st.dataframe(merged_full, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ 下载行业横评 CSV",
                merged_full.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"industry_compare_{ticker}.csv",
                mime="text/csv", key=f"dl_industry_{ticker}",
            )
        else:
            st.info("同行明细数据为空")

    st.caption("💡 分位条形:绿色=优(low_good 时低分位 / high_good 时高分位)| 黄色=合理 | 红色=劣")
