"""黄金分析 Tab 共享 helpers:imports / 缓存层 / 数据时效 / 拉新 / banner。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[4]
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
    _engine_vote = None
    ParadigmVoteV1 = None

# v2.4 step-D · 短期过热引擎
try:
    from gold.overheat import (  # noqa: E402
        vote as _overheat_vote, trend_combo_advice as _overheat_advice,
        stock_etf_advice as _stock_etf_advice,
    )
    _OVERHEAT_AVAILABLE = True
except Exception:
    _OVERHEAT_AVAILABLE = False
    _overheat_vote = None
    _overheat_advice = None
    _stock_etf_advice = None

# v2.6 主题 3 板块 G · 金股 ETF β 引擎
try:
    from gold.beta import compute_all as _stock_compute_all  # noqa: E402
    _STOCK_BETA_AVAILABLE = True
except Exception:
    _STOCK_BETA_AVAILABLE = False
    _stock_compute_all = None

# ⑧ 策略回溯引擎
try:
    from gold.backtest import (  # noqa: E402
        run as _backtest_run, GOLD_DB as _BACKTEST_DB, DEFAULT_MULT,
    )
    _BACKTEST_AVAILABLE = True
except Exception:
    _BACKTEST_AVAILABLE = False
    _backtest_run = None
    _BACKTEST_DB = None
    DEFAULT_MULT = None

# 供 sub-tab `from ._helpers import *` 使用 —
# 集中导出,避免 9 份 25 行重复 import。
# 缓存约定:所有 `_*_cached` 函数首参为 db_mtime(`gold.duckdb` 的 mtime),
# 文件 touch / 刷新数据后自动失效;不需要手动 bump 版本号。
# 仅导出 sub-tab body 真实使用的符号 — __init__.py 用显式 from 导入不受影响。
__all__ = [
    # 路径常量
    "ROOT", "DASHBOARD_DIR", "KNOWLEDGE_BASE",
    # data 层(sub-tab 直接调用)
    "Snapshot",
    "latest_snapshot", "static_paradigm_vote", "fill_dynamic_signals",
    "load_indicator", "load_ratios", "load_percentiles",
    # 引擎可用性(布尔 + 句柄)
    "_ENGINE_AVAILABLE",
    "_OVERHEAT_AVAILABLE", "_overheat_advice", "_stock_etf_advice",
    "_STOCK_BETA_AVAILABLE",
    "_BACKTEST_AVAILABLE", "_backtest_run", "_BACKTEST_DB",
    # banner 渐变
    "BANNER_GRADIENT",
    "OVERHEAT_GRADIENT_RED", "OVERHEAT_GRADIENT_YELLOW", "OVERHEAT_GRADIENT_GREEN",
    # 缓存层
    "_snapshot_cached", "_vote_cached",
    "_ratios_cached", "_indicator_cached", "_percentiles_cached",
    "_etf_master_cached", "_etf_prices_cached",
    "_overheat_cached", "_stock_etf_master_cached", "_stock_etf_prices_cached",
    "_stock_betas_cached", "_overheat_history_cached",
    "_freshness_cached",
    # banner 渲染
    "_render_banner", "_render_overheat_banner",
]

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


@st.cache_data(ttl=600, show_spinner=False)
def _vote_cached(db_mtime: float) -> dict:
    """yaml 引擎投票(verified=True);失败回落 static。db_mtime 变化即失效。"""
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
    from gold.data import GOLD_DB, gold_conn
    if not GOLD_DB.exists():
        return pd.DataFrame()
    try:
        with gold_conn() as con:
            return con.execute(
                "SELECT etf_code, etf_name, exchange, manager, tracking_index, "
                "fee_rate, listing_date FROM gold_stock_etf_master "
                "ORDER BY etf_code"
            ).df()
    except Exception:
        return pd.DataFrame()
@st.cache_data(ttl=600, show_spinner=False)
def _stock_etf_prices_cached(db_mtime: float, days: int = 365) -> pd.DataFrame:
    """v2.6 板块 F · 金股 ETF 日 K。"""
    from gold.data import GOLD_DB, gold_conn
    if not GOLD_DB.exists():
        return pd.DataFrame()
    try:
        with gold_conn() as con:
            return con.execute(
                "SELECT etf_code, date, open, close, high, low, volume, "
                "turnover, pct_change "
                "FROM gold_stock_etf_prices "
                f"WHERE date >= CURRENT_DATE - INTERVAL '{days} days' "
                "ORDER BY etf_code, date"
            ).df()
    except Exception:
        return pd.DataFrame()
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
    from gold.data import GOLD_DB, gold_conn  # 局部导入避免循环
    if not GOLD_DB.exists():
        return pd.DataFrame()
    with gold_conn() as con:
        return con.execute(
            "SELECT date, red_count, yellow_count, green_count, "
            "verdict_id, verdict_label "
            "FROM gold_overheat_history "
            f"WHERE date >= CURRENT_DATE - INTERVAL '{days} days' "
            "ORDER BY date"
        ).df()
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
        from gold.data import gold_conn
        with gold_conn() as con:
            for col, table in (("etf_date", "gold_etf_prices"),
                               ("metric_date", "gold_metrics"),
                               ("overheat_date", "gold_overheat_history")):
                try:
                    row = con.execute(f"SELECT MAX(date) FROM {table}").fetchone()
                    if row and row[0]:
                        info[col] = str(row[0])[:10]
                except Exception:
                    pass
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
