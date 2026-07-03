"""PEG 历史曲线(理杏仁口径).

用于林奇分析法第 4 步「PEG 估值」— 把当前 PEG 单点扩展为时间序列,
让用户看到「当下 PEG 是历史的什么位置」.

数据口径(理杏仁同款,2026-05-06 校准):
    PEG_t = PE-TTM_t ÷ (净利润 3y CAGR × 100)

    其中:
    - PE-TTM_t :从 DuckDB valuation 表取日级序列(最新)
    - 净利润 3y CAGR:基于年报(12 月底)累计净利润 3 段几何平均,
      end = 倒数第二份年报(滞后一年保稳定 — 避免最新年报数据冲击),
      start = end - 3 年.

    为什么用滞后一年?
        美的 case:今天 2026-05,2025 年报已披露:
        - 用 2025 年报 vs 2022 年报 (新口径): CAGR 14.14% → PEG 0.99
        - 用 2024 年报 vs 2021 年报 (理杏仁): CAGR 10.50% → PEG **1.33** ← 与理杏仁页面一致

历史曲线模式:对每一日,基于"截至该日已披露"的最新一份滞后年报算 CAGR.
亏损 / 负增长公司 PEG 不适用 — 返回 NaN,UI 上明确兜底.

老口径 PEG 备查(已废弃,默认不用):
    method='ttm_yoy':PE-TTM ÷ (净利润 TTM YoY × 100) — 单期同比波动大,与理杏仁不一致
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "preson.duckdb"

PROFIT_METRIC = "归属于母公司普通股股东的净利润"  # 中国财报标准口径
# 估值口径(.config/数据更新规则.md):优先扣非,缺时 fallback GAAP — 见 build_peg_series
PE_METRIC_PRIMARY = "PE-TTM(扣非)"
PE_METRIC_FALLBACK = "PE-TTM"
PE_METRIC = PE_METRIC_PRIMARY  # 兼容旧引用


@dataclass
class PEGGrade:
    label: str
    color: str
    advice: str


def grade_peg(peg: float) -> PEGGrade:
    """5 档评级,对照林奇五步框架."""
    if pd.isna(peg):
        return PEGGrade("⚪ 不适用", "gray", "公司未盈利或数据不足")
    if peg < 0.5:
        return PEGGrade("🟢🟢 极度低估", "darkgreen", "重仓买入")
    if peg < 1.0:
        return PEGGrade("🟢 合理偏低", "green", "买入")
    if peg < 1.5:
        return PEGGrade("🟡 略贵", "gold", "观望")
    if peg < 2.0:
        return PEGGrade("🟠 高估", "orange", "减仓")
    return PEGGrade("🔴 严重高估", "red", "清仓")


def _quarter_key(d: pd.Timestamp) -> tuple[int, int]:
    """把日期映射到 (year, quarter_index 1-4)."""
    return d.year, ((d.month - 1) // 3) + 1


def compute_profit_ttm(profit_df: pd.DataFrame) -> pd.DataFrame:
    """从季度累计净利润 DataFrame 还原 TTM.

    输入列:date / value(累计值,Q1/Q2/Q3/Q4 都是 YTD)
    输出列:date / cumulative / ttm
    """
    df = profit_df.sort_values("date").copy()
    df["date"] = pd.to_datetime(df["date"])
    df["q"] = df["date"].apply(_quarter_key)
    df["year"] = df["date"].dt.year
    df["quarter"] = df["date"].apply(lambda d: ((d.month - 1) // 3) + 1)

    # 把每年 Q4 (Dec)累计单独存:annual_by_year
    annual_map = {
        row.year: row.value
        for row in df.itertuples()
        if row.quarter == 4
    }
    same_q_prev_map = {
        (row.year, row.quarter): row.value
        for row in df.itertuples()
    }

    def _ttm(row):
        if row.quarter == 4:
            return row.value
        prev_annual = annual_map.get(row.year - 1)
        prev_same_q = same_q_prev_map.get((row.year - 1, row.quarter))
        if prev_annual is None or prev_same_q is None:
            return None
        return row.value + prev_annual - prev_same_q

    df["cumulative"] = df["value"]
    df["ttm"] = df.apply(_ttm, axis=1)
    return df[["date", "cumulative", "ttm"]]


def compute_ttm_yoy(profit_with_ttm: pd.DataFrame) -> pd.DataFrame:
    """对每个季度的 TTM,找一年前同期的 TTM,算 YoY%.

    返回:date / ttm / ttm_yoy_pct(浮点百分比,如 33.0 = +33%)
    """
    df = profit_with_ttm.sort_values("date").copy().reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])

    # asof merge:每条数据找一年前最近的 TTM
    df["one_year_before"] = df["date"] - pd.DateOffset(years=1)

    df_left = df[["date", "ttm", "one_year_before"]].copy()
    df_left = df_left.rename(columns={"date": "_date"})
    df_right = df[["date", "ttm"]].rename(columns={"date": "_date_prev", "ttm": "ttm_prev"})

    merged = pd.merge_asof(
        df_left.sort_values("one_year_before"),
        df_right.sort_values("_date_prev"),
        left_on="one_year_before",
        right_on="_date_prev",
        direction="backward",
        tolerance=pd.Timedelta(days=400),  # 容忍报告延迟
    )

    merged["ttm_yoy_pct"] = (merged["ttm"] / merged["ttm_prev"] - 1) * 100
    return merged[["_date", "ttm", "ttm_yoy_pct"]].rename(columns={"_date": "date"})


def compute_npat_cagr_3y_lagged(profit_df: pd.DataFrame) -> pd.DataFrame:
    """理杏仁口径 · 净利润 3 年 CAGR · 用倒数第二份年报作 end.

    输入:profit_df 季度累计净利润 [date, value]
    输出:[as_of_date, end_year, start_year, end_value, start_value, cagr_3y_pct]
        as_of_date 列:每个 trading 日 ≥ end+12 个月 → 切到下一份年报
        cagr_3y_pct 是百分数(10.5 = 10.5%)

    每年只产生一条记录,后续会按 date asof 合并到 PE 序列.
    """
    df = profit_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    annuals = df[df["date"].dt.month == 12].sort_values("date").reset_index(drop=True)
    if len(annuals) < 5:
        return pd.DataFrame(columns=["as_of_date", "end_year", "start_year",
                                      "end_value", "start_value", "cagr_3y_pct"])

    rows = []
    for i in range(3, len(annuals)):
        # i 作 end_idx,需要 ≥ 3 才有 start = i-3
        end = annuals.iloc[i]
        start = annuals.iloc[i - 3]
        if end["value"] <= 0 or start["value"] <= 0:
            continue
        cagr = (end["value"] / start["value"]) ** (1 / 3) - 1
        # as_of_date:此 (start, end) 对从 end + 12 个月开始生效
        # 即 2024-12-31 年报作 end 时,需在 2025-12-31 之后才生效(滞后一年)
        # 期间(2024-12-31 ~ 2025-12-31)使用上一份 (start_idx-1, end_idx-1)
        as_of = end["date"] + pd.DateOffset(years=1)
        rows.append({
            "as_of_date": as_of,
            "end_year": end["date"].year,
            "start_year": start["date"].year,
            "end_value": float(end["value"]),
            "start_value": float(start["value"]),
            "cagr_3y_pct": cagr * 100,
        })
    return pd.DataFrame(rows)


def build_peg_series(
    ticker: str,
    db_path: Path | str | None = None,
    lookback_years: int = 5,
    method: str = "cagr_3y_lagged",
) -> pd.DataFrame:
    """主入口.返回 date / pe_ttm / growth_pct / peg DataFrame.

    method:
      'cagr_3y_lagged'(默认,理杏仁口径)— 净利 3y CAGR + 滞后一年的年报作 end
      'ttm_yoy'(已废弃,旧版口径,与理杏仁不一致)— 净利 TTM YoY

    PEG NaN 表示"不适用"(亏损 / 负增长 / 数据不足).
    """
    db = Path(db_path) if db_path else DB_PATH
    if not db.exists():
        return pd.DataFrame(columns=["date", "pe_ttm", "growth_pct", "peg"])

    con = duckdb.connect(str(db), read_only=True)
    try:
        # 扣非主,GAAP 备(.config/数据更新规则.md)
        # fallback 触发条件:扣非 empty,或扣非 max(date) 比 GAAP max(date) 落后 > 540 天
        # (例:000333 美的 扣非锁在 2025-04-30,GAAP 到 2026-05-06,落后 1 年 → 切 GAAP)
        pe_primary = con.execute(
            "SELECT date, value AS pe_ttm FROM valuation "
            "WHERE ticker = ? AND metric = ? AND value IS NOT NULL "
            "ORDER BY date",
            [ticker, PE_METRIC_PRIMARY],
        ).fetchdf()
        pe_fallback = con.execute(
            "SELECT date, value AS pe_ttm FROM valuation "
            "WHERE ticker = ? AND metric = ? AND value IS NOT NULL "
            "ORDER BY date",
            [ticker, PE_METRIC_FALLBACK],
        ).fetchdf()
        if pe_primary.empty:
            pe_df = pe_fallback
        elif not pe_fallback.empty:
            primary_max = pd.to_datetime(pe_primary["date"]).max()
            fallback_max = pd.to_datetime(pe_fallback["date"]).max()
            # 扣非数据停更超过 365 天(扣非数据源典型披露周期)且 GAAP 更新,切 GAAP 兜底
            # 例:000333 美的 扣非锁在 2025-04-30,GAAP 到 2026-05-06,gap=371d → 切 GAAP
            if (fallback_max - primary_max).days > 365:
                pe_df = pe_fallback
            else:
                pe_df = pe_primary
        else:
            pe_df = pe_primary

        profit_df = con.execute(
            "SELECT date, value FROM growth "
            "WHERE ticker = ? AND metric = ? AND value IS NOT NULL "
            "ORDER BY date",
            [ticker, PROFIT_METRIC],
        ).fetchdf()
    finally:
        con.close()

    if pe_df.empty or profit_df.empty:
        return pd.DataFrame(columns=["date", "pe_ttm", "growth_pct", "peg"])

    pe_df["date"] = pd.to_datetime(pe_df["date"])

    if method == "cagr_3y_lagged":
        cagr_df = compute_npat_cagr_3y_lagged(profit_df)
        if cagr_df.empty:
            return pd.DataFrame(columns=["date", "pe_ttm", "growth_pct", "peg"])
        growth_col = "cagr_3y_pct"
        merge_left = cagr_df[["as_of_date", growth_col]].rename(
            columns={"as_of_date": "date", growth_col: "growth_pct"}
        )
    else:
        # 旧 TTM YoY 方法(保留备查,已废弃)
        profit_with_ttm = compute_profit_ttm(profit_df)
        yoy_df = compute_ttm_yoy(profit_with_ttm)
        yoy_df = yoy_df.dropna(subset=["ttm_yoy_pct"]).sort_values("date")
        if yoy_df.empty:
            return pd.DataFrame(columns=["date", "pe_ttm", "growth_pct", "peg"])
        merge_left = yoy_df[["date", "ttm_yoy_pct"]].rename(
            columns={"ttm_yoy_pct": "growth_pct"}
        )

    # 限制 lookback
    if lookback_years and lookback_years > 0:
        cutoff = pe_df["date"].max() - pd.DateOffset(years=lookback_years)
        pe_df = pe_df[pe_df["date"] >= cutoff].copy()

    # asof merge:每个交易日找截至该日"已生效"的增长率(end + 1 年滞后已切换)
    merged = pd.merge_asof(
        pe_df.sort_values("date"),
        merge_left.sort_values("date"),
        on="date",
        direction="backward",
    )

    # PEG:仅在 PE>0 且 growth>0 时有意义
    merged["peg"] = pd.NA
    valid = (merged["pe_ttm"] > 0) & (merged["growth_pct"] > 0)
    merged.loc[valid, "peg"] = (
        merged.loc[valid, "pe_ttm"] / merged.loc[valid, "growth_pct"]
    )

    return merged[["date", "pe_ttm", "growth_pct", "peg"]].reset_index(drop=True)


# ─── Streamlit 渲染层 ──────────────────────────────────────────────
def render_peg_curve(
    ticker: str,
    name: str = "",
    db_path: Path | str | None = None,
    container=None,
    lookback_years: int = 5,
) -> None:
    """画 PEG 时间曲线 + KPI + 评级表.放在 streamlit 容器里."""
    import plotly.graph_objects as go
    import streamlit as st

    target = container if container is not None else st

    df = build_peg_series(ticker, db_path=db_path, lookback_years=lookback_years)

    if df.empty:
        target.info("📊 PEG 数据缺失 — 请确认 valuation / growth 表已抓数")
        return

    valid = df.dropna(subset=["peg"]).copy()
    valid["peg"] = pd.to_numeric(valid["peg"])

    if valid.empty:
        # 看下原因:亏损 or 负增长
        last_yoy = df["growth_pct"].iloc[-1] if not df.empty else None
        last_pe = df["pe_ttm"].iloc[-1] if not df.empty else None
        msg = "⚠️ PEG 不适用 — "
        if last_pe is not None and last_pe < 0:
            msg += f"PE-TTM={last_pe:.1f} 公司亏损"
        elif last_yoy is not None and last_yoy <= 0:
            msg += f"净利润 3y CAGR={last_yoy:.1f}% 增长为负或停滞"
        else:
            msg += "数据不全"
        msg += "。林奇建议改用 PSG / EV-EBITDA / 股息率。"
        target.warning(msg)
        return

    cur = valid.iloc[-1]
    cur_peg = float(cur["peg"])
    cur_pe = float(cur["pe_ttm"])
    cur_yoy = float(cur["growth_pct"])

    g = grade_peg(cur_peg)

    p20 = float(valid["peg"].quantile(0.20))
    p50 = float(valid["peg"].quantile(0.50))
    p80 = float(valid["peg"].quantile(0.80))

    # KPI
    k1, k2, k3, k4 = target.columns(4)
    k1.metric(
        "当前 PEG",
        f"{cur_peg:.2f}",
        help=f"PE-TTM={cur_pe:.1f} ÷ (净利 3y CAGR={cur_yoy:.1f}%) ÷ 100 · 理杏仁口径",
    )
    k2.metric("林奇评级", g.label, help=g.advice)
    k3.metric(
        f"近 {lookback_years} 年中位",
        f"{p50:.2f}",
        delta=f"{cur_peg - p50:+.2f}",
        delta_color="inverse",
    )
    k4.metric("净利 3y CAGR", f"{cur_yoy:+.1f}%",
              help="基于年报数据的 3 段几何平均;end 取倒数第二份年报(滞后一年)")

    # 曲线
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=valid["date"],
            y=valid["peg"],
            mode="lines",
            name="PEG",
            line=dict(color="#1f77b4", width=2),
            hovertemplate="%{x|%Y-%m-%d}<br>PEG=%{y:.2f}<extra></extra>",
        )
    )

    # 评级阈值线
    fig.add_hline(y=1.0, line_dash="dash", line_color="green", opacity=0.6,
                  annotation_text="合理 1.0", annotation_position="right")
    fig.add_hline(y=1.5, line_dash="dash", line_color="orange", opacity=0.6,
                  annotation_text="略贵 1.5", annotation_position="right")
    fig.add_hline(y=2.0, line_dash="dash", line_color="red", opacity=0.6,
                  annotation_text="高估 2.0", annotation_position="right")

    # 历史分位(理杏仁同款 80/50/20)
    fig.add_hline(y=p20, line_dash="dot", line_color="gray", opacity=0.4,
                  annotation_text=f"20%={p20:.2f}", annotation_position="left")
    fig.add_hline(y=p50, line_dash="dot", line_color="gray", opacity=0.4,
                  annotation_text=f"50%={p50:.2f}", annotation_position="left")
    fig.add_hline(y=p80, line_dash="dot", line_color="gray", opacity=0.4,
                  annotation_text=f"80%={p80:.2f}", annotation_position="left")

    # 当前点 marker
    fig.add_trace(
        go.Scatter(
            x=[cur["date"]], y=[cur_peg],
            mode="markers",
            name="当前",
            marker=dict(size=12, color="red", symbol="circle"),
            showlegend=False,
        )
    )

    fig.update_layout(
        height=380,
        title=f"{name or ticker} · PEG 时间曲线(近 {lookback_years} 年 · 林奇五步法第 4 步)",
        hovermode="x unified",
        yaxis_title="PEG",
        xaxis_title=None,
        margin=dict(l=20, r=80, t=50, b=20),
    )

    target.plotly_chart(fig, width="stretch")

    # 评级表
    with target.expander("📊 林奇 PEG 5 档评级表"):
        target.markdown(
            "| PEG 区间 | 评级 | 建议 |\n"
            "|---|---|---|\n"
            "| < 0.5 | 🟢🟢 极度低估 | 重仓买入 |\n"
            "| 0.5 - 1.0 | 🟢 合理偏低 | 买入 |\n"
            "| 1.0 - 1.5 | 🟡 略贵 | 观望 |\n"
            "| 1.5 - 2.0 | 🟠 高估 | 减仓 |\n"
            "| > 2.0 | 🔴 严重高估 | 清仓 |\n\n"
            "📐 **公式**:PEG = PE-TTM ÷ (净利润 3y CAGR × 100) — 理杏仁同口径\n\n"
            "增长率取**滞后一年的年报对照**(end=倒数第二份年报),避免最新年报刚发布带来的数据冲击\n\n"
            "💡 **用法**:看历史曲线在哪个分位带,而不是只看当前数。"
            "曲线靠近 80% 分位 = 估值偏贵;靠近 20% = 估值便宜。"
        )
