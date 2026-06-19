"""黄金 sub-tab ⑧ 策略回溯(含按日对照 + 诊断面板)。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ._helpers import *  # noqa: F401,F403


# ─── ⑧ 策略回溯 ────────────────────────────────────────────────────────


@st.cache_data(ttl=300, show_spinner=False)
def _backtest_cached(
    db_mtime: float,
    start: str, end: str,
    init_total: float, init_gold: float,
    upper_mult: float, lower_mult: float,
    step_shares: int, confirm_days: int,
    etf_code: str = "518880",
    price_table: str = "gold_etf_prices",
) -> dict:
    """缓存回测结果(把 BacktestResult 拆成可序列化字典)。"""
    from pathlib import Path as _P
    mult = {
        "add": upper_mult,
        "add_caution": (1.0 + upper_mult) / 2,
        "hold": 1.0,
        "pause_partial": (1.0 + lower_mult) / 2,
        "pause": lower_mult,
    }
    r = _backtest_run(
        db_path=_BACKTEST_DB if _P(str(_BACKTEST_DB)).exists() else _BACKTEST_DB,
        etf_code=etf_code, price_table=price_table,
        start_date=start, end_date=end,
        init_total=init_total, init_gold_value=init_gold,
        multipliers=mult, step_shares=int(step_shares),
        confirm_days=int(confirm_days),
    )
    return {
        "daily": r.daily, "trades": r.trades, "switches": r.switches,
        "summary": r.summary, "params": r.params, "multipliers": mult,
    }


@st.cache_data(ttl=300, show_spinner=False)
def _diagnose_cached(
    db_mtime: float,
    start: str, end: str,
    init_total: float, init_gold: float,
    upper_mult: float, lower_mult: float,
    step_shares: int, confirm_days: int,
    etf_code: str = "518880",
    price_table: str = "gold_etf_prices",
) -> dict:
    """缓存诊断结果(重新跑 run+diagnose,把 DiagnosticsResult 拆成字典)。"""
    from gold.backtest import run as _run, diagnose as _diag, GOLD_DB
    mult = {
        "add": upper_mult,
        "add_caution": (1.0 + upper_mult) / 2,
        "hold": 1.0,
        "pause_partial": (1.0 + lower_mult) / 2,
        "pause": lower_mult,
    }
    r = _run(
        db_path=GOLD_DB,
        etf_code=etf_code, price_table=price_table,
        start_date=start, end_date=end,
        init_total=init_total, init_gold_value=init_gold,
        multipliers=mult, step_shares=int(step_shares),
        confirm_days=int(confirm_days),
    )
    d = _diag(
        r, db_path=GOLD_DB, etf_code=etf_code, price_table=price_table,
        init_total=init_total, init_gold_value=init_gold, multipliers=mult,
        step_shares=int(step_shares),
        current_confirm_days=int(confirm_days),
    )
    return {
        "verdict_stay": d.verdict_stay,
        "extreme_misalign": d.extreme_misalign,
        "confirm_sensitivity": d.confirm_sensitivity,
        "current_status": d.current_status,
        "advice": d.advice,
    }


def _render_backtest(db_mtime: float) -> None:
    st.markdown("### ⑧ 策略回溯 · 红绿灯择时 vs 一直持有")
    st.caption(
        "📚 复盘「过去一段时间按红绿灯信号操作」与「一直持有」的收益差异 · "
        "标注实际买卖时点、信号切换、最终份额。"
        "**默认参数**:基数 20w / 上限 30w / 下限 10w / 步长 2w 份/次 / 信号稳定 7 天才动。"
    )

    if not _BACKTEST_AVAILABLE:
        st.error("回测引擎未加载:`gold_backtest_engine.py` 不在 PYTHONPATH")
        return

    # ─── 参数面板 ──────────────────────────────────────────
    from datetime import date, timedelta
    today = date.today()

    # 标的字典(切换时按 β 矩阵自动绑定上下限/步长/数据下限)
    TARGETS = {
        "518880 · 实物金 ETF (默认)": {
            "etf_code": "518880",
            "price_table": "gold_etf_prices",
            "data_min": date(2021, 5, 11),
            "default_upper": 1.5, "default_lower": 0.5,
            "default_step": 20_000,
            "presets": ["最近 1 年", "最近 3 年", "最近 5 年", "自定义"],
            "note": "实物金红绿灯,base 倍数(1.5/0.5)",
        },
        "159562 · 永赢黄金股 ETF (β=1.18 · β矩阵推荐)": {
            "etf_code": "159562",
            "price_table": "gold_stock_etf_prices",
            "data_min": date(2025, 5, 12),
            # β矩阵: low-β(<1.5) 加仓 1.2× / 减仓 0.8× → base × β_mult
            # add: 1.5×1.2=1.8 ; pause: 0.5×0.8=0.4
            "default_upper": 1.8, "default_lower": 0.4,
            "default_step": 100_000,  # 永赢单价低,基数 ~13.5w 份,步长按比例放大
            "presets": ["最近 1 年", "自定义"],  # 永赢数据仅 1 年
            "note": "金股共用实物金信号 + β 矩阵 (β=1.18 命中 low-β 规则,加仓 1.2× / 减仓 0.8×)",
        },
    }
    target_label = st.selectbox(
        "📦 回测标的", options=list(TARGETS.keys()),
        index=0, key="bt_target",
    )
    cfg = TARGETS[target_label]
    etf_code = cfg["etf_code"]
    price_table = cfg["price_table"]
    data_min = cfg["data_min"]
    st.caption(f"📌 {cfg['note']}  ·  数据范围 {data_min} → {today}")

    preset = st.radio(
        "📅 回测区间",
        options=cfg["presets"],
        index=0, horizontal=True,
        key=f"bt_preset_{etf_code}",  # 标的切换时 reset
    )
    preset_days = {"最近 1 年": 365, "最近 3 年": 1095, "最近 5 年": 1825}

    with st.expander("⚙️ 参数(可调)", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if preset == "自定义":
                start_d = st.date_input(
                    "起始日期", max(today - timedelta(days=365), data_min),
                    min_value=data_min, max_value=today,
                    key=f"bt_start_{etf_code}")
            else:
                start_d = max(today - timedelta(days=preset_days[preset]), data_min)
                st.markdown(f"**起始日期**  \n{start_d}")
            init_total = st.number_input(
                "初始本金(元)", value=1_000_000, step=10_000,
                min_value=100_000, key="bt_init")
        with c2:
            if preset == "自定义":
                end_d = st.date_input(
                    "结束日期", today,
                    min_value=data_min, max_value=today,
                    key=f"bt_end_{etf_code}")
            else:
                end_d = today
                st.markdown(f"**结束日期**  \n{end_d}")
            init_gold = st.number_input(
                "初始黄金投入(元)", value=200_000, step=10_000,
                min_value=10_000, key="bt_gold")
        with c3:
            upper_m = st.slider(
                "上限倍数(基数×)", 1.1, 2.5,
                value=cfg["default_upper"], step=0.05,
                help="add 信号目标份额倍数。1.5 = 基数 1.5 倍 = 上限",
                key=f"bt_upper_{etf_code}")
            step_sh = st.number_input(
                "步长(份/次)", value=cfg["default_step"], step=1_000,
                min_value=1_000, key=f"bt_step_{etf_code}")
        with c4:
            lower_m = st.slider(
                "下限倍数(基数×)", 0.0, 0.9,
                value=cfg["default_lower"], step=0.05,
                help="pause 信号目标份额倍数。0.5 = 基数 0.5 倍 = 下限",
                key=f"bt_lower_{etf_code}")
            confirm_d = st.number_input(
                "信号确认天数", value=7, step=1,
                min_value=0, max_value=30,
                help="新档位需稳定 N 天才执行;0=立即,推荐 7",
                key="bt_confirm")

    # ─── 跑回测 ──────────────────────────────────────────
    try:
        res = _backtest_cached(
            db_mtime, str(start_d), str(end_d),
            float(init_total), float(init_gold),
            float(upper_m), float(lower_m),
            int(step_sh), int(confirm_d),
            etf_code=etf_code, price_table=price_table,
        )
    except Exception as e:
        st.error(f"回测失败:{type(e).__name__}: {e}")
        return

    summary = res["summary"]
    if "_error" in summary:
        st.error(f"⚠️ {summary['_error']}")
        return

    daily = res["daily"]
    trades = res["trades"]
    switches = res["switches"]

    # ─── 摘要 metrics ─────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "A · 一直持有 终值",
        f"{summary['A_final']:,.0f}",
        f"{summary['A_return_pct']:+.2f}%",
    )
    c2.metric(
        "E · 红绿灯策略 终值",
        f"{summary['E_final']:,.0f}",
        f"{summary['E_return_pct']:+.2f}%",
    )
    c3.metric(
        "策略 - 持有 差异",
        f"{summary['diff']:+,.0f} 元",
        f"{summary['diff_pct']:+.2f}pp",
    )
    c4.metric(
        "操作次数",
        f"{summary['n_trades']} 笔",
        f"{summary['n_buy']} 买 / {summary['n_sell']} 卖",
    )

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("A 最大回撤", f"{summary['A_mdd']:.2f}%")
    c6.metric("E 最大回撤", f"{summary['E_mdd']:.2f}%",
              f"{summary['E_mdd'] - summary['A_mdd']:+.2f}pp vs A",
              delta_color="inverse")
    c7.metric("金价涨幅(区间)", f"{summary['price_change_pct']:+.2f}%",
              f"{summary['start_price']:.3f} → {summary['end_price']:.3f}")
    c8.metric("终态份额", f"{summary['end_shares']:,.0f}",
              f"现金 {summary['end_cash']:,.0f}")

    # 档位说明
    tm = summary["target_map"]
    st.caption(
        f"📐 档位映射(基数 {summary['base_shares']:,.0f} 份):"
        f"add → **{tm['add']:,}** 份  ·  "
        f"add_caution → {tm['add_caution']:,} 份  ·  "
        f"hold → {tm['hold']:,} 份  ·  "
        f"pause_partial → {tm['pause_partial']:,} 份  ·  "
        f"pause → **{tm['pause']:,}** 份"
    )

    # ─── 信号背景显示开关 ─────────────────────────────────
    bg_col1, bg_col2, bg_col3 = st.columns([2, 3, 5])
    with bg_col1:
        show_bg = st.checkbox("🎨 显示信号区段背景", value=True,
                              key="bt_show_signal_bg",
                              help="把每日 verdict (add/hold/pause...) 用彩色背景标到价格图上")
    with bg_col2:
        bg_opacity = st.slider("透明度", 0.10, 1.00, 0.55, 0.05,
                               key="bt_bg_opacity",
                               disabled=not show_bg,
                               help="拉到 0.7-0.9 可显著加深背景色")

    # ─── 主图:价格 + 买卖点 + 信号背景 ───────────────────
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.08,
        subplot_titles=("ETF 价格 + 买卖点 + 信号区段", "总资产对比"),
    )

    # 1) 信号背景着色(分段填充) — 可通过 show_bg 开关控制
    daily_r = daily.reset_index()
    if show_bg:
        # 5 档颜色基于 RGB,透明度由 slider 控制
        verdict_rgb = {
            "add":           "16, 185, 129",    # 浅绿
            "add_caution":   "251, 191, 36",    # 浅黄
            "hold":          "245, 158, 11",    # 橙黄
            "pause_partial": "220, 38, 38",     # 浅红
            "pause":         "153, 27, 27",     # 深红
        }
        # pause 默认再加深一点(+0.08)更醒目
        # 找连续 verdict 区段(把 x1 推到下个区段起点,避免单日区段零宽不可见)
        daily_r["block"] = (daily_r["verdict"] != daily_r["verdict"].shift()).cumsum()
        _blocks = list(daily_r.groupby("block"))
        for _i, (_, blk) in enumerate(_blocks):
            v = blk.iloc[0]["verdict"]
            x0 = blk["date"].iloc[0]
            if _i + 1 < len(_blocks):
                x1 = _blocks[_i + 1][1]["date"].iloc[0]
            else:
                x1 = blk["date"].iloc[-1] + pd.Timedelta(days=1)
            rgb = verdict_rgb.get(v, "128, 128, 128")
            op = min(1.0, bg_opacity + 0.08) if v == "pause" else bg_opacity
            fig.add_vrect(
                x0=x0, x1=x1,
                fillcolor=f"rgba({rgb}, {op:.2f})",
                line_width=0, layer="below", row=1, col=1,
            )

    # 2) ETF 价格
    fig.add_trace(go.Scatter(
        x=daily_r["date"], y=daily_r["close"],
        mode="lines", name="518880 收盘",
        line=dict(color="#f59e0b", width=2),
        hovertemplate="%{x|%Y-%m-%d}<br>收盘 %{y:.3f}<extra></extra>",
    ), row=1, col=1)

    # 3) 买卖点散点
    if len(trades) > 0:
        buys = trades[trades["action"] == "BUY"]
        sells = trades[trades["action"] == "SELL"]
        if len(buys):
            fig.add_trace(go.Scatter(
                x=buys["date"], y=buys["price"],
                mode="markers",
                name="买入 ▲",
                marker=dict(symbol="triangle-up", size=14,
                            color="#10b981",
                            line=dict(color="white", width=1.5)),
                hovertemplate=("<b>买入</b><br>%{x|%Y-%m-%d}<br>"
                               "单价 %{y:.3f}<br>"
                               "份额 %{customdata[0]:,.0f}<br>"
                               "金额 %{customdata[1]:,.0f}<br>"
                               "触发 %{customdata[2]}<extra></extra>"),
                customdata=buys[["qty", "amount", "verdict"]].values,
            ), row=1, col=1)
        if len(sells):
            fig.add_trace(go.Scatter(
                x=sells["date"], y=sells["price"],
                mode="markers",
                name="卖出 ▼",
                marker=dict(symbol="triangle-down", size=14,
                            color="#dc2626",
                            line=dict(color="white", width=1.5)),
                hovertemplate=("<b>卖出</b><br>%{x|%Y-%m-%d}<br>"
                               "单价 %{y:.3f}<br>"
                               "份额 %{customdata[0]:,.0f}<br>"
                               "金额 %{customdata[1]:,.0f}<br>"
                               "触发 %{customdata[2]}<extra></extra>"),
                customdata=sells[["qty", "amount", "verdict"]].values,
            ), row=1, col=1)

    # 4) 总资产曲线对比
    fig.add_trace(go.Scatter(
        x=daily_r["date"], y=daily_r["total_A"],
        mode="lines", name="A · 一直持有",
        line=dict(color="#94a3b8", width=2, dash="dot"),
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=daily_r["date"], y=daily_r["total_E"],
        mode="lines", name="E · 红绿灯策略",
        line=dict(color="#f59e0b", width=2.5),
    ), row=2, col=1)

    fig.update_layout(
        height=700, hovermode="x unified",
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
    )
    fig.update_yaxes(title_text="价格(元)", row=1, col=1)
    fig.update_yaxes(title_text="总资产(元)", row=2, col=1)
    st.plotly_chart(fig, use_container_width=True)

    # ─── 信号图例(仅在显示背景时才展示)─────────────────
    if show_bg:
        st.caption(
            "🟢 浅绿背景 = `add`(全绿,目标上限)  ·  "
            "🟡 浅黄背景 = `add_caution`(1+ 黄,目标 ↓ 1 档)  ·  "
            "🟠 橙黄 = `hold`  ·  🔴 浅红 = `pause_partial`  ·  ⛔ 深红 = `pause`"
        )

    # ─── 交易明细 + 信号切换 ──────────────────────────────
    cA, cB = st.columns(2)

    with cA:
        st.markdown(f"#### 📋 交易明细({len(trades)} 笔)")
        if len(trades) > 0:
            disp = trades.copy()
            disp["date"] = pd.to_datetime(disp["date"]).dt.strftime("%Y-%m-%d")
            disp["qty"] = disp["qty"].astype(int)
            disp["price"] = disp["price"].round(3)
            disp["amount"] = disp["amount"].round(0).astype(int)
            disp["shares_after"] = disp["shares_after"].astype(int)
            disp = disp[["date", "action", "qty", "price",
                         "amount", "verdict", "shares_after"]]
            disp.columns = ["日期", "动作", "份额", "单价",
                            "金额", "触发档", "持仓后"]
            st.dataframe(disp, use_container_width=True, hide_index=True)
        else:
            st.info("回测区间内没有产生操作(信号始终在档位内 / 现金不足 / 确认期过滤)")

    with cB:
        st.markdown(f"#### 🚦 信号切换记录({len(switches)} 次)")
        if len(switches) > 0:
            sd = switches.copy()
            sd["date"] = pd.to_datetime(sd["date"]).dt.strftime("%Y-%m-%d")
            sd.columns = ["日期", "前档", "新档", "红", "黄", "绿"]
            st.dataframe(sd, use_container_width=True, hide_index=True,
                         height=min(420, 35 + 35 * len(sd)))
        else:
            st.info("区间内无信号切换")

    # ─── 按日红绿灯对照表 ─────────────────────────────────
    st.markdown("---")
    st.markdown("#### 📅 按日红绿灯对照(逐日扫读)")
    st.caption("每行 = 1 个交易日。切档/操作日已高亮。默认显示最近 30 天。")

    show_all = st.checkbox(
        "显示全部交易日(默认仅最近 30 天)",
        value=False, key="bt_daily_all",
    )
    daily_disp = daily_r.copy()
    if not show_all:
        daily_disp = daily_disp.tail(30)

    # 计算 vs 持有差
    daily_disp["vs_hold"] = daily_disp["total_E"] - daily_disp["total_A"]

    # 格式化
    daily_disp["date"] = pd.to_datetime(daily_disp["date"]).dt.strftime("%Y-%m-%d")
    daily_disp["close"] = daily_disp["close"].round(3)
    daily_disp["shares"] = daily_disp["shares"].astype(int)
    daily_disp["total_E"] = daily_disp["total_E"].round(0).astype(int)
    daily_disp["vs_hold"] = daily_disp["vs_hold"].round(0).astype(int)
    daily_disp["qty"] = daily_disp["qty"].fillna(0).astype(int)
    daily_disp["red_count"] = daily_disp["red_count"].fillna(0).astype(int)
    daily_disp["yellow_count"] = daily_disp["yellow_count"].fillna(0).astype(int)
    daily_disp["green_count"] = daily_disp["green_count"].fillna(0).astype(int)

    # 切档/操作标记列
    daily_disp["mark"] = daily_disp.apply(
        lambda r: ("🔄 切档" if r.get("is_switch") else "") +
                  (" 🟢买" if r.get("action") == "BUY" else
                   " 🔴卖" if r.get("action") == "SELL" else ""),
        axis=1,
    )

    cols_order = ["date", "close", "red_count", "yellow_count", "green_count",
                  "verdict", "mark", "shares", "total_E", "vs_hold"]
    labels = ["日期", "收盘", "红", "黄", "绿", "Verdict", "事件",
              "持仓份额", "总资产", "vs持有"]
    disp_final = daily_disp[cols_order].copy()
    disp_final.columns = labels

    # 高亮切档/操作日
    def _row_style(row):
        mark = row["事件"]
        if "切档" in mark:
            return ["background-color: rgba(245,158,11,0.15)"] * len(row)
        if "买" in mark or "卖" in mark:
            return ["background-color: rgba(59,130,246,0.10)"] * len(row)
        return [""] * len(row)

    styled = disp_final.style.apply(_row_style, axis=1)
    st.dataframe(
        styled, use_container_width=True, hide_index=True,
        height=min(560, 38 + 35 * len(disp_final)),
    )

    # ─── 优化诊断 ───────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🔧 红绿灯策略优化诊断")
    st.caption("基于本次回测的统计与敏感度分析,自动给出 1-3 条优化建议。")

    try:
        diag = _diagnose_cached(
            db_mtime, str(start_d), str(end_d),
            float(init_total), float(init_gold),
            float(upper_m), float(lower_m),
            int(step_sh), int(confirm_d),
            etf_code=etf_code, price_table=price_table,
        )
    except Exception as e:
        st.warning(f"诊断失败:{type(e).__name__}: {e}")
        diag = None

    if diag is not None:
        # ─ a) 当前状态 ─
        cs = diag["current_status"]
        st.markdown(
            f"**当前 verdict** `{cs['current_verdict']}`  ·  "
            f"距上次切档 **{cs['days_since_switch']} 天**  "
            f"(上次切档 {cs['last_switch_date']})  ·  "
            f"缺口 {cs['gap']:+,.0f} 份"
        )

        # ─ b/c) 信号停留 + 极值错位 ─
        cL, cR = st.columns([1, 1])
        with cL:
            st.markdown("**📊 各档位停留天数**")
            vs = diag["verdict_stay"].copy()
            vs["pct"] = vs["pct"].round(1).astype(str) + "%"
            vs.columns = ["档位", "天数", "占比"]
            st.dataframe(
                vs, use_container_width=True, hide_index=True,
                height=min(220, 38 + 35 * len(vs)),
            )

        with cR:
            st.markdown("**🎯 区间极值错位检查**")
            em = diag["extreme_misalign"]
            high_warn = " ⚠️ 错位" if em["high_misaligned"] else " ✅"
            low_warn = " ⚠️ 错位" if em["low_misaligned"] else " ✅"
            st.markdown(
                f"- 最高价 **{em['high_price']:.3f}** ({em['high_date']}) "
                f"当日档位 `{em['high_verdict']}`{high_warn}\n"
                f"- 最低价 **{em['low_price']:.3f}** ({em['low_date']}) "
                f"当日档位 `{em['low_verdict']}`{low_warn}"
            )

        # ─ d) confirm_days 敏感度 ─
        st.markdown("**⚙️ confirm_days 参数敏感度**")
        cs_df = diag["confirm_sensitivity"].copy()
        cs_df["E_final"] = cs_df["E_final"].round(0).astype("Int64")
        cs_df["E_return_pct"] = cs_df["E_return_pct"].round(2).astype(str) + "%"
        cs_df["diff_vs_current"] = cs_df["diff_vs_current"].round(0).astype("Int64")
        cs_df.columns = ["确认天数", "终值", "收益%", "操作次数", "vs当前"]
        st.dataframe(cs_df, use_container_width=True, hide_index=True)

        # ─ e) 综合建议 ─
        st.markdown("**💡 优化建议**")
        for i, a in enumerate(diag["advice"], 1):
            st.markdown(f"{i}. {a}")

    # ─── 当前下一步建议 ───────────────────────────────────
    last_v = summary["end_verdict"]
    end_shares = summary["end_shares"]
    target_now = tm.get(last_v, tm["hold"])
    gap = target_now - end_shares
    last_price = summary["end_price"]

    if abs(gap) < 0.5:
        advice = "✅ **持有不动**(已到目标份额)"
        color = "#10b981"
    elif gap > 0:
        qty = min(step_sh, gap)
        advice = f"🟢 **下次评估日建议买入 {qty:,.0f} 份**(≈ {qty*last_price:,.0f} 元)"
        color = "#10b981"
    else:
        qty = min(step_sh, -gap)
        advice = f"🔴 **下次评估日建议卖出 {qty:,.0f} 份**(≈ {qty*last_price:,.0f} 元)"
        color = "#dc2626"

    st.markdown(
        f'<div style="padding:14px 18px;border-radius:8px;'
        f'border-left:4px solid {color};background:rgba(245,158,11,0.06);'
        f'margin-top:10px">'
        f'<div style="font-size:13px;color:#888">📌 当前持仓 & 下次建议</div>'
        f'<div style="font-size:15px;margin-top:6px">{advice}</div>'
        f'<div style="font-size:12px;color:#666;margin-top:4px">'
        f'当前份额 {end_shares:,.0f}  ·  当前现金 {summary["end_cash"]:,.0f}  ·  '
        f'红绿灯 <b>{last_v}</b> → 目标 {target_now:,} 份  ·  '
        f'缺口 {gap:+,.0f}'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ─── 策略说明 ─────────────────────────────────────────
    with st.expander("💡 策略逻辑", expanded=False):
        st.markdown(f"""
**对照组 A · 一直持有**
- 起点投入 {init_gold:,.0f} 元买入 ETF 后**永不交易**
- 终值 = 起始份额 × 终价 + 现金 {init_total - init_gold:,.0f}

**实验组 E · 红绿灯档位策略**
- 红绿灯 verdict → 目标份额倍数:
  - `add`(全绿) → 上限 = 基数 × {upper_m}
  - `pause`(3+ 红) → 下限 = 基数 × {lower_m}
- 每周一评估,新档位需稳定 **{confirm_d} 天**才执行
- 每次最多调整 **{step_sh:,} 份**(大跨档分多周走完)
- 现金部分 0% 收益(简化)

**关键洞察**
- 信号确认期能过滤 ~83% 的短期抖动 → 减少无效操作
- 牛市单边期:策略小幅跑赢持有(止盈+回补)
- 横盘 / 熊市:策略才能真正发挥避险价值(目前过去一年未出现)
""")


