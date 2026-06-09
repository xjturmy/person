"""v2.5 行业周期判定引擎(任务包 04 / E2)。

给定行业(SW L2 名,例如「白酒」/「股份制银行」),综合 4 路信号:

  1. **cycle_type / kondratieff_position** — 直接读 `.config/industry_master.yaml`
  2. **valuation 信号(估值高低)** — 调 `industry_percentile_engine.compute()` 拿 PE 10y 分位
       · 高 (>70%) / 中 (30-70%) / 低 (<30%)
  3. **1y 趋势信号(涨跌方向)** — 用 industry_master.etf_codes[0] 从 `data/etf.duckdb`
       拿 1y 涨跌;若 etf_codes 空 → 用 leaders[0] 从 `data/preson.duckdb.prices`
       · 涨 (>+10%) / 横 (±10%) / 跌 (<-10%)
  4. **ROE 趋势信号(盈利方向)** — 行业内自选成份(.config/companies.csv 过滤
       industry_l2)的 latest ROE 中位数 vs 上一报告期(年末值)
       · 上行 / 持平 ±2pp / 下行

通过 RULE_TABLE 5×3 映射 phase(rising/topping/falling/bottoming/sideways)。

confidence:
  · 三信号同向 → 0.8
  · 两信号同向 → 0.6
  · 信号冲突 → 0.4
  · 单信号可用 → 0.3
  · 全无 → 0.1(phase=sideways)

接口契约(README.md F):
    @dataclass class IndustryCycle
    def diagnose(industry: str) -> IndustryCycle

不抛错;任何数据缺失走 sideways + 低 confidence。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import csv

import duckdb
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
INDUSTRY_MASTER = PROJECT_ROOT / ".config" / "industry_master.yaml"
COMPANIES_CSV = PROJECT_ROOT / ".config" / "companies.csv"
ETF_DB = PROJECT_ROOT / "data" / "etf.duckdb"
PRESON_DB = PROJECT_ROOT / "data" / "preson.duckdb"

# 让 industry_percentile_engine 可被 import(同目录)
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))


# ─── 规则表(模块级常量,可调阈值)──────────────────────────────────────

# (估值档位, 1y 涨跌档位) → phase
RULE_TABLE: dict[tuple[str, str], str] = {
    ("high", "up"): "topping",
    ("high", "flat"): "topping",
    ("high", "down"): "falling",
    ("mid", "up"): "rising",
    ("mid", "flat"): "sideways",
    ("mid", "down"): "falling",
    ("low", "up"): "rising",
    ("low", "flat"): "bottoming",
    ("low", "down"): "bottoming",
}

PHASE_CN: dict[str, str] = {
    "rising": "上行",
    "topping": "见顶",
    "falling": "下行",
    "bottoming": "见底",
    "sideways": "横盘",
}

# 阈值(模块级,便于后续调整)
PCT_HIGH = 70.0
PCT_LOW = 30.0
RET_UP = 0.10        # 1y 涨幅 > +10% → 上涨
RET_DOWN = -0.10     # 1y 跌幅 < -10% → 下跌
ROE_FLAT_BAND = 0.02  # ROE 同比变化 ±2pp 视为持平


# ─── 数据类 ────────────────────────────────────────────────────────────


@dataclass
class IndustryCycle:
    industry: str
    cycle_type: str                              # 成长 / 价值 / 防御 / 周期
    phase: str                                   # rising / topping / falling / bottoming / sideways
    phase_cn: str                                # 上行 / 见顶 / 下行 / 见底 / 横盘
    confidence: float                            # 0-1
    rationale: str                               # 一句理由
    kondratieff_position: str                    # 康波定位
    signals: dict = field(default_factory=dict)  # {"valuation_pct", "1y_return", "roe_trend"}


# ─── 助手:industry_master 读取 ─────────────────────────────────────────


def _load_industry_master() -> dict:
    if not INDUSTRY_MASTER.exists():
        return {"industries": []}
    try:
        with open(INDUSTRY_MASTER, encoding="utf-8") as f:
            return yaml.safe_load(f) or {"industries": []}
    except Exception:
        return {"industries": []}


def _industry_meta(industry: str) -> Optional[dict]:
    """从 industry_master.yaml 取该行业的整段配置。找不到返回 None。"""
    data = _load_industry_master()
    for item in data.get("industries", []) or []:
        if item.get("name") == industry:
            return item
    return None


# ─── 助手:自选成份 tickers ─────────────────────────────────────────────


def _self_tickers_for_industry(industry: str) -> list[str]:
    """从 .config/companies.csv 读 industry_l2 == industry 的 ticker 列表。"""
    if not COMPANIES_CSV.exists():
        return []
    out: list[str] = []
    try:
        with COMPANIES_CSV.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if (row.get("industry_l2") or "").strip() == industry:
                    t = (row.get("stock") or "").strip()
                    if t:
                        out.append(t.zfill(6))
    except Exception:
        pass
    return out


# ─── 信号 1:估值分位 ──────────────────────────────────────────────────


def _signal_valuation(industry: str) -> tuple[Optional[float], Optional[str]]:
    """返回 (pe_pct_10y, level: 'high'/'mid'/'low' or None)。"""
    try:
        from industry.percentile_engine import compute as pct_compute
    except Exception:
        return None, None
    try:
        r = pct_compute(industry)
    except Exception:
        return None, None
    pct = getattr(r, "pe_percentile_10y", None)
    if pct is None:
        # 退而求其次:用 pb_percentile_10y
        pct = getattr(r, "pb_percentile_10y", None)
    if pct is None:
        return None, None
    if pct > PCT_HIGH:
        return float(pct), "high"
    if pct < PCT_LOW:
        return float(pct), "low"
    return float(pct), "mid"


# ─── 信号 2:1y 趋势(ETF / 股票) ─────────────────────────────────────


def _etf_1y_return(etf_code: str) -> Optional[float]:
    """从 etf.duckdb 拿 etf_code 的 1y 涨跌(最新 close vs ~365 天前最近 close)。"""
    if not etf_code or not ETF_DB.exists():
        return None
    try:
        con = duckdb.connect(str(ETF_DB), read_only=True)
    except Exception:
        return None
    try:
        latest = con.execute(
            "SELECT close FROM etf_prices WHERE etf_code = ? "
            "AND close IS NOT NULL AND close > 0 ORDER BY date DESC LIMIT 1",
            [etf_code],
        ).fetchone()
        if not latest or latest[0] is None:
            return None
        cutoff = (date.today() - timedelta(days=365)).isoformat()
        ago = con.execute(
            "SELECT close FROM etf_prices WHERE etf_code = ? "
            "AND close IS NOT NULL AND close > 0 AND date <= ? "
            "ORDER BY date DESC LIMIT 1",
            [etf_code, cutoff],
        ).fetchone()
        if not ago or ago[0] is None or float(ago[0]) <= 0:
            return None
        return float(latest[0]) / float(ago[0]) - 1.0
    except Exception:
        return None
    finally:
        try:
            con.close()
        except Exception:
            pass


def _stock_1y_return(ticker: str) -> Optional[float]:
    """从 preson.duckdb.prices 拿股票的 1y 涨跌(降级路径)。"""
    if not ticker or not PRESON_DB.exists():
        return None
    try:
        con = duckdb.connect(str(PRESON_DB), read_only=True)
    except Exception:
        return None
    try:
        # 检查 prices 表存在
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        if "prices" not in tables:
            return None
        latest = con.execute(
            "SELECT close FROM prices WHERE ticker = ? "
            "AND close IS NOT NULL AND close > 0 ORDER BY date DESC LIMIT 1",
            [ticker],
        ).fetchone()
        if not latest or latest[0] is None:
            return None
        cutoff = (date.today() - timedelta(days=365)).isoformat()
        ago = con.execute(
            "SELECT close FROM prices WHERE ticker = ? "
            "AND close IS NOT NULL AND close > 0 AND date <= ? "
            "ORDER BY date DESC LIMIT 1",
            [ticker, cutoff],
        ).fetchone()
        if not ago or ago[0] is None or float(ago[0]) <= 0:
            return None
        return float(latest[0]) / float(ago[0]) - 1.0
    except Exception:
        return None
    finally:
        try:
            con.close()
        except Exception:
            pass


def _signal_trend(meta: dict) -> tuple[Optional[float], Optional[str]]:
    """返回 (1y_return, direction: 'up'/'flat'/'down' or None)。
    优先用 etf_codes[0],降级 leaders[0]。
    """
    etf_codes = meta.get("etf_codes") or []
    ret: Optional[float] = None
    if etf_codes:
        ret = _etf_1y_return(str(etf_codes[0]))
    if ret is None:
        leaders = meta.get("leaders") or []
        if leaders:
            ret = _stock_1y_return(str(leaders[0]).zfill(6))
    if ret is None:
        return None, None
    if ret > RET_UP:
        return ret, "up"
    if ret < RET_DOWN:
        return ret, "down"
    return ret, "flat"


# ─── 信号 3:ROE 趋势 ─────────────────────────────────────────────────


def _detect_roe_metric_name(con) -> Optional[str]:
    """探针 profitability 表里实际的 ROE 字段名(可能是「净资产收益率(ROE)」/
    「ROE」/「ROE-加权」等)。返回首个找到的 metric 名或 None。
    """
    candidates = [
        "净资产收益率(ROE)",
        "净资产收益率",
        "ROE",
        "ROE-加权",
        "ROE(加权)",
        "净资产收益率(加权)",
    ]
    try:
        rows = con.execute(
            "SELECT DISTINCT metric FROM profitability "
            "WHERE metric LIKE '%ROE%' OR metric LIKE '%净资产%'"
        ).fetchall()
    except Exception:
        return None
    available = {r[0] for r in rows if r and r[0]}
    for c in candidates:
        if c in available:
            return c
    # 兜底:任何含 ROE 的
    for m in available:
        if "ROE" in str(m):
            return m
    return None


def _signal_roe_trend(self_tickers: list[str]) -> tuple[Optional[dict], Optional[str]]:
    """返回 (info_dict, trend: '上行'/'持平'/'下行' or None)。

    info_dict = {"latest_roe_median": x, "prev_roe_median": y, "delta_pp": z}
    口径:对每个 ticker 取最新年末(12-31)ROE 与上一年末 ROE,
    分别求行业内中位数,差值 > +2pp → 上行 / < -2pp → 下行 / 否则持平。
    单位:本仓库 ROE 通常以百分比形式存储(e.g., 25.0 表示 25%);
    若发现是小数(<1),做个保守缩放,band 也按比例处理。
    """
    if not self_tickers or not PRESON_DB.exists():
        return None, None
    try:
        con = duckdb.connect(str(PRESON_DB), read_only=True)
    except Exception:
        return None, None
    try:
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        if "profitability" not in tables:
            return None, None
        roe_metric = _detect_roe_metric_name(con)
        if not roe_metric:
            return None, None
        placeholders = ",".join(["?"] * len(self_tickers))
        # 取每个 ticker 最新 2 个年末 (12-31) ROE
        rows = con.execute(
            f"""
            SELECT ticker, EXTRACT(YEAR FROM date) AS y, value
            FROM profitability
            WHERE metric = ?
              AND ticker IN ({placeholders})
              AND MONTH(date) = 12 AND DAY(date) = 31
              AND value IS NOT NULL
            ORDER BY ticker, y DESC
            """,
            [roe_metric, *self_tickers],
        ).fetchall()
    except Exception:
        return None, None
    finally:
        try:
            con.close()
        except Exception:
            pass

    if not rows:
        return None, None

    # 每个 ticker 取最新两个年份
    by_ticker: dict[str, list[tuple[int, float]]] = {}
    for t, y, v in rows:
        if v is None:
            continue
        try:
            by_ticker.setdefault(str(t), []).append((int(y), float(v)))
        except Exception:
            continue

    latest_vals: list[float] = []
    prev_vals: list[float] = []
    for _t, pairs in by_ticker.items():
        pairs_sorted = sorted(pairs, key=lambda x: x[0], reverse=True)
        if len(pairs_sorted) >= 1:
            latest_vals.append(pairs_sorted[0][1])
        if len(pairs_sorted) >= 2:
            prev_vals.append(pairs_sorted[1][1])

    if not latest_vals or not prev_vals:
        return None, None

    def _median(xs: list[float]) -> float:
        xs = sorted(xs)
        n = len(xs)
        return xs[n // 2] if n % 2 == 1 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])

    cur = _median(latest_vals)
    prev = _median(prev_vals)
    delta = cur - prev

    # 单位归一:若两值都 < 1 视为小数(0.25 等),阈值取 0.02;
    # 否则视为百分比(25.0),阈值取 2.0
    if max(abs(cur), abs(prev)) < 1.0:
        band = ROE_FLAT_BAND
    else:
        band = ROE_FLAT_BAND * 100.0

    if delta > band:
        trend = "上行"
    elif delta < -band:
        trend = "下行"
    else:
        trend = "持平"
    info = {"latest": cur, "prev": prev, "delta_pp": delta}
    return info, trend


# ─── 综合判定 ─────────────────────────────────────────────────────────


def _confidence_from_signals(val_lvl: Optional[str],
                             trend_dir: Optional[str],
                             roe_trend: Optional[str],
                             phase: str) -> float:
    """三信号同向 0.8 / 两信号同向 0.6 / 冲突 0.4 / 单信号 0.3 / 全无 0.1。

    "同向" 判定:
      · valuation high → 偏空 / low → 偏多 / mid → 中性
      · trend up → 偏多 / down → 偏空 / flat → 中性
      · roe 上行 → 偏多 / 下行 → 偏空 / 持平 → 中性
    """
    available = sum(1 for s in (val_lvl, trend_dir, roe_trend) if s is not None)
    if available == 0:
        return 0.1
    if available == 1:
        return 0.3

    def _polarity(val_lvl, trend_dir, roe_trend) -> tuple[Optional[int], Optional[int], Optional[int]]:
        v = None
        if val_lvl == "high":
            v = -1
        elif val_lvl == "low":
            v = 1
        elif val_lvl == "mid":
            v = 0
        t = None
        if trend_dir == "up":
            t = 1
        elif trend_dir == "down":
            t = -1
        elif trend_dir == "flat":
            t = 0
        r = None
        if roe_trend == "上行":
            r = 1
        elif roe_trend == "下行":
            r = -1
        elif roe_trend == "持平":
            r = 0
        return v, t, r

    v, t, r = _polarity(val_lvl, trend_dir, roe_trend)
    polarities = [p for p in (v, t, r) if p is not None]
    non_neutral = [p for p in polarities if p != 0]

    if not non_neutral:
        # 全部中性 → 弱多信号但无方向
        return 0.4 if available >= 2 else 0.3

    pos = sum(1 for p in non_neutral if p > 0)
    neg = sum(1 for p in non_neutral if p < 0)

    if available >= 3:
        # 三信号都 OK
        if pos == 0 or neg == 0:
            # 同向(或与中性混合,均算一致)
            return 0.8
        return 0.4  # 冲突
    if available == 2:
        if pos == 0 or neg == 0:
            return 0.6
        return 0.4
    return 0.3


def _format_pct(p: Optional[float]) -> str:
    return f"{p:.0f}" if p is not None else "—"


def _format_ret(r: Optional[float]) -> str:
    if r is None:
        return "—"
    sign = "+" if r >= 0 else ""
    return f"{sign}{r * 100:.0f}%"


def diagnose(industry: str) -> IndustryCycle:
    """规则化判定行业当前周期阶段。

    步骤:
      1. 读 industry_master.yaml.industries[name==industry] →
         cycle_type / kondratieff_position / etf_codes / leaders
      2. 三信号取值:估值分位 / 1y 涨跌 / ROE 趋势
      3. RULE_TABLE 5×3 映射 phase
      4. confidence = 信号一致度
      5. rationale 一句话拼接
    """
    if not industry or not isinstance(industry, str):
        return IndustryCycle(
            industry=str(industry or ""),
            cycle_type="未知",
            phase="sideways",
            phase_cn=PHASE_CN["sideways"],
            confidence=0.1,
            rationale="行业名为空 → 无法判定",
            kondratieff_position="未知",
            signals={},
        )

    meta = _industry_meta(industry) or {}
    cycle_attrs = meta.get("cycle_attrs") or {}
    cycle_type = str(cycle_attrs.get("type") or "未知")
    kondratieff = str(cycle_attrs.get("kondratieff_position") or "未知")

    # 信号 1:估值
    pct, val_lvl = _signal_valuation(industry)
    # 信号 2:1y 涨跌
    ret_1y, trend_dir = _signal_trend(meta)
    # 信号 3:ROE 趋势
    self_tickers = _self_tickers_for_industry(industry)
    _roe_info, roe_trend = _signal_roe_trend(self_tickers)

    # 规则映射 phase
    if val_lvl is not None and trend_dir is not None:
        phase = RULE_TABLE.get((val_lvl, trend_dir), "sideways")
    elif val_lvl is None and trend_dir is None:
        # 全无信号 → sideways
        phase = "sideways"
    else:
        # 仅一信号:用 ROE 兜底辅助一下
        if val_lvl is not None:
            # 仅估值
            if val_lvl == "high":
                phase = "topping" if roe_trend != "下行" else "falling"
            elif val_lvl == "low":
                phase = "bottoming" if roe_trend != "上行" else "rising"
            else:
                phase = "sideways"
        else:
            # 仅趋势
            if trend_dir == "up":
                phase = "rising"
            elif trend_dir == "down":
                phase = "falling"
            else:
                phase = "sideways"

    confidence = _confidence_from_signals(val_lvl, trend_dir, roe_trend, phase)
    if val_lvl is None and trend_dir is None and roe_trend is None:
        phase = "sideways"

    # 组装 signals dict
    signals: dict = {}
    if pct is not None:
        signals["valuation_pct"] = round(pct, 2)
    if ret_1y is not None:
        signals["1y_return"] = round(ret_1y, 4)
    if roe_trend is not None:
        signals["roe_trend"] = roe_trend

    # 组装 rationale 一句话
    parts: list[str] = []
    if pct is not None:
        parts.append(f"PE 第 {_format_pct(pct)} 分位")
    if ret_1y is not None:
        parts.append(f"1y 涨跌 {_format_ret(ret_1y)}")
    if roe_trend is not None:
        parts.append(f"ROE 同比 {roe_trend}")
    if not parts:
        parts.append("无可用信号")
    phase_cn = PHASE_CN.get(phase, "横盘")
    rationale = (
        " + ".join(parts)
        + f" → {phase_cn}(置信 {confidence:.1f})"
    )

    return IndustryCycle(
        industry=industry,
        cycle_type=cycle_type,
        phase=phase,
        phase_cn=phase_cn,
        confidence=confidence,
        rationale=rationale,
        kondratieff_position=kondratieff,
        signals=signals,
    )


__all__ = ["IndustryCycle", "diagnose", "RULE_TABLE", "PHASE_CN"]
