"""dash-01 横切组件:顶部全局温度计栏.

读 DuckDB `macro` 表,渲染 5 项指标(M2_YOY / CPI_YOY / 10Y_YIELD / USDCNY / A_FULL_PE)
的紧凑徽章,显示在每个 Tab 的顶部。

口径:
- "current" = 最新一期值
- "pct_5y"  = 当前值在最近 5 年同指标序列中的分位(0-1)
- 颜色:
    interpret="high"(高=偏紧/贵,如 CPI/USD): >80% 红 / 50-80% 黄 / <50% 绿
    interpret="low" (低=偏松/便宜,如 10Y/A_FULL_PE):  <20% 绿 / 20-50% 绿 / >50% 黄红

调用:
    import header_thermometer as hth
    hth.render(db_path, mtime)         # 在 st.title 之后调一次
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import duckdb
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
MACRO_DB_DEFAULT = ROOT / "data" / "macro.duckdb"


# M1 视觉语言常量 — 供其他模块(M5 等)复用,统一 dashboard 状态卡风格
CARD_STYLE = (
    "text-align:center;border:1px solid #e0e0e0;border-radius:8px;"
    "padding:8px;background:#fafafa;"
)
CARD_LABEL_STYLE = "font-size:11px;color:#666"
CARD_VALUE_STYLE = "font-size:18px;font-weight:700;line-height:1.2"
CARD_HINT_STYLE = "font-size:10px;color:#888"


def card_html(label: str, value: str, hint: str = "",
              tooltip: str = "", value_color: str = "") -> str:
    """渲染一张 M1 风格紧凑卡片(三行:label / value / hint)。

    供 M5 ttyd 状态、其他模块统一视觉用。
    value_color 为空时走默认黑色;传入 hex 改写主数字色。
    """
    val_style = CARD_VALUE_STYLE + (f";color:{value_color}" if value_color else "")
    title_attr = f" title='{tooltip}'" if tooltip else ""
    hint_div = f"<div style='{CARD_HINT_STYLE}'>{hint}</div>" if hint else ""
    return (
        f"<div{title_attr} style='{CARD_STYLE}'>"
        f"<div style='{CARD_LABEL_STYLE}'>{label}</div>"
        f"<div style='{val_style}'>{value}</div>"
        f"{hint_div}"
        f"</div>"
    )


# bands 用于在小图上画横向阈值带 + 左侧文字标注
# 每个 band: {emoji, label, lo, hi, fill}; lo/hi 为 None 表示无下/上限
INDICATORS = [
    {"key": "M2_YOY",    "label": "M2 同比",    "unit": "%",       "fmt": "{:.1f}%",  "interpret": "high",
     "meaning":   "货币供应量增速,反映流动性松紧",
     "thresholds": "🔴 <6% 紧缩 / 🟢 6-10% 适中 / 🟡 10-12% 偏松 / 🔴 >12% 过热",
     "bands": [
         {"emoji": "🔴", "label": "<6% 紧缩",   "lo": None, "hi": 6,    "fill": "#d9534f"},
         {"emoji": "🟢", "label": "6-10% 适中", "lo": 6,    "hi": 10,   "fill": "#1b8a3a"},
         {"emoji": "🟡", "label": "10-12% 偏松","lo": 10,   "hi": 12,   "fill": "#f0ad4e"},
         {"emoji": "🔴", "label": ">12% 过热",  "lo": 12,   "hi": None, "fill": "#d9534f"},
     ]},
    {"key": "CPI_YOY",   "label": "CPI 同比",   "unit": "%",       "fmt": "{:.1f}%",  "interpret": "high",
     "meaning":   "通胀水平,影响利率与企业利润",
     "thresholds": "🔴 <0% 通缩 / 🟢 0-3% 健康 / 🟡 3-4% 偏高 / 🔴 >4% 过热",
     "bands": [
         {"emoji": "🔴", "label": "<0% 通缩",   "lo": None, "hi": 0,    "fill": "#d9534f"},
         {"emoji": "🟢", "label": "0-3% 健康",  "lo": 0,    "hi": 3,    "fill": "#1b8a3a"},
         {"emoji": "🟡", "label": "3-4% 偏高",  "lo": 3,    "hi": 4,    "fill": "#f0ad4e"},
         {"emoji": "🔴", "label": ">4% 过热",   "lo": 4,    "hi": None, "fill": "#d9534f"},
     ]},
    {"key": "10Y_YIELD", "label": "10Y 国债",   "unit": "%",       "fmt": "{:.2f}%",  "interpret": "low",
     "meaning":   "无风险利率,股票估值锚",
     "thresholds": "🟢 <2.5% 利好股 / 🟡 2.5-3.5% 平衡 / 🔴 >3.5% 压制估值",
     "bands": [
         {"emoji": "🟢", "label": "<2.5% 利好股",  "lo": None, "hi": 2.5,  "fill": "#1b8a3a"},
         {"emoji": "🟡", "label": "2.5-3.5% 平衡","lo": 2.5,  "hi": 3.5,  "fill": "#f0ad4e"},
         {"emoji": "🔴", "label": ">3.5% 压估值",  "lo": 3.5,  "hi": None, "fill": "#d9534f"},
     ]},
    {"key": "USDCNY",    "label": "USD/CNY",   "unit": "CNY/USD", "fmt": "{:.4f}",   "interpret": "high",
     "meaning":   "汇率,反映外资流入/流出压力",
     "thresholds": "🟢 <7.0 升值 / 🟡 7.0-7.2 平稳 / 🔴 >7.2 贬值压力",
     "bands": [
         {"emoji": "🟢", "label": "<7.0 升值",     "lo": None, "hi": 7.0,  "fill": "#1b8a3a"},
         {"emoji": "🟡", "label": "7.0-7.2 平稳", "lo": 7.0,  "hi": 7.2,  "fill": "#f0ad4e"},
         {"emoji": "🔴", "label": ">7.2 贬值",    "lo": 7.2,  "hi": None, "fill": "#d9534f"},
     ]},
    {"key": "A_FULL_PE", "label": "A 股全指 PE", "unit": "x",     "fmt": "{:.1f}x",  "interpret": "low",
     "meaning":   "全市场加权 PE(理杏仁口径,000985 中证全指,格雷厄姆指数主算)",
     "thresholds": "🟢 <17 低估 / 🟢 17-20 偏低 / 🟡 20-23 合理 / 🟠 23-27 偏高 / 🔴 >27 高估",
     "bands": [
         {"emoji": "🟢", "label": "<17 低估",   "lo": None, "hi": 17,   "fill": "#1b8a3a"},
         {"emoji": "🟢", "label": "17-20 偏低","lo": 17,   "hi": 20,   "fill": "#5cb85c"},
         {"emoji": "🟡", "label": "20-23 合理","lo": 20,   "hi": 23,   "fill": "#f0ad4e"},
         {"emoji": "🟠", "label": "23-27 偏高","lo": 23,   "hi": 27,   "fill": "#fd7e14"},
         {"emoji": "🔴", "label": ">27 高估",  "lo": 27,   "hi": None, "fill": "#d9534f"},
     ]},
]


def _badge(pct: Optional[float], interpret: str) -> str:
    if pct is None:
        return "⚪"
    if interpret == "high":
        if pct >= 0.80: return "🔴"
        if pct >= 0.50: return "🟡"
        return "🟢"
    # interpret == "low"
    if pct <= 0.20: return "🟢"
    if pct <= 0.50: return "🟢"
    if pct <= 0.80: return "🟡"
    return "🔴"


@st.cache_data(ttl=3600, show_spinner=False)
def _load(db_path: str, mtime: float) -> dict:
    """每个 indicator 取最新值 + 5y 分位。失败/缺数据时该项返回 None。"""
    p = Path(db_path)
    if not p.exists():
        return {"_error": f"DuckDB 不存在: {db_path}"}
    try:
        con = duckdb.connect(str(p), read_only=True)
    except Exception as e:
        return {"_error": f"DuckDB 连接失败: {e}"}
    out: dict = {}
    try:
        tabs = {r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()}
        if "macro" not in tabs:
            return {"_error": "macro 表不存在 — 跑 `.venv/bin/python .tools/db/fetch_macro.py`"}

        cutoff = date.today() - timedelta(days=365 * 5)
        for ind in INDICATORS:
            key = ind["key"]
            try:
                row = con.execute(
                    "SELECT value, date FROM macro "
                    "WHERE indicator = ? AND value IS NOT NULL "
                    "ORDER BY date DESC LIMIT 1",
                    [key],
                ).fetchone()
                if not row:
                    out[key] = None
                    continue
                cur = float(row[0])
                cur_date = row[1]
                series = con.execute(
                    "SELECT value FROM macro "
                    "WHERE indicator = ? AND value IS NOT NULL AND date >= ?",
                    [key, cutoff],
                ).fetchdf()
                if len(series) > 5:
                    pct = float((series["value"] <= cur).sum()) / len(series)
                else:
                    pct = None
                out[key] = {"current": cur, "date": str(cur_date),
                            "pct_5y": pct, "n_5y": len(series)}
            except Exception as e:
                out[key] = {"error": str(e)}
    finally:
        con.close()
    return out


def is_data_ready(db_path: str | Path, db_mtime: float) -> bool:
    data = _load(str(db_path), db_mtime)
    if "_error" in data:
        return False
    return any(v and "error" not in (v or {}) for v in data.values())


def render(db_path: str | Path, mtime: float) -> None:
    """在调用处渲染温度计栏。数据缺失时退化为友好提示。"""
    data = _load(str(db_path), mtime)
    if "_error" in data:
        st.caption(f"🌡️ 市场温度计 · {data['_error']}")
        return
    if not any(v and "error" not in (v or {}) for v in data.values()):
        st.caption("🌡️ 市场温度计 · 暂无数据 · 跑 `.venv/bin/python .tools/db/fetch_macro.py`")
        return

    cols = st.columns(len(INDICATORS))
    for col, ind in zip(cols, INDICATORS):
        d = data.get(ind["key"])
        with col:
            if not d or "error" in (d or {}):
                st.markdown(
                    "<div style='text-align:center;border:1px solid #e0e0e0;"
                    "border-radius:8px;padding:8px;background:#fafafa;'>"
                    f"<div style='font-size:11px;color:#888'>{ind['label']}</div>"
                    "<div style='font-size:18px;color:#bbb;font-weight:600'>—</div>"
                    "<div style='font-size:10px;color:#aaa'>无数据</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                continue
            cur = d["current"]
            pct = d.get("pct_5y")
            badge = _badge(pct, ind["interpret"])
            cur_str = ind["fmt"].format(cur)
            pct_str = f"{pct*100:.0f}%" if pct is not None else "—"
            meaning = ind.get("meaning", "")
            thresholds = ind.get("thresholds", "")
            tooltip_lines = [
                f"最新 {d['date']} · 5y 分位 {pct_str} · 样本 {d.get('n_5y', '?')} 个",
            ]
            if meaning:
                tooltip_lines.append(f"含义:{meaning}")
            if thresholds:
                tooltip_lines.append(f"阈值:{thresholds}")
            tooltip = " | ".join(tooltip_lines)
            st.markdown(
                f"<div title='{tooltip}' style='text-align:center;"
                "border:1px solid #e0e0e0;border-radius:8px;padding:8px;background:#fafafa;'>"
                f"<div style='font-size:11px;color:#666'>{ind['label']}</div>"
                f"<div style='font-size:18px;font-weight:700;line-height:1.2'>{cur_str}</div>"
                f"<div style='font-size:10px;color:#888'>{badge} 5y {pct_str}</div>"
                "</div>",
                unsafe_allow_html=True,
            )


# ───── 兼容旧 API ───────────────────────────────────────────────────


def render_thermometer(db_mtime: float = 0.0) -> None:
    """旧 API 名,自动指向默认 macro.duckdb。"""
    mt = db_mtime
    if mt == 0.0 and MACRO_DB_DEFAULT.exists():
        mt = MACRO_DB_DEFAULT.stat().st_mtime
    render(MACRO_DB_DEFAULT, mt)


__all__ = [
    "render", "render_thermometer", "is_data_ready", "INDICATORS",
    "card_html", "CARD_STYLE", "CARD_LABEL_STYLE", "CARD_VALUE_STYLE", "CARD_HINT_STYLE",
]
