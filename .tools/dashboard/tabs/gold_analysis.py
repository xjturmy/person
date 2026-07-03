"""D2 Phase 2.3 · 黄金分析法 Tab(对照 lynch / graham 模式,但**资产类**不针对单家公司)。

5 sub-tabs:
  ① 三大范式投票  → 5+5+5=15 信号矩阵 + 投票结果(Phase 2.4 引擎前用静态判定)
  ② 实际利率定价  → 双轴时序图 + 散点图 + 四象限决策
  ③ 周期定位      → 康波四阶段时间轴 + 历史萧条期黄金回报对照
  ④ 关键比率      → 金油 / 金银 / 实际利率 / SPDR 4 张时序 + 分位仪表盘
  ⑤ ETF 选择      → 4 只 ETF 对比 + 归一化叠加 + 推荐评分

设计原则:
- 顶部 banner 主色:黄金渐变(对照林奇绿 / 格雷厄姆蓝)
- 复用 gold_data.py 纯数据 + Phase 2.4 引擎接入位预留(`paradigm_engine.py` 待建)
- 与 lynch/graham 一致的 render 签名(忽略 selected/year/folder_to_ticker)

Author: Claude (D2 Phase 2.3, 2026-05-07)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
KNOWLEDGE_BASE = ROOT / "01_knowledge" / "03_投资策略与选股" / "12_黄金投资法"

if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from gold.data import (  # noqa: E402
    Snapshot, ParadigmVote,
    latest_snapshot, static_paradigm_vote, fill_dynamic_signals,
    load_indicator, load_ratios, load_percentiles,
    load_etf_master, load_etf_prices,
)

# Phase 2.4 yaml 投票引擎(可用时优先)
try:
    from gold.paradigm import vote as _engine_vote, ParadigmVoteV1  # noqa: E402
    _ENGINE_AVAILABLE = True
except Exception:
    _ENGINE_AVAILABLE = False

# v2.4 step-D · 短期过热引擎
try:
    from gold.overheat import (  # noqa: E402
        vote as _overheat_vote, trend_combo_advice as _overheat_advice,
        stock_etf_advice as _stock_etf_advice,
    )
    _OVERHEAT_AVAILABLE = True
except Exception:
    _OVERHEAT_AVAILABLE = False

# v2.6 主题 3 板块 G · 金股 ETF β 引擎
try:
    from gold.beta import compute_all as _stock_compute_all  # noqa: E402
    _STOCK_BETA_AVAILABLE = True
except Exception:
    _STOCK_BETA_AVAILABLE = False

# ⑧ 策略回溯引擎
try:
    from gold.backtest import (  # noqa: E402
        run as _backtest_run, GOLD_DB as _BACKTEST_DB, DEFAULT_MULT,
    )
    _BACKTEST_AVAILABLE = True
except Exception:
    _BACKTEST_AVAILABLE = False

# 黄金渐变 banner
BANNER_GRADIENT = "linear-gradient(90deg, #b45309 0%, #f59e0b 50%, #fbbf24 100%)"
# 短期过热 banner(冷调蓝紫,与黄金渐变形成对偶 — 长期 vs 短期)
OVERHEAT_GRADIENT_RED = "linear-gradient(90deg, #991b1b 0%, #dc2626 100%)"
OVERHEAT_GRADIENT_YELLOW = "linear-gradient(90deg, #b45309 0%, #f59e0b 100%)"
OVERHEAT_GRADIENT_GREEN = "linear-gradient(90deg, #065f46 0%, #10b981 100%)"


# ─── 缓存层(随 db_mtime 失效)──────────────────────────────────────────


@st.cache_data(ttl=600, show_spinner=False)
def _snapshot_cached(db_mtime: float) -> dict | None:
    """返回 dict 而非 dataclass(streamlit cache 不爱 dataclass)。"""
    try:
        return latest_snapshot().to_dict()
    except Exception as e:
        return {"_error": str(e)}


_VOTE_CACHE_VERSION = "v2.4_engine"  # 升版强制 cache 失效(每次切换 engine/static 行为时 +1)


@st.cache_data(ttl=600, show_spinner=False)
def _vote_cached(db_mtime: float, cache_version: str = _VOTE_CACHE_VERSION) -> dict:
    """yaml 引擎投票(verified=True);失败回落 static。

    cache_version 是显式 cache key 一部分 — 切换 engine/static 行为时改它,
    避免 streamlit 复用旧 dict(常被 ttl 复用)。
    """
    if _ENGINE_AVAILABLE:
        try:
            return _engine_vote().to_dict()
        except Exception as e:
            # 引擎失败 → 回落 static
            snap = latest_snapshot()
            d = static_paradigm_vote(snap).to_dict()
            d["_engine_error"] = str(e)
            return d
    snap = latest_snapshot()
    return static_paradigm_vote(snap).to_dict()


@st.cache_data(ttl=600, show_spinner=False)
def _ratios_cached(db_mtime: float, days: int | None = None) -> pd.DataFrame:
    return load_ratios(days=days)


@st.cache_data(ttl=600, show_spinner=False)
def _indicator_cached(indicator: str, db_mtime: float, days: int | None = None) -> pd.DataFrame:
    return load_indicator(indicator, days=days)


@st.cache_data(ttl=600, show_spinner=False)
def _percentiles_cached(db_mtime: float) -> pd.DataFrame:
    return load_percentiles()


@st.cache_data(ttl=600, show_spinner=False)
def _etf_master_cached(db_mtime: float) -> pd.DataFrame:
    return load_etf_master()


@st.cache_data(ttl=600, show_spinner=False)
def _etf_prices_cached(db_mtime: float, days: int = 1825) -> pd.DataFrame:
    return load_etf_prices(days=days)


@st.cache_data(ttl=600, show_spinner=False)
def _overheat_cached(db_mtime: float) -> dict | None:
    """v2.4 step-D · 短期过热投票(失败/未启用时返回 None)。"""
    if not _OVERHEAT_AVAILABLE:
        return None
    try:
        return _overheat_vote().to_dict()
    except Exception as e:
        return {"_error": str(e)}


@st.cache_data(ttl=600, show_spinner=False)
def _stock_etf_master_cached(db_mtime: float) -> pd.DataFrame:
    """v2.6 板块 F · 金股 ETF 静态信息(4 只)。"""
    from gold.data import GOLD_DB
    if not GOLD_DB.exists():
        return pd.DataFrame()
    import duckdb
    con = duckdb.connect(str(GOLD_DB), read_only=True)
    try:
        return con.execute(
            "SELECT etf_code, etf_name, exchange, manager, tracking_index, "
            "fee_rate, listing_date FROM gold_stock_etf_master "
            "ORDER BY etf_code"
        ).df()
    except Exception:
        return pd.DataFrame()
    finally:
        con.close()


@st.cache_data(ttl=600, show_spinner=False)
def _stock_etf_prices_cached(db_mtime: float, days: int = 365) -> pd.DataFrame:
    """v2.6 板块 F · 金股 ETF 日 K。"""
    from gold.data import GOLD_DB
    if not GOLD_DB.exists():
        return pd.DataFrame()
    import duckdb
    con = duckdb.connect(str(GOLD_DB), read_only=True)
    try:
        return con.execute(
            "SELECT etf_code, date, open, close, high, low, volume, "
            "turnover, pct_change "
            "FROM gold_stock_etf_prices "
            f"WHERE date >= CURRENT_DATE - INTERVAL '{days} days' "
            "ORDER BY etf_code, date"
        ).df()
    except Exception:
        return pd.DataFrame()
    finally:
        con.close()


@st.cache_data(ttl=600, show_spinner=False)
def _stock_betas_cached(db_mtime: float) -> list[dict]:
    """v2.6 板块 G · 4 只金股 ETF 相对 518880 的滚动 β。"""
    if not _STOCK_BETA_AVAILABLE:
        return []
    try:
        results = _stock_compute_all()
    except Exception:
        return []
    out = []
    for r in results:
        d = r.__dict__.copy()
        d["as_of"] = str(d["as_of"])
        out.append(d)
    return out


@st.cache_data(ttl=600, show_spinner=False)
def _overheat_history_cached(db_mtime: float, days: int = 365) -> pd.DataFrame:
    """读 gold_overheat_history(用于历史回看时序图)。"""
    from gold.data import GOLD_DB  # 局部导入避免循环
    if not GOLD_DB.exists():
        return pd.DataFrame()
    import duckdb
    con = duckdb.connect(str(GOLD_DB), read_only=True)
    try:
        df = con.execute(
            "SELECT date, red_count, yellow_count, green_count, "
            "verdict_id, verdict_label "
            "FROM gold_overheat_history "
            f"WHERE date >= CURRENT_DATE - INTERVAL '{days} days' "
            "ORDER BY date"
        ).df()
        return df
    finally:
        con.close()


# ─── 数据时效 + 一键拉新数据(v2.4 step-D 补强)─────────────────────────


@st.cache_data(ttl=60, show_spinner=False)
def _freshness_cached(db_mtime: float) -> dict:
    """读 gold.duckdb 文件 mtime + 关键表最新数据日期。ttl 60s 是为了刷新后能快速更新。"""
    from datetime import datetime
    from gold.data import GOLD_DB
    info = {"db_mtime": None, "etf_date": None, "metric_date": None,
            "overheat_date": None}
    if not GOLD_DB.exists():
        return info
    try:
        ts = GOLD_DB.stat().st_mtime
        info["db_mtime"] = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass
    try:
        import duckdb
        con = duckdb.connect(str(GOLD_DB), read_only=True)
        try:
            for col, table in (("etf_date", "gold_etf_prices"),
                               ("metric_date", "gold_metrics"),
                               ("overheat_date", "gold_overheat_history")):
                try:
                    row = con.execute(f"SELECT MAX(date) FROM {table}").fetchone()
                    if row and row[0]:
                        info[col] = str(row[0])[:10]
                except Exception:
                    pass
        finally:
            con.close()
    except Exception:
        pass
    return info


def _refresh_gold_data() -> tuple[bool, str]:
    """跑 fetch_gold_etf + fetch_gold_etf_share + fetch_gold_prices + overheat_engine --write。

    返回 (整体成功?, 摘要日志)。任一步失败不致命,继续后续步骤。
    """
    import subprocess
    import time

    py_exec = sys.executable
    steps = [
        ("ETF 价格 / 换手率", [py_exec, str(ROOT / ".tools/db/fetch_gold_etf.py")]),
        ("ETF 份额", [py_exec, str(ROOT / ".tools/db/fetch_gold_etf_share.py")]),
        ("金价时序(SGE/USD)", [py_exec, str(ROOT / ".tools/db/fetch_gold_prices.py")]),
        ("过热引擎重算 + 写库",
         [py_exec, str(ROOT / ".tools/dashboard/overheat_engine.py"), "--write"]),
    ]
    log_lines: list[str] = []
    t_total = time.time()
    n_ok = 0
    for name, cmd in steps:
        t0 = time.time()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=180, cwd=str(ROOT))
            elapsed = time.time() - t0
            if r.returncode == 0:
                log_lines.append(f"✅ {name} ({elapsed:.0f}s)")
                n_ok += 1
            else:
                tail = (r.stderr or r.stdout or "").strip().split("\n")[-1][:140]
                log_lines.append(f"⚠️ {name} 失败 ({elapsed:.0f}s): {tail}")
        except subprocess.TimeoutExpired:
            log_lines.append(f"⏱ {name} 超时(>180s)")
        except Exception as e:
            log_lines.append(f"💥 {name} 异常: {type(e).__name__}: {e}")
    total = time.time() - t_total
    log_lines.append(f"⏱ 总耗时:{total:.0f}s · {n_ok}/{len(steps)} 步成功")
    return n_ok == len(steps), "\n".join(log_lines)


# ─── Banner ─────────────────────────────────────────────────────────────


def _render_banner(snap: Snapshot, vote) -> None:
    """vote 可以是 ParadigmVote(static)/ ParadigmVoteV1(engine)/ SimpleNamespace(dict→ns)。"""
    rr_str = f"{snap.real_rate:+.2f}%" if snap.real_rate is not None else "—"
    rr_pct = f"{snap.real_rate_pct_10y * 100:.0f}% 分位(10y)" if snap.real_rate_pct_10y is not None else "分位 —"
    go_str = f"{snap.gold_oil:.1f}" if snap.gold_oil is not None else "—"
    gs_str = f"{snap.gold_silver:.1f}" if snap.gold_silver is not None else "—"
    pct_lo, pct_hi = vote.suggested_pct
    as_of_str = snap.as_of.strftime("%Y-%m-%d") if snap.as_of else "—"

    st.markdown(
        f'<div style="padding:14px 18px;border-radius:10px;'
        f'background:{BANNER_GRADIENT};color:white;margin:8px 0">'
        f'<span style="font-size:26px">🥇</span> '
        f'<span style="font-size:21px;font-weight:700;margin-left:8px">'
        f'当前主导身份:{vote.dominant_label}</span>'
        f'<span style="margin-left:14px;background:rgba(255,255,255,0.25);'
        f'padding:3px 10px;border-radius:10px;font-size:13px">'
        f'范式投票 {vote.p1_count}-{vote.p2_count}-{vote.p3_count} '
        f'({"3/3 全开" if (vote.p1_active and vote.p2_active and vote.p3_active) else f"{sum([vote.p1_active, vote.p2_active, vote.p3_active])}/3 激活"})</span>'
        f'<span style="margin-left:14px;background:rgba(255,255,255,0.18);'
        f'padding:3px 10px;border-radius:10px;font-size:13px">'
        f'⏱ {as_of_str}</span>'
        f'<div style="font-size:13px;opacity:0.92;margin-top:6px">'
        f'📍 实际利率 <b>{rr_str}</b> · {rr_pct}'
        f' &nbsp;&nbsp;|&nbsp;&nbsp; 金油比 <b>{go_str}</b>'
        f' &nbsp;&nbsp;|&nbsp;&nbsp; 金银比 <b>{gs_str}</b>(SGE 国内口径)</div>'
        f'<div style="font-size:14px;font-weight:600;margin-top:6px">'
        f'💡 配置建议:权益类组合中 黄金占 <b>{pct_lo:.0f}-{pct_hi:.0f}%</b>'
        f'(高风险偏好可至 38%)</div>'
        f'<div style="font-size:11px;opacity:0.7;margin-top:4px">'
        f'{"✅ 来源:yaml 投票引擎(verified=True)" if vote.verified else "⚠️ 来源:静态判定(Phase 2.4 引擎未启用)"}'
        f' · {getattr(vote, "source", "—")}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── 短期过热 banner(v2.4 step-D)─────────────────────────────────────


def _render_overheat_banner(overheat: dict | None, paradigm_actives: int) -> None:
    """挂在主 banner 下方的小卡。

    overheat = OverheatVote.to_dict() | {"_error": ...} | None
    paradigm_actives = 0-3,用于联动建议
    """
    if not overheat or overheat.get("_error"):
        # 引擎未启用 / 失败 → 退化提示
        msg = "未启用" if overheat is None else f"失败({overheat.get('_error')})"
        st.markdown(
            f'<div style="padding:8px 12px;border-radius:8px;'
            f'background:#f3f4f6;color:#666;margin:6px 0;font-size:12px">'
            f'⏱ <b>短期热度引擎</b>:{msg} '
            f'<span style="color:#999">(将提供"今天该不该追"建议)</span></div>',
            unsafe_allow_html=True,
        )
        return

    verdict_id = overheat.get("verdict_id", "add")
    if verdict_id in ("pause", "pause_partial"):
        bg = OVERHEAT_GRADIENT_RED
    elif verdict_id == "hold":
        bg = OVERHEAT_GRADIENT_YELLOW
    else:
        bg = OVERHEAT_GRADIENT_GREEN

    advice = ""
    try:
        if _OVERHEAT_AVAILABLE:
            advice = _overheat_advice(verdict_id, paradigm_actives)
    except Exception:
        pass

    red, yel, gre = (overheat.get("red_count", 0),
                     overheat.get("yellow_count", 0),
                     overheat.get("green_count", 0))

    st.markdown(
        f'<div style="padding:12px 16px;border-radius:10px;'
        f'background:{bg};color:white;margin:6px 0">'
        f'<span style="font-size:21px">⏱</span> '
        f'<span style="font-size:18px;font-weight:700;margin-left:6px">'
        f'短期热度:{overheat.get("verdict_label", "—")}</span>'
        f'<span style="margin-left:14px;background:rgba(255,255,255,0.25);'
        f'padding:3px 10px;border-radius:10px;font-size:13px">'
        f'🔴 {red} · 🟡 {yel} · 🟢 {gre}</span>'
        + (f'<div style="font-size:13px;margin-top:6px;font-weight:600">'
           f'💡 联动建议:{advice}</div>' if advice else '')
        + f'<div style="font-size:12px;opacity:0.9;margin-top:4px">'
          f'{overheat.get("verdict_action", "")}</div>'
        f'<div style="font-size:11px;opacity:0.7;margin-top:4px">'
        f'✅ 来源:overheat_engine_v1 · '
        f'阈值见 [.tools/rules/gold_overheat.yaml](#)</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── ① 三大范式投票 ─────────────────────────────────────────────────────


def _render_paradigm(snap: Snapshot, vote) -> None:
    st.markdown("### ① 三大范式投票(15 信号矩阵)")
    st.caption(
        "📚 方法论:[01_三大范式判定.md]"
        f"({KNOWLEDGE_BASE}/01_三大范式判定.md)"
        " · 鲁政委《保卫财富》框架"
        " · 📸 **快照型判定**:13/15 信号为人工季度复审值(康波/地缘/央行购金等),"
        "历史不可回看,本卡仅展示「当下」结果"
    )

    # 引擎可用 → 用引擎信号(dict 列表);否则回落 static
    engine_signals = getattr(vote, "signals", None)
    if engine_signals:
        # 引擎结果格式:list[dict] — 适配为 UI 期望格式
        # paradigm 字段(经济金融 / 技术革命 / 大国博弈)从 paradigm_label 提取
        p_map = {"economic_financial": "经济金融",
                 "tech_revolution": "技术革命",
                 "great_power_struggle": "大国博弈"}
        signals = []
        for sig in engine_signals:
            if isinstance(sig, dict):
                p_zh = p_map.get(sig.get("paradigm", ""), sig.get("paradigm", ""))
                signals.append({
                    "id": sig["signal_id"],
                    "p": p_zh,
                    "name": sig["name"],
                    "current": str(sig.get("current_value")) if sig.get("current_value") is not None else "—",
                    "threshold": sig.get("threshold_str", ""),
                    "active": bool(sig.get("active", False)),
                    "source": sig.get("source", "—"),
                })
    else:
        signals = fill_dynamic_signals(snap)
    by_paradigm = {"经济金融": [], "技术革命": [], "大国博弈": []}
    for sig in signals:
        by_paradigm.setdefault(sig.get("p", ""), []).append(sig)

    col_a, col_b, col_c = st.columns(3)
    paradigm_meta = [
        ("经济金融", "🟢 范式一", "短期(月-季)", vote.p1_count, vote.p1_active, col_a),
        ("技术革命", "🟡 范式二", "中期(年-十年)", vote.p2_count, vote.p2_active, col_b),
        ("大国博弈", "🔴 范式三", "长期(十年-世代)", vote.p3_count, vote.p3_active, col_c),
    ]

    for p_name, p_label, p_horizon, count, active, col in paradigm_meta:
        with col:
            badge = "✅ 激活" if active else "⚪ 钝化"
            color = "#10b981" if active else "#9ca3af"
            st.markdown(
                f'<div style="padding:10px 12px;border-radius:8px;'
                f'border-left:4px solid {color};background:rgba(0,0,0,0.04);margin-bottom:6px">'
                f'<div style="font-size:13px;color:#666">{p_label} · {p_horizon}</div>'
                f'<div style="font-size:18px;font-weight:700;margin-top:4px">{p_name}</div>'
                f'<div style="font-size:14px;margin-top:4px">{badge} · {count}/5 信号</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            for sig in by_paradigm[p_name]:
                emoji = "✅" if sig["active"] else "⚪"
                st.markdown(
                    f'<div style="padding:6px 8px;font-size:12px;line-height:1.5">'
                    f'{emoji} <b>{sig["name"]}</b><br/>'
                    f'<span style="color:#888">阈值:{sig["threshold"]}</span><br/>'
                    f'<span style="color:#444">当前:{sig["current"]}</span><br/>'
                    f'<span style="color:#aaa;font-size:11px">来源:{sig["source"]}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    st.divider()
    st.markdown("#### 投票判定 → 主导身份 → 配置区间")
    pct_lo, pct_hi = vote.suggested_pct
    actives = sum([vote.p1_active, vote.p2_active, vote.p3_active])
    st.markdown(f"""
- **范式一(经济金融)**:{vote.p1_count}/5 信号激活 → {"✅ 激活" if vote.p1_active else "⚪ 钝化"}
- **范式二(技术革命)**:{vote.p2_count}/5 信号激活 → {"✅ 激活" if vote.p2_active else "⚪ 钝化"}
- **范式三(大国博弈)**:{vote.p3_count}/5 信号激活 → {"✅ 激活" if vote.p3_active else "⚪ 钝化"}

**主导身份**:{vote.dominant_label}({actives}/3 范式激活)
**建议黄金占比**:{pct_lo:.0f}-{pct_hi:.0f}%(高风险偏好客户可至 38%,鲁政委震撼结论)
""")
    if vote.verified:
        st.success(
            f"✅ 当前判定来源:**yaml 投票引擎**(`{getattr(vote, 'source', '—')}`)"
            "。yaml 阈值见 [.tools/rules/gold_paradigm.yaml](#)。"
            " 数据真实接入度:实际利率 / SPDR(若手填)/ 康波 / 地缘 / 央行购金 / 美元储备 / 全部 yaml manual_const。"
        )
        if hasattr(vote, "note") and vote.note:
            st.caption(f"💡 {vote.note}")
    else:
        st.info(
            "⚠️ 当前判定来源:**静态判定**(yaml 引擎未启用,可能 yaml 路径错或 PyYAML 缺)。"
            " 待接入项:VIX 实时数据 / 美股科技-金价相关性 / 美国生产力 YoY。"
        )


# ─── ② 实际利率定价 ─────────────────────────────────────────────────────


def _render_real_rate(snap: Snapshot, db_mtime: float) -> None:
    st.markdown("### ② 实际利率定价模型")
    st.caption(
        "📚 方法论:[02_实际利率定价模型.md]"
        f"({KNOWLEDGE_BASE}/02_实际利率定价模型.md)"
        " · 实际利率 = 名义利率 - 通胀预期"
    )

    # 三件套 metric
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        rr = f"{snap.real_rate:+.2f}%" if snap.real_rate is not None else "—"
        st.metric("实际利率(US 10Y - CPI YoY)", rr,
                  help="< 0 利好黄金 · > 0 压制黄金(2022 后失效期需查范式二/三)")
    with col_b:
        n10y = f"{snap.nominal_10y:.2f}%" if snap.nominal_10y is not None else "—"
        st.metric("名义利率(US 10Y)", n10y)
    with col_c:
        cpi = f"{snap.cpi_yoy:.2f}%" if snap.cpi_yoy is not None else "—"
        st.metric("CPI YoY", cpi)
    with col_d:
        gusd = f"${snap.gold_usd:.0f}/oz" if snap.gold_usd is not None else "—"
        st.metric("USD 金价(派生)", gusd, help="沪金 × USDCNY × 31.1g/oz")

    # 双轴时序图
    st.markdown("#### 实际利率 vs USD 金价(20 年视角)")
    rates = _ratios_cached(db_mtime, days=365 * 20)
    gold_usd = _indicator_cached("GOLD_USD_DERIVED", db_mtime, days=365 * 20)

    if not rates.empty and not gold_usd.empty:
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            rates = rates.dropna(subset=["real_rate"])
            gold_usd = gold_usd.dropna()

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(
                go.Scatter(x=gold_usd["date"], y=gold_usd["value"],
                           name="USD 金价", line=dict(color="#fbbf24", width=2)),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(x=rates["date"], y=rates["real_rate"],
                           name="实际利率(右轴 反向)",
                           line=dict(color="#1e3a8a", width=2, dash="dot")),
                secondary_y=True,
            )
            fig.update_layout(
                hovermode="x unified", height=400,
                margin=dict(l=20, r=20, t=20, b=20),
                legend=dict(orientation="h", y=1.05),
            )
            fig.update_yaxes(title="USD/oz", secondary_y=False)
            fig.update_yaxes(title="实际利率 %", secondary_y=True, autorange="reversed")
            st.plotly_chart(fig, width="stretch")
        except Exception as e:
            st.warning(f"图表渲染失败:{e}")
    else:
        st.info("数据不足(实际利率或 USD 金价缺失)")

    # 四象限决策
    with st.expander("💡 四象限决策矩阵(实际利率 × 通胀)", expanded=False):
        st.markdown("""
| 象限 | 实际利率 | 通胀 | 黄金强度 | 配置 | 当前对照 |
|------|---------|------|---------|------|---------|
| I 通胀繁荣 | < 0 | 高 | ⭐⭐⭐⭐ | 15-20% | — |
| II 滞胀型 | < 0 | 高 | ⭐⭐⭐⭐⭐ | 20-25% | — |
| III 通缩衰退 | > 0 | 低 | ⭐⭐⭐ | 5-10% | — |
| **IV 通胀回落** | **> 0** | **正常** | **⭐⭐** | **0-5%(范式二/三激活时仍可持有)** | ✅ **当前位置** |

**当前(2026-05)**:实际利率 +1.63% / CPI YoY 2.73% → **象限 IV**
但范式二/三仍激活 → 黄金不应大幅减仓,维持战略配置
""")


# ─── ③ 周期定位(康波四阶段)──────────────────────────────────────────


def _render_cycle() -> None:
    st.markdown("### ③ 周期定位(康波四阶段)")
    st.caption(
        "📚 方法论:[03_配置比例量化.md]"
        f"({KNOWLEDGE_BASE}/03_配置比例量化.md)"
        " · 周金涛康波周期"
    )

    st.markdown("""
```text
┌─────────────────────────────────────────────────────────────────┐
│           康波四阶段:股票/商品/现金/黄金的轮动               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   回升期        繁荣期         衰退期         萧条期(当前)    │
│  2030/35-?    1991-2004    2004-2020       2020-2030/35        │
│      │            │              │              │              │
│      ▼            ▼              ▼              ▼              │
│   ┌──────┐    ┌──────┐      ┌──────┐      ┌──────────┐      │
│   │ 股票 │───►│ 商品 │─────►│ 现金 │─────►│   黄金   │      │
│   │ 优先 │    │ 优先 │      │ 优先 │      │   优先   │      │
│   └──────┘    └──────┘      └──────┘      └──────────┘      │
│      ✅           ❌            ⚠️            ⭐⭐⭐         │
│   黄金一般    黄金较差      黄金中性       黄金优异          │
│                                                                  │
│   配置:5-10%   0-5%          5-10%          15-25% ← 当前    │
│                                                                  │
│   【当前定位】第五次康波萧条期中后段(2020-2030/35)            │
└─────────────────────────────────────────────────────────────────┘
```
""")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("当前周期阶段", "第五次康波萧条期",
                  help="周金涛预测 2030-2035 切回升期")
    with col_b:
        st.metric("黄金战略权重", "15-25%",
                  help="萧条期对黄金最有利")
    with col_c:
        st.metric("预计切换时间", "2030-2035",
                  help="AI 商用化 + 新动能爆发 = 切换标志")

    st.markdown("#### 历史四次萧条期黄金回报对照")
    historical = pd.DataFrame({
        "康波": ["第一次", "第二次", "第三次", "第四次", "第五次(当前)"],
        "萧条期": ["1815-1849", "1873-1896", "1929-1949", "1973-1982", "2020-2030/35?"],
        "黄金表现": ["保值", "缓慢上行", "金本位崩溃后大涨", "+1300% (1971-1980)", "进行中"],
        "驱动因素": [
            "拿破仑战争结束 / 工业初期",
            "长萧条 / 银本位危机",
            "大萧条 / 二战 / 布雷顿森林",
            "石油危机 / 滞胀 / 美元脱金",
            "AI 革命 / 去美元化 / 地缘冲突",
        ],
    })
    st.dataframe(historical, width="stretch", hide_index=True)

    with st.expander("💡 配置比例公式(三层联动)", expanded=False):
        st.markdown("""
**第一步**:康波阶段 → 战略基础区间
- 萧条期 15-25% / 衰退期 5-10% / 回升期 5-10% / 繁荣期 0-5%

**第二步**:风险偏好乘数
- 低风险(股 < 10%):基础 × 0.1 → 黄金 1-2%
- 中风险(股 20-40%):基础 × 0.7 → 黄金 14-17%
- 高风险(股 ≥ 50%):基础 × 1.6 → 黄金 32-40% ⭐(鲁政委定律)

**第三步**:战术微调
- 三范式全开 + 实际利率 < -1%:+5%
- 钝化 + 实际利率 > +2%:-5%

**示例**(高风险偏好,2026-05):
- 战略基础 20%(萧条期中位)× 1.6 = 32% + 战术 +5% = **37%** ≈ 鲁政委 38% 上限
""")


# ─── ④ 关键比率(4 张时序 + 分位仪表盘)──────────────────────────────


def _render_ratios(snap: Snapshot, db_mtime: float) -> None:
    st.markdown("### ④ 关键比率与分位仪表盘")
    st.caption(
        "📚 方法论:[05_关键指标速查.md]"
        f"({KNOWLEDGE_BASE}/05_关键指标速查.md)"
    )

    # 顶部 4 列 metric
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        rr = f"{snap.real_rate:+.2f}%" if snap.real_rate is not None else "—"
        rrp = f"{snap.real_rate_pct_10y*100:.0f}% 分位" if snap.real_rate_pct_10y is not None else "—"
        st.metric("① 实际利率", rr, rrp)
    with col_b:
        go_v = f"{snap.gold_oil:.1f}" if snap.gold_oil is not None else "—"
        gop = f"{snap.gold_oil_pct_10y*100:.0f}% 分位" if snap.gold_oil_pct_10y is not None else "—"
        st.metric("② 金油比", go_v, gop)
    with col_c:
        gs_v = f"{snap.gold_silver:.1f}" if snap.gold_silver is not None else "—"
        gsp = f"{snap.gold_silver_pct_10y*100:.0f}% 分位" if snap.gold_silver_pct_10y is not None else "—"
        st.metric("③ 金银比(SGE)", gs_v, gsp,
                  help="SGE 国内口径,与 LBMA 国际(~88)不可直接对比")
    with col_d:
        spdr = f"{snap.spdr_holdings:.0f} 吨" if snap.spdr_holdings is not None else "未启用"
        st.metric("④ SPDR 持仓", spdr,
                  help="jin10.com 中国 IP 卡 → 走 .config/spdr_holdings_manual.csv 手填")

    # 4 张时序图
    st.markdown("#### 历史时序(10 年)")
    ratios = _ratios_cached(db_mtime, days=365 * 10)

    if not ratios.empty:
        try:
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            fig = make_subplots(rows=2, cols=2,
                                subplot_titles=("实际利率(%)", "金油比",
                                                "金银比(SGE)", "(SPDR 持仓 — 数据待接入)"))

            d = ratios["date"]
            for r, c, ycol, color in [
                (1, 1, "real_rate", "#1e3a8a"),
                (1, 2, "gold_oil",  "#b45309"),
                (2, 1, "gold_silver", "#dc2626"),
            ]:
                if ycol in ratios.columns:
                    yy = ratios[ycol]
                    fig.add_trace(
                        go.Scatter(x=d, y=yy, line=dict(color=color, width=2),
                                   showlegend=False),
                        row=r, col=c,
                    )

            # SPDR 占位(保留位置)
            spdr_df = _indicator_cached("SPDR_HOLDINGS", db_mtime, days=365 * 10)
            if not spdr_df.empty:
                fig.add_trace(
                    go.Scatter(x=spdr_df["date"], y=spdr_df["value"],
                               line=dict(color="#fbbf24", width=2), showlegend=False),
                    row=2, col=2,
                )
                fig.layout.annotations[3].text = "SPDR 持仓(吨)"

            fig.update_layout(height=520, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig, width="stretch")
        except Exception as e:
            st.warning(f"图表渲染失败:{e}")

    # 分位仪表盘
    st.markdown("#### 分位仪表盘(metric × window)")
    pct_df = _percentiles_cached(db_mtime)
    if not pct_df.empty:
        # pivot 成 metric × window
        pivot = pct_df.pivot_table(
            index="metric", columns="window_label",
            values="percentile", aggfunc="first",
        )

        def _pct_color(v):
            """0(绿)-50(黄)-100(红)线性渐变,纯 CSS 不依赖 matplotlib。"""
            if pd.isna(v):
                return ""
            v = max(0.0, min(1.0, float(v)))
            # RdYlGn_r:0=#1a9850(绿)/ 0.5=#ffffbf(黄)/ 1=#d73027(红)
            if v <= 0.5:
                # 绿 → 黄
                t = v * 2
                r = int(26 + (255 - 26) * t)
                g = int(152 + (255 - 152) * t)
                b = int(80 + (191 - 80) * t)
            else:
                # 黄 → 红
                t = (v - 0.5) * 2
                r = int(255 + (215 - 255) * t)
                g = int(255 + (48 - 255) * t)
                b = int(191 + (39 - 191) * t)
            return f"background-color: rgb({r},{g},{b}); color: #1a1a1a"

        st.dataframe(
            pivot.style.format("{:.1%}", na_rep="—").map(_pct_color),
            width="stretch",
        )
        st.caption("🟢 绿色 = 低分位(可能加仓机会)/ 🔴 红色 = 高分位(可能减仓信号)")
    else:
        st.info("分位数据未生成,先跑 `fetch_gold_ratios.py`")


# ─── ⑤ ETF 选择 ─────────────────────────────────────────────────────────


def _render_etf(db_mtime: float) -> None:
    st.markdown("### ⑤ 黄金 ETF 选择")
    st.caption(
        "📚 方法论:[04_黄金ETF选择.md]"
        f"({KNOWLEDGE_BASE}/04_黄金ETF选择.md)"
    )

    master = _etf_master_cached(db_mtime)
    if master.empty:
        st.warning("ETF master 未填,先跑 `fetch_gold_etf.py`")
        return

    # 4 列对比卡片
    cols = st.columns(len(master))
    for i, (_, etf) in enumerate(master.iterrows()):
        with cols[i]:
            highlight = "⭐ 推荐" if etf["etf_code"] == "518880" else ""
            st.markdown(
                f'<div style="padding:10px 12px;border-radius:8px;'
                f'border:1px solid #fbbf24;background:rgba(251,191,36,0.08);margin-bottom:6px">'
                f'<div style="font-size:11px;color:#888">{etf["exchange"]} · {etf["manager"]}</div>'
                f'<div style="font-size:16px;font-weight:700;margin-top:2px">{etf["etf_code"]}</div>'
                f'<div style="font-size:13px;margin-top:2px">{etf["etf_name"]}</div>'
                f'<div style="font-size:11px;color:#666;margin-top:6px">'
                f'费率 {etf["fee_rate"]:.2f}% / 跟踪 {etf["tracking"]}</div>'
                f'<div style="font-size:11px;color:#10b981;font-weight:600;margin-top:4px">{highlight}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # 归一化叠加图
    st.markdown("#### 归一化净值对比(3 年)")
    prices = _etf_prices_cached(db_mtime, days=365 * 3)
    if not prices.empty:
        try:
            import plotly.graph_objects as go

            fig = go.Figure()
            for code in master["etf_code"]:
                sub = prices[prices["etf_code"] == code].sort_values("date")
                if sub.empty:
                    continue
                base = sub["close"].iloc[0]
                fig.add_trace(go.Scatter(
                    x=sub["date"],
                    y=sub["close"] / base * 100,
                    mode="lines",
                    name=code,
                    line=dict(width=2),
                ))
            fig.update_layout(
                height=380, hovermode="x unified",
                margin=dict(l=20, r=20, t=20, b=20),
                yaxis_title="归一化净值(基期 = 100)",
                legend=dict(orientation="h", y=1.05),
            )
            st.plotly_chart(fig, width="stretch")
        except Exception as e:
            st.warning(f"图表渲染失败:{e}")
    else:
        st.info("ETF 价格数据未填,先跑 `fetch_gold_etf.py`")

    with st.expander("💡 ETF 选择原则", expanded=False):
        st.markdown("""
**首选标的**:**华安黄金 ETF(518880)**
- 规模最大(~430 亿)→ 流动性最好 → 跟踪误差最小
- 上交所挂牌 → 国内券商均可交易
- 4 只费率均为 0.6%,**不在费率上选,而在流动性**

**工具组合(推荐)**:
- 70-80% **黄金 ETF(518880)** — 主仓 / 流动性 / 战术调整
- 10-20% **银行积存金** — 自动定投 / 强制储蓄
- 5-10% **实物金条** — 极端避险 / 长期 / 心理锚

**避坑提醒**:
- ❌ 黄金股(GDX/紫金矿业)— 短期受**大盘指数 > 金价**影响
- ❌ 黄金期货 / 期权 — 普通投资者爆仓概率 > 80%
- ❌ 银行纸黄金 — 费率比 ETF 高 5-10 倍
""")


# ─── ⑥ 短期过热扫描(v2.4 step-D)──────────────────────────────────────


def _render_overheat(overheat: dict | None, paradigm_actives: int,
                     db_mtime: float) -> None:
    st.markdown("### ⑥ 短期过热扫描(防追高)")
    st.caption(
        "📚 用途:在三大范式「长期主导身份」之上,补一层周/日级"
        "「短期热度」,回答 *今天该不该追?是建仓窗口还是暂停?* · "
        "阈值见 [.tools/rules/gold_overheat.yaml](#)"
    )

    if not overheat or overheat.get("_error"):
        msg = "引擎未启用,请确认 PyYAML 已装,且 `.tools/rules/gold_overheat.yaml` 路径正确"
        if overheat and overheat.get("_error"):
            msg = f"引擎执行失败:{overheat['_error']}"
        st.warning(f"⚠️ {msg}")
        return

    # ── 综合判定卡 ──
    red, yel, gre = (overheat.get("red_count", 0),
                     overheat.get("yellow_count", 0),
                     overheat.get("green_count", 0))
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("🔴 红灯", red, help="过热警示信号数(0-6)")
    with col_b:
        st.metric("🟡 黄灯", yel, help="局部偏热信号数")
    with col_c:
        st.metric("🟢 绿灯", gre, help="健康信号数")
    with col_d:
        st.metric("综合判定", overheat.get("verdict_label", "—").split(" ")[-1],
                  help=overheat.get("verdict_action", ""))

    # 大趋势联动建议
    try:
        advice = (_overheat_advice(overheat["verdict_id"], paradigm_actives)
                  if _OVERHEAT_AVAILABLE else "")
    except Exception:
        advice = ""
    if advice:
        st.success(f"💡 **联动建议**(范式 {paradigm_actives}/3 激活 + "
                   f"短期 {overheat['verdict_label']}):{advice}")

    st.divider()

    # ── 6 信号矩阵 ──
    st.markdown("#### 6 信号矩阵 × 3 档红绿灯")
    signals = overheat.get("signals", [])
    if not signals:
        st.info("信号数据缺失")
        return

    rows = []
    for sig in signals:
        cv = sig.get("current_value")
        unit = sig.get("unit", "") or ""
        if cv is None:
            cur_str = "—"
        else:
            try:
                cur_str = f"{float(cv):.2f}{unit}"
            except (TypeError, ValueError):
                cur_str = str(cv)
        rows.append({
            "状态": sig.get("emoji", "⚪"),
            "信号": sig["name"],
            "当前值": cur_str,
            "阈值": sig.get("threshold_str", ""),
            "来源": sig.get("source", "—"),
            "说明": sig.get("note", ""),
        })
    df_sig = pd.DataFrame(rows)
    st.dataframe(df_sig, width="stretch", hide_index=True)

    # ── 历史回看时序图(可切换 1 年 / 5 年)──
    col_h1, col_h2 = st.columns([4, 1])
    with col_h2:
        period = st.radio(
            "周期",
            options=["近 1 年", "近 5 年"],
            index=0,
            key="overheat_history_period",
            horizontal=True,
            label_visibility="collapsed",
        )
    days_map = {"近 1 年": 365, "近 5 年": 365 * 5}
    hist_days = days_map[period]
    with col_h1:
        st.markdown(f"#### 历史回看({period})")
    hist = _overheat_history_cached(db_mtime, days=hist_days)
    if hist.empty:
        st.info("尚无过热历史快照 — 跑 `python3 .tools/dashboard/overheat_engine.py "
                "--backfill --years 5` 一次性回填,之后 update.py 每周累积一行")
    else:
        try:
            import plotly.graph_objects as go
            fig = go.Figure()
            fig.add_trace(go.Bar(x=hist["date"], y=hist["red_count"],
                                 name="🔴 红", marker_color="#dc2626"))
            fig.add_trace(go.Bar(x=hist["date"], y=hist["yellow_count"],
                                 name="🟡 黄", marker_color="#f59e0b"))
            fig.add_trace(go.Bar(x=hist["date"], y=hist["green_count"],
                                 name="🟢 绿", marker_color="#10b981"))
            fig.update_layout(
                barmode="stack", height=320,
                margin=dict(l=20, r=20, t=20, b=20),
                hovermode="x unified",
                yaxis_title="信号数(0-6)",
                legend=dict(orientation="h", y=1.05),
            )
            st.plotly_chart(fig, width="stretch")
            st.caption(f"📊 共 {len(hist)} 个采样点(每周 1 个)· 🔴 高位 = 历史过热警示 · "
                       "可对比 GOLD_USD_DERIVED 时序看是否对应回调")
        except Exception as e:
            st.warning(f"图表渲染失败:{e}")

    # ── 仓位走廊(短期热度 × 战略目标 × 当前持仓 → 建议)──
    with st.expander("📐 仓位走廊 · 短期热度 → 当前合理仓位", expanded=True):
        try:
            from valuation.corridor import compute_corridor, load_corridor_config
            cfg = load_corridor_config()
            default_x = float(cfg.get("default_strategic_pct", 20.0))
            default_pw = int(cfg.get("default_period_weeks", 26))

            col_x, col_y, col_n = st.columns(3)
            with col_x:
                strategic_pct = st.number_input(
                    "战略目标 X (%)", min_value=0.0, max_value=50.0,
                    value=float(st.session_state.get("gold_strategic_pct", default_x)),
                    step=0.5, key="gold_strategic_pct",
                    help="范式投票 + 康波决定的黄金目标占比上限。看好默认 20%,看空默认 5%。",
                )
            with col_y:
                current_pct = st.number_input(
                    "当前持仓 Y (%)", min_value=0.0, max_value=50.0,
                    value=float(st.session_state.get("gold_current_pct", 10.0)),
                    step=0.5, key="gold_current_pct",
                    help="你账户中黄金资产(实物 + ETF + 期货)占总资产的比例。",
                )
            with col_n:
                period_weeks = st.number_input(
                    "建仓/减仓周期(周)", min_value=4, max_value=104,
                    value=int(st.session_state.get("gold_period_weeks", default_pw)),
                    step=1, key="gold_period_weeks",
                    help="匀速建仓或减仓的总周数。默认 26(半年);减仓信号紧迫时可缩到 8。",
                )

            verdict_id = overheat.get("verdict_id", "add")
            corridor = compute_corridor(
                verdict_id, strategic_pct, current_pct,
                period_weeks=int(period_weeks),
            )

            # 走廊可视化:水平条
            tier_map = {
                "add": "🟢 add",
                "add_caution": "🟢 caution",
                "hold": "🟡 hold",
                "pause_partial": "🔴 partial",
                "pause": "🔴 pause",
            }
            decision_color = {"add": "#10b981", "hold": "#f59e0b", "reduce": "#dc2626"}
            color = decision_color.get(corridor.decision, "#64748b")

            col_l, col_r = st.columns([2, 1])
            with col_l:
                import plotly.graph_objects as go
                fig = go.Figure()
                # 走廊带(浅灰)
                fig.add_shape(type="rect",
                              x0=corridor.lower_pct, x1=corridor.upper_pct,
                              y0=0.3, y1=0.7,
                              fillcolor="rgba(148, 163, 184, 0.25)",
                              line=dict(width=0))
                # 走廊中线(目标)
                fig.add_vline(x=corridor.target_pct, line_dash="dash",
                              line_color="#475569",
                              annotation_text=f"目标 {corridor.target_pct:.1f}%",
                              annotation_position="top")
                # 战略上限 X
                fig.add_vline(x=corridor.strategic_pct, line_dash="dot",
                              line_color="#1e3a8a",
                              annotation_text=f"战略 X={corridor.strategic_pct:.0f}%",
                              annotation_position="bottom")
                # 当前持仓点
                fig.add_trace(go.Scatter(
                    x=[corridor.current_pct], y=[0.5],
                    mode="markers+text",
                    marker=dict(size=20, color=color, line=dict(color="white", width=2)),
                    text=[f"Y={corridor.current_pct:.1f}%"],
                    textposition="bottom center",
                    showlegend=False,
                ))
                fig.update_layout(
                    height=180,
                    margin=dict(l=20, r=20, t=30, b=30),
                    xaxis=dict(range=[0, max(corridor.strategic_pct + 5, corridor.current_pct + 3)],
                               title="占总资产比例 %"),
                    yaxis=dict(visible=False, range=[0, 1]),
                    plot_bgcolor="white",
                )
                st.plotly_chart(fig, width="stretch")

            with col_r:
                arrow = "▲" if corridor.decision == "add" else (
                    "▼" if corridor.decision == "reduce" else "→")
                st.markdown(
                    f"### {arrow} {corridor.decision_label}\n\n"
                    f"**当前档**:{tier_map.get(verdict_id, verdict_id)}({corridor.discount:.0%} × X)\n\n"
                    f"**走廊**:{corridor.lower_pct:.1f}% ~ {corridor.upper_pct:.1f}%\n\n"
                    f"**本周建议**:{corridor.weekly_step_pct:+.2f}% / 周\n\n"
                    f"_({corridor.tier_label})_"
                )

            # 决策细节
            if corridor.decision == "add":
                gap = corridor.upper_pct - corridor.current_pct
                weeks = max(1, int(round(gap / max(corridor.weekly_step_pct, 1e-6))))
                st.success(
                    f"✅ 当前 Y={corridor.current_pct:.1f}% 低于走廊下界 {corridor.lower_pct:.1f}% — "
                    f"按每周 {corridor.weekly_step_pct:+.2f}% 加仓,约 {weeks} 周达上界 {corridor.upper_pct:.1f}%。"
                )
            elif corridor.decision == "reduce":
                gap = corridor.current_pct - corridor.lower_pct
                weeks = max(1, int(round(gap / max(abs(corridor.weekly_step_pct), 1e-6))))
                st.error(
                    f"⚠️ 当前 Y={corridor.current_pct:.1f}% 高于走廊上界 {corridor.upper_pct:.1f}% — "
                    f"按每周 {corridor.weekly_step_pct:+.2f}% 减仓,约 {weeks} 周降到下界 {corridor.lower_pct:.1f}%。"
                )
            else:
                st.info(
                    f"⏸ 当前 Y={corridor.current_pct:.1f}% 在走廊 "
                    f"{corridor.lower_pct:.1f}% ~ {corridor.upper_pct:.1f}% 内 — 持有不动。"
                )

            st.caption(
                "💡 短期热度档位变了 → 走廊重画 → 重新比较 Y 与新走廊 → 决定本周是加 / 持 / 减。"
                "仓位倾向不是单次步长,而是阶梯式上限折扣。"
            )
        except Exception as e:
            st.warning(f"仓位走廊渲染失败:{e}")

    # ── 大趋势 × 短期联动矩阵 ──
    with st.expander("💡 大趋势 × 短期 8 种联动操作建议", expanded=False):
        st.markdown("""
| 大趋势(范式投票)| 短期判定 | 操作建议 |
|---|---|---|
| 看好(≥2/3) | 🟢 加仓窗口 | ✅ **加仓**(双绿,大胆建仓) |
| 看好         | 🟢 可小幅加仓 | ✅ **小幅加仓**(温和买入) |
| 看好         | 🟡 持有观望 | 🟡 **持有不动**(等过热释放再加) |
| 看好         | 🔴 局部过热 | ⚠️ **暂停建仓**(局部冷却) |
| 看好         | 🔴 暂停建仓 | ⚠️ **暂停建仓**(过热警示,大趋势好也不追高)|
| 看空(≤1/3) | 🟢 加仓窗口 | 🟢 **反弹机会**(高风险,大趋势空但已超卖)|
| 看空         | 🔴 暂停建仓 | 🔻 **减仓信号**(双红,高位风险) |

**核心原则**:大趋势看好 ≠ 任何时点都能进。**追高被套**是黄金投资最常见损失模式。
""")


# ─── ⑦ 金股 ETF 杠杆视图(v2.6 主题 3 板块 I)──────────────────────────


def _format_beta(b: float | None, decimals: int = 2) -> str:
    return f"{b:.{decimals}f}" if isinstance(b, (int, float)) else "—"


def _render_stock_etf_leverage(overheat: dict | None, db_mtime: float) -> None:
    st.markdown("### ⑦ 金股 ETF 杠杆视图(放大版黄金 ETF)")
    st.caption(
        "📈 **核心洞察**:金股 ETF(金矿股票挂钩)是黄金 ETF 的放大工具,"
        "β 通常 1.5-2.5 倍。⚠️ **双向性**:β 放大上涨,也放大下跌 — "
        "金价红灯时高 β 应优先减。"
    )

    master = _stock_etf_master_cached(db_mtime)
    if master.empty:
        st.warning("⚠️ 金股 ETF 数据未就绪 — 跑 `.tools/db/fetch_gold_stock_etf.py` 后刷新。")
        return

    # 1. β 计算
    betas = _stock_betas_cached(db_mtime)
    beta_map = {b["etf_code"]: b for b in betas}

    # 2. 顶部 banner — 金价 verdict + 杠杆总建议
    verdict_id = (overheat or {}).get("verdict_id", "hold")
    verdict_label = (overheat or {}).get("verdict_label", "🟡 数据未就绪")
    # 取 4 只 β_60d 中位数作"代表 β"给 banner advice;
    # 同一只 ETF 的 R² 一并取出,避免低 R² 的极端 β 污染 banner
    valid_pairs = [
        (b.get("beta_60d"), b.get("r_squared_60d"))
        for b in betas
        if b.get("beta_60d") is not None
    ]
    if valid_pairs:
        valid_pairs_sorted = sorted(valid_pairs, key=lambda p: p[0])
        rep_beta, rep_r2 = valid_pairs_sorted[len(valid_pairs_sorted) // 2]
    else:
        rep_beta, rep_r2 = None, None

    banner_advice = None
    if _OVERHEAT_AVAILABLE:
        try:
            banner_advice = _stock_etf_advice(verdict_id, rep_beta, r_squared=rep_r2)
        except Exception as e:
            st.warning(f"杠杆建议引擎失败:{e}")

    if banner_advice:
        rep_b_str = _format_beta(rep_beta)
        bg = (OVERHEAT_GRADIENT_RED if "🔴" in banner_advice.advice
              else OVERHEAT_GRADIENT_YELLOW if "🟡" in banner_advice.advice
              else OVERHEAT_GRADIENT_GREEN if "🟢" in banner_advice.advice
              else "linear-gradient(90deg, #475569 0%, #64748b 100%)")
        st.markdown(
            f'<div style="background:{bg};padding:14px 20px;border-radius:10px;'
            f'color:#fff;margin-bottom:10px">'
            f'<div style="font-size:13px;opacity:0.85">金价红绿灯:{verdict_label}'
            f' · 代表 β(中位 60d):{rep_b_str}</div>'
            f'<div style="font-size:18px;font-weight:700;margin-top:4px">{banner_advice.advice}</div>'
            f'<div style="font-size:12px;opacity:0.9;margin-top:4px">'
            f'📐 仓位倍数:×{banner_advice.position_multiplier:.2f}  ·  '
            f'{banner_advice.rationale}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # 3. 主图 — 金股 ETF vs 黄金 ETF 归一化叠加(180d)
    st.markdown("#### 归一化净值对比 · 金股 ETF vs 黄金 ETF(180 天)")
    prices = _stock_etf_prices_cached(db_mtime, days=180)
    gold_prices = _etf_prices_cached(db_mtime, days=180)
    if not prices.empty and not gold_prices.empty:
        try:
            import plotly.graph_objects as go
            fig = go.Figure()
            # 黄金 ETF 518880(基准,粗灰线)
            g518 = gold_prices[gold_prices["etf_code"] == "518880"].sort_values("date")
            if not g518.empty:
                base = g518["close"].iloc[0]
                fig.add_trace(go.Scatter(
                    x=g518["date"], y=g518["close"] / base * 100,
                    mode="lines", name="518880 黄金 ETF(基准)",
                    line=dict(color="#fbbf24", width=3, dash="dot"),
                ))
            # 4 只金股 ETF(细线)
            colors = ["#dc2626", "#7c3aed", "#0ea5e9", "#10b981"]
            for i, code in enumerate(master["etf_code"]):
                sub = prices[prices["etf_code"] == code].sort_values("date")
                if sub.empty:
                    continue
                base = sub["close"].iloc[0]
                name = master.loc[master["etf_code"] == code, "etf_name"].iloc[0]
                fig.add_trace(go.Scatter(
                    x=sub["date"], y=sub["close"] / base * 100,
                    mode="lines", name=f"{code} {name}",
                    line=dict(color=colors[i % len(colors)], width=1.8),
                ))
            fig.update_layout(
                height=360, hovermode="x unified",
                margin=dict(l=20, r=20, t=20, b=20),
                yaxis_title="归一化净值(基期 = 100)",
                legend=dict(orientation="h", y=1.08, font=dict(size=10)),
            )
            st.plotly_chart(fig, width="stretch")
        except Exception as e:
            st.warning(f"主图渲染失败:{e}")
    else:
        st.info("价格数据不足,跑 `fetch_gold_stock_etf.py --years 1` 补数据。")

    # 4. 横评表格 + 个性化决策卡
    st.markdown("#### 4 只金股 ETF 横评 + 个性化决策")

    rows = []
    for _, etf in master.iterrows():
        code = etf["etf_code"]
        b = beta_map.get(code, {})
        sub = prices[prices["etf_code"] == code].sort_values("date") if not prices.empty else pd.DataFrame()
        # 1y 涨跌 = 期末/期初 - 1(本视图只有 180d,故展示 180d 涨跌)
        chg_pct = None
        if len(sub) >= 2:
            chg_pct = (sub["close"].iloc[-1] / sub["close"].iloc[0] - 1) * 100

        beta_60d = b.get("beta_60d")
        r2_60d = b.get("r_squared_60d")
        advice = None
        if _OVERHEAT_AVAILABLE:
            try:
                advice = _stock_etf_advice(verdict_id, beta_60d, r_squared=r2_60d)
            except Exception:
                advice = None

        rows.append({
            "代码": code,
            "名称": etf["etf_name"],
            "交易所": etf["exchange"],
            "费率(%)": etf["fee_rate"],
            "180d 涨跌(%)": chg_pct,
            "β_30d": b.get("beta_30d"),
            "β_60d": beta_60d,
            "β_180d": b.get("beta_180d"),
            "R²_60d": b.get("r_squared_60d"),
            "建议": advice.advice if advice else "—",
            "仓位 ×": advice.position_multiplier if advice else None,
        })

    df_view = pd.DataFrame(rows)
    st.dataframe(
        df_view,
        width="stretch", hide_index=True,
        column_config={
            "费率(%)": st.column_config.NumberColumn(format="%.2f"),
            "180d 涨跌(%)": st.column_config.NumberColumn(format="%+.2f"),
            "β_30d": st.column_config.NumberColumn(format="%.2f"),
            "β_60d": st.column_config.NumberColumn(format="%.2f"),
            "β_180d": st.column_config.NumberColumn(format="%.2f"),
            "R²_60d": st.column_config.NumberColumn(format="%.3f",
                help="60d 回归拟合优度;>0.7 = β 可信"),
            "仓位 ×": st.column_config.NumberColumn(format="×%.2f"),
        },
    )

    # 4 张决策卡(每只一张)
    cols = st.columns(len(master))
    for i, row in enumerate(rows):
        with cols[i]:
            mult = row["仓位 ×"]
            mult_str = f"×{mult:.2f}" if isinstance(mult, (int, float)) else "—"
            border_color = ("#dc2626" if "🔴" in (row["建议"] or "")
                            else "#fbbf24" if "🟡" in (row["建议"] or "")
                            else "#10b981" if "🟢" in (row["建议"] or "")
                            else "#64748b")
            st.markdown(
                f'<div style="padding:10px 12px;border-radius:8px;'
                f'border:1px solid {border_color};background:rgba(100,116,139,0.05);'
                f'margin-bottom:6px;height:140px">'
                f'<div style="font-size:11px;color:#888">{row["交易所"]} · '
                f'β_60d {_format_beta(row["β_60d"])}</div>'
                f'<div style="font-size:15px;font-weight:700;margin-top:2px">{row["代码"]}</div>'
                f'<div style="font-size:12px;color:#555;margin-top:2px">{row["名称"]}</div>'
                f'<div style="font-size:11px;color:#444;margin-top:6px">{row["建议"]}</div>'
                f'<div style="font-size:11px;color:#666;margin-top:4px">仓位倍数:{mult_str}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # 5. β 滚动副图(可选展开)
    with st.expander("📊 β 滚动窗口对照(30 / 60 / 180 天)", expanded=False):
        if betas:
            beta_df = pd.DataFrame([{
                "代码": b["etf_code"], "β_30d": b.get("beta_30d"),
                "β_60d": b.get("beta_60d"), "β_180d": b.get("beta_180d"),
                "R²_60d": b.get("r_squared_60d"), "样本量": b.get("n_obs_max"),
                "as_of": b.get("as_of"),
            } for b in betas])
            st.dataframe(beta_df, width="stretch", hide_index=True,
                column_config={
                    "β_30d": st.column_config.NumberColumn(format="%.3f"),
                    "β_60d": st.column_config.NumberColumn(format="%.3f"),
                    "β_180d": st.column_config.NumberColumn(format="%.3f"),
                    "R²_60d": st.column_config.NumberColumn(format="%.3f"),
                })
            st.caption(
                "📌 **β 窗口选择**:30d 灵敏但噪声大,180d 稳健但慢;"
                "**默认看 60d**(平衡)。R² < 0.5 时 β 不稳定,建议持有观望。"
            )
        else:
            st.info("β 数据未生成(金股 ETF 数据不足或表未建)。")

    # 6. 教育卡(双向性提醒)
    with st.expander("💡 金股 ETF vs 黄金 ETF · 怎么用", expanded=False):
        st.markdown("""
**为什么金股 ETF 是「放大版黄金 ETF」**

金股 ETF 跟踪的是金矿/有色金属股票指数,而非实物黄金:
- 矿企经营杠杆(固定成本不变,金价涨 → 利润放大)
- 市场情绪杠杆(金价涨 → 资金涌入金股板块)

**β = 1.5 意味着什么?**
- 金价涨 10% → 金股 ETF 涨 ~15%
- 金价**跌** 10% → 金股 ETF **跌** ~15% ⚠️
- **β 不是单向利好**,放大上涨也放大下跌

**操作矩阵(已自动应用于上方决策卡)**

| 金价 verdict | β < 2.0 | β ≥ 2.0 |
|---|---|---|
| 🟢 加仓 / 小幅加仓 | 🟢 加金股放大 ×1.2 | 🟡 谨慎加金股 ×1.0 |
| 🟡 持有观望 | 🟡 持金股观望 ×1.0 | 🟡 持金股观望 ×1.0 |
| 🔴 暂停 / 局部过热 | 🔴 减金股(同步)×0.8 | 🔴 优先减金股 ×0.6 |

**仓位倍数怎么用**

黄金大类目标 X%(由范式投票决定,看好默认 20%)。金股建议仓位 =
**X × default_stock_share × multiplier**(yaml: `default_stock_share_in_gold = 0.30`)。

举例:战略目标 20%,multiplier=1.2 → 金股建议 20% × 30% × 1.2 = **7.2%** 黄金大类;
其中 12.8% 走实物 ETF(518880 等),7.2% 走金股 ETF。

**金股 ETF 的特性局限**

- **R² 不稳**:本视图 4 只 ETF R² 在 0.26 - 0.997 不等 — 因为部分 ETF 跟踪的是
  "沪深港金属矿业"而非纯金股,与黄金的相关性会偏离
- **样本短**:多数金股 ETF 2024 后上市,长窗口 β(180d)样本可能 < 180
- **不要做主动选股**:本视图聚焦 ETF 层;紫金/山东黄金等单股是公司分析 Tab 的事
""")


# ─── 主入口 ─────────────────────────────────────────────────────────────


def render(companies: list[str] | None = None,
           selected: str | None = None,
           db_mtime: float = 0.0,
           decisions_db=None,
           folder_to_ticker_fn=None) -> None:
    """黄金分析法 Tab 入口。signature 与 lynch/graham 对齐,但黄金是资产类不针对单家公司。"""
    st.subheader("🥇 黄金分析法 · 三身份决策框架")

    # 上一次刷新日志(session_state 跨 rerun 残留 → 渲染后清空)
    if st.session_state.get("gold_refresh_log"):
        log = st.session_state.pop("gold_refresh_log")
        ok = st.session_state.pop("gold_refresh_ok", False)
        if ok:
            st.success("✅ 行情已刷新,数据已重算")
        else:
            st.warning("⚠️ 刷新部分失败 — 详见日志")
        with st.expander("📋 刷新日志(自动隐藏)", expanded=not ok):
            st.code(log, language="text")

    # 顶部:数据来源 / 时效 / 刷新按钮
    fresh = _freshness_cached(db_mtime)
    col_left, col_ts, col_refresh = st.columns([3, 2, 1])
    with col_left:
        st.caption(
            "📊 数据来源:沪金 SGE / 美国 10Y / CPI / WTI 油 / 4 只 ETF · "
            "理论:鲁政委《保卫财富》三大范式 + 周金涛康波"
        )
    with col_ts:
        db_ts = fresh.get("db_mtime") or "—"
        etf_d = fresh.get("etf_date") or "—"
        oh_d = fresh.get("overheat_date") or "—"
        st.caption(
            f"💾 库更新:**{db_ts}**  ·  📈 ETF 最新:**{etf_d}**  ·  "
            f"⏱ 过热快照:**{oh_d}**"
        )
    with col_refresh:
        if st.button("🔄 拉新数据", key="gold_refresh",
                     width="stretch",
                     help="跑 fetch_gold_etf + fetch_gold_etf_share + "
                          "fetch_gold_prices + overheat_engine --write"
                          "(预计 30-90s)"):
            with st.spinner("正在拉取最新行情(预计 30-90s,请勿关闭)..."):
                ok, log = _refresh_gold_data()
            st.session_state["gold_refresh_log"] = log
            st.session_state["gold_refresh_ok"] = ok
            for cache_fn in (_snapshot_cached, _ratios_cached, _indicator_cached,
                             _percentiles_cached, _etf_master_cached, _etf_prices_cached,
                             _overheat_cached, _overheat_history_cached,
                             _freshness_cached,
                             _stock_etf_master_cached, _stock_etf_prices_cached,
                             _stock_betas_cached):
                cache_fn.clear()
            st.rerun()

    # 加载 snapshot + 投票
    snap_dict = _snapshot_cached(db_mtime)
    if snap_dict is None or "_error" in (snap_dict or {}):
        err = snap_dict.get("_error") if snap_dict else "数据加载失败"
        st.error(f"⚠️ gold.duckdb 未就绪:{err}")
        st.info("请先跑 4 个 fetch 脚本:`fetch_gold_prices` / `fetch_real_rate` / `fetch_gold_etf` / `fetch_gold_ratios`")
        return

    snap = Snapshot(**snap_dict)

    # 投票:引擎优先,失败回落 static
    vote_dict = _vote_cached(db_mtime)
    # SimpleNamespace 适配:UI 用属性访问(.dominant_label / .suggested_pct 等)
    from types import SimpleNamespace
    # tuple 化 suggested_pct(yaml 出 list)
    if isinstance(vote_dict.get("suggested_pct"), list):
        vote_dict["suggested_pct"] = tuple(vote_dict["suggested_pct"])
    vote = SimpleNamespace(**vote_dict)

    # Banner(主)
    _render_banner(snap, vote)

    # v2.4 step-D · 短期过热 banner(挂主 banner 下方)
    overheat = _overheat_cached(db_mtime)
    paradigm_actives = sum([vote.p1_active, vote.p2_active, vote.p3_active])
    _render_overheat_banner(overheat, paradigm_actives)

    # 9 sub-tabs(v2.7 加第 ⑨ 持仓建议)
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
        "① 三大范式投票",
        "② 实际利率定价",
        "③ 周期定位",
        "④ 关键比率",
        "⑤ ETF 选择",
        "⑥ 短期过热扫描",
        "⑦ 金股 ETF 杠杆视图",
        "⑧ 策略回溯",
        "⑨ 持仓建议",
    ])
    with tab1:
        _render_paradigm(snap, vote)
    with tab2:
        _render_real_rate(snap, db_mtime)
    with tab3:
        _render_cycle()
    with tab4:
        _render_ratios(snap, db_mtime)
    with tab5:
        _render_etf(db_mtime)
    with tab6:
        _render_overheat(overheat, paradigm_actives, db_mtime)
    with tab7:
        _render_stock_etf_leverage(overheat, db_mtime)
    with tab8:
        _render_backtest(db_mtime)
    with tab9:
        _render_position_advisor(overheat, db_mtime)


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

    # ─── 主图:价格 + 买卖点 + 信号背景 ───────────────────
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.08,
        subplot_titles=("ETF 价格 + 买卖点 + 信号区段", "总资产对比"),
    )

    # 1) 信号背景着色(分段填充)
    verdict_colors = {
        "add":           "rgba(16, 185, 129, 0.22)",   # 浅绿
        "add_caution":   "rgba(251, 191, 36, 0.22)",   # 浅黄
        "hold":          "rgba(245, 158, 11, 0.22)",   # 橙黄
        "pause_partial": "rgba(220, 38, 38, 0.22)",    # 浅红
        "pause":         "rgba(153, 27, 27, 0.30)",    # 深红
    }
    # 找连续 verdict 区段(把 x1 推到下个区段起点,避免单日区段零宽不可见)
    daily_r = daily.reset_index()
    daily_r["block"] = (daily_r["verdict"] != daily_r["verdict"].shift()).cumsum()
    _blocks = list(daily_r.groupby("block"))
    for _i, (_, blk) in enumerate(_blocks):
        v = blk.iloc[0]["verdict"]
        x0 = blk["date"].iloc[0]
        if _i + 1 < len(_blocks):
            x1 = _blocks[_i + 1][1]["date"].iloc[0]
        else:
            x1 = blk["date"].iloc[-1] + pd.Timedelta(days=1)
        fig.add_vrect(
            x0=x0, x1=x1,
            fillcolor=verdict_colors.get(v, "rgba(128,128,128,0.05)"),
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
    st.plotly_chart(fig, width="stretch")

    # ─── 信号图例 ─────────────────────────────────────────
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
            st.dataframe(disp, width="stretch", hide_index=True)
        else:
            st.info("回测区间内没有产生操作(信号始终在档位内 / 现金不足 / 确认期过滤)")

    with cB:
        st.markdown(f"#### 🚦 信号切换记录({len(switches)} 次)")
        if len(switches) > 0:
            sd = switches.copy()
            sd["date"] = pd.to_datetime(sd["date"]).dt.strftime("%Y-%m-%d")
            sd.columns = ["日期", "前档", "新档", "红", "黄", "绿"]
            st.dataframe(sd, width="stretch", hide_index=True,
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
        styled, width="stretch", hide_index=True,
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
                vs, width="stretch", hide_index=True,
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
        st.dataframe(cs_df, width="stretch", hide_index=True)

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
    """β 矩阵命中(同 gold_overheat.yaml stock_etf_position.matrix)。

    返回 (multiplier, rule_id)。
    """
    if verdict_id in ("add", "add_caution"):
        return (1.2, "add_low_beta") if beta < 2.0 else (1.0, "add_high_beta")
    if verdict_id == "hold":
        return (1.0, "hold_any")
    if verdict_id in ("pause", "pause_partial"):
        return (0.6, "reduce_high_beta") if beta >= 1.5 else (0.8, "reduce_low_beta")
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
