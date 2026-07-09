"""我的持仓视角 — 决策中心的窄口径持仓工作台。

这个模块不直接修改 portfolio.yaml。它先用用户确认的持仓清单作为
决策视角白名单，把股票 / ETF 拆成适合复盘的几个问题。
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

import streamlit as st


ROOT = Path(__file__).resolve().parents[4]
PRESON_DB = ROOT / "data" / "preson.duckdb"
ETF_DB = ROOT / "data" / "etf.duckdb"
GOLD_DB = ROOT / "data" / "gold.duckdb"

STATIC_DATA_NOTES = {
    "562500": "静态配置:机器人主题，行情待抓取",
    "512890": "静态配置:红利低波，行情待抓取",
    "510880": "静态配置:上证红利50，行情待抓取",
}


@dataclass(frozen=True)
class FocusHolding:
    name: str
    ticker: str
    kind: str
    sleeve: str
    role: str
    decision_question: str
    review_focus: str
    default_action: str
    note: str = ""


FOCUS_HOLDINGS: tuple[FocusHolding, ...] = (
    FocusHolding(
        name="中国中车",
        ticker="601766",
        kind="股票",
        sleeve="防御 / 周期修复",
        role="央企轨交龙头，偏低估与政策周期修复。",
        decision_question="继续持有，还是在订单/分红改善后做再平衡？",
        review_focus="看 PE/PB 分位、股息率、动车组招标和海外订单。",
        default_action="持有复盘",
    ),
    FocusHolding(
        name="新华保险",
        ticker="601336",
        kind="股票",
        sleeve="金融 / 保险",
        role="低估保险股，核心看资产端弹性和负债端修复。",
        decision_question="低估是否足够补仓，还是只作为金融弹性仓？",
        review_focus="看 P/EV、NBV、偿付能力、权益市场β和分红稳定性。",
        default_action="低估观察",
    ),
    FocusHolding(
        name="海康威视",
        ticker="002415",
        kind="股票",
        sleeve="AIoT / 高股息成长",
        role="安防与 AIoT 龙头，兼具现金流、防御和第二曲线。",
        decision_question="海外压力和创新业务之间，是否仍值得长期拿？",
        review_focus="看创新业务占比、海外恢复、自由现金流和股息率。",
        default_action="跟踪验证",
    ),
    FocusHolding(
        name="蜜雪集团",
        ticker="02097",
        kind="股票",
        sleeve="消费 / 下沉成长",
        role="现制茶饮龙头，核心看门店扩张、加盟商现金流和海外增长。",
        decision_question="IPO 后估值和增长是否匹配，是否值得作为消费成长仓长期拿？",
        review_focus="看同店恢复、海外门店、加盟商盈利、供应链毛利和港股流动性。",
        default_action="成长验证",
    ),
    FocusHolding(
        name="机器人ETF",
        ticker="562500",
        kind="ETF",
        sleeve="进攻 / 产业主题",
        role="机器人与智能制造方向的小仓位进攻工具。",
        decision_question="主题热度高时是否控制仓位，回调时是否分批加？",
        review_focus="看主题估值、成交热度、核心成分和产业催化。",
        default_action="小仓位纪律",
    ),
    FocusHolding(
        name="券商ETF",
        ticker="512000",
        kind="ETF",
        sleeve="进攻 / 市场β",
        role="牛市早周期弹性仓，和市场成交额高度相关。",
        decision_question="市场冰点是否加仓，行情过热是否主动兑现？",
        review_focus="看沪深成交额、券商 PB、市场温度和政策催化。",
        default_action="周期交易",
    ),
    FocusHolding(
        name="有色ETF",
        ticker="512400",
        kind="ETF",
        sleeve="周期 / 商品资源",
        role="有色金属与金矿链条工具，受商品周期和金价共同驱动。",
        decision_question="商品复苏是否进入右侧，还是只作为黄金链增强仓？",
        review_focus="看铜/金价格、美元实际利率、库存周期、资源股盈利和回撤。",
        default_action="周期确认",
    ),
    FocusHolding(
        name="黄金股ETF",
        ticker="517520",
        kind="ETF",
        sleeve="黄金增强 / 高β",
        role="金价上行时的放大工具，波动高于实物黄金 ETF。",
        decision_question="当前金价信号下，是否该比黄金ETF更小仓位？",
        review_focus="看金价趋势、实际利率、β、回撤和 R² 稳定性。",
        default_action="高β控制",
    ),
    FocusHolding(
        name="黄金ETF",
        ticker="518660",
        kind="ETF",
        sleeve="防御 / 资产配置",
        role="组合防御锚，主要对冲实际利率下行和风险事件。",
        decision_question="黄金仓位是否达到战略目标，是否需要再平衡？",
        review_focus="看实际利率、美元、金银比、黄金红绿灯和目标仓位。",
        default_action="配置锚定",
    ),
    FocusHolding(
        name="化工ETF",
        ticker="516020",
        kind="ETF",
        sleeve="周期 / 复苏",
        role="基础化工复苏与补库周期的行业工具。",
        decision_question="化工景气是否进入上行段，还是仍需等待价格信号？",
        review_focus="看化工品价格、库存、油价、行业 PE 分位和龙头盈利。",
        default_action="周期等待",
    ),
    FocusHolding(
        name="红利低波",
        ticker="512890",
        kind="ETF",
        sleeve="防御 / 高股息低波",
        role="防御权益核心仓，靠高股息、低估值和低波动稳定组合。",
        decision_question="当前是否作为底仓继续持有，还是与黄金/现金做再平衡？",
        review_focus="看股息率、估值分位、银行煤炭权重、利率环境和回撤。",
        default_action="底仓持有",
    ),
    FocusHolding(
        name="短融ETF",
        ticker="511360",
        kind="ETF",
        sleeve="现金 / 短久期",
        role="现金替代和流动性缓冲工具。",
        decision_question="现金缓冲是否足够，是否需要为加仓释放资金？",
        review_focus="看现金需求、短端利率和组合权益仓位。",
        default_action="现金管理",
    ),
    FocusHolding(
        name="新汽车ETF",
        ticker="515030",
        kind="ETF",
        sleeve="进攻 / 新能源车主题",
        role="新能源汽车产业链主题工具仓。",
        decision_question="产业链价格战和销量修复之间，是否只保留小仓位？",
        review_focus="看销量、价格战、产业链利润和主题估值。",
        default_action="主题仓纪律",
    ),
    FocusHolding(
        name="红利50",
        ticker="510880",
        kind="ETF",
        sleeve="防御 / 红利蓝筹",
        role="更集中于高股息蓝筹的红利仓，弹性和集中度高于红利低波。",
        decision_question="红利暴露是否过高，是否和红利低波形成重复配置？",
        review_focus="看指数股息率、行业集中度、银行/能源权重和相对红利低波表现。",
        default_action="重复度检查",
        note="默认按上证红利 ETF 510880；本项目里的 515880 当前是通信ETF，不作为红利替代。",
    ),
)


def _fmt_money(v: float | None) -> str:
    if v is None:
        return "—"
    if abs(v) >= 10000:
        return f"{v / 10000:.1f} 万"
    return f"{v:,.0f}"


def _fmt_price(v: float | None) -> str:
    if v is None:
        return "—"
    if abs(v) < 10:
        return f"{v:.3f}"
    return f"{v:,.2f}"


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.1f}%"


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_weight(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.0f}%"


def _price_band_html(row: Any | None) -> str:
    if row is None:
        return """
        <div class="hf-band hf-band-muted">
          <span>价格范围</span>
          <p>待录入账本后显示</p>
        </div>
        """
    band = getattr(row, "price_band", None) or {}
    if not isinstance(band, dict) or not band:
        return """
        <div class="hf-band hf-band-muted">
          <span>价格范围</span>
          <p>待最终确认</p>
        </div>
        """
    buy = _num(band.get("buy_below"))
    add = _num(band.get("add_below"))
    trim = _num(band.get("trim_above"))
    exit_ = _num(band.get("exit_above"))
    stop = _num(band.get("stop_loss_below"))
    parts = []
    if buy is not None:
        parts.append(f"买入≤{_fmt_price(buy)}")
    if add is not None:
        parts.append(f"加仓≤{_fmt_price(add)}")
    if trim is not None:
        parts.append(f"减仓≥{_fmt_price(trim)}")
    if exit_ is not None:
        parts.append(f"清仓评估≥{_fmt_price(exit_)}")
    if stop is not None:
        parts.append(f"失效≤{_fmt_price(stop)}")
    text = " · ".join(parts) if parts else "待最终确认"
    return f"""
    <div class="hf-band">
      <span>价格范围</span>
      <p>{escape(text)}</p>
    </div>
    """


def _position_band_html(row: Any | None) -> str:
    if row is None:
        return """
        <div class="hf-band hf-band-muted">
          <span>仓位范围</span>
          <p>待录入账本后显示</p>
        </div>
        """
    band = getattr(row, "position_band", None) or {}
    if not isinstance(band, dict) or not band:
        return """
        <div class="hf-band hf-band-muted">
          <span>仓位范围</span>
          <p>待确认类型上限</p>
        </div>
        """
    role = str(band.get("role") or "仓位")
    min_w = _num(band.get("min_weight"))
    target_w = _num(band.get("target_weight"))
    max_w = _num(band.get("max_weight"))
    actual = _num(getattr(row, "actual_weight", None))
    status = ""
    if actual is not None and max_w is not None and actual > max_w:
        status = f" · 当前{_fmt_weight(actual)} 超上限"
    elif actual is not None and target_w is not None and actual >= target_w:
        status = f" · 当前{_fmt_weight(actual)} 高于目标"
    elif actual is not None:
        status = f" · 当前{_fmt_weight(actual)}"
    text = f"{role}: {_fmt_weight(min_w)} / {_fmt_weight(target_w)} / {_fmt_weight(max_w)}{status}"
    return f"""
    <div class="hf-band">
      <span>仓位范围</span>
      <p>{escape(text)}</p>
    </div>
    """


def _snap_row_by_ticker(snap: Any) -> dict[str, Any]:
    return {str(r.ticker): r for r in getattr(snap, "rows", [])}


def _latest_market_info(tickers: tuple[str, ...]) -> dict[str, dict[str, float | None]]:
    """尽量从本地库补最新价和 PE 分位；ETF 数据不足时自然降级。"""
    if not tickers:
        return {}
    out: dict[str, dict[str, Any]] = {}

    def _ensure(ticker: str) -> dict[str, Any]:
        return out.setdefault(
            str(ticker),
            {"last_price": None, "pe_pct": None, "source": "", "data_note": "未接入行情"},
        )

    # 股票 / 港股:preson.duckdb
    try:
        import duckdb

        if PRESON_DB.exists():
            con = duckdb.connect(str(PRESON_DB), read_only=True)
            try:
                placeholders = ",".join("?" for _ in tickers)
                price_rows = con.execute(
                    f"""
                    SELECT ticker, close, date
                    FROM (
                        SELECT ticker, close, date,
                               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
                        FROM prices
                        WHERE ticker IN ({placeholders})
                    )
                    WHERE rn = 1
                    """,
                    list(tickers),
                ).fetchall()
                for ticker, px, dt in price_rows:
                    if px is None:
                        continue
                    info = _ensure(str(ticker))
                    info["last_price"] = float(px)
                    info["source"] = "preson"
                    info["data_note"] = f"行情至 {dt}"

                val_rows = con.execute(
                    f"""
                    WITH latest AS (
                        SELECT ticker, value
                        FROM (
                            SELECT ticker, value,
                                   ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
                            FROM valuation
                            WHERE ticker IN ({placeholders})
                              AND metric = 'PE-TTM'
                        )
                        WHERE rn = 1
                    ),
                    series AS (
                        SELECT ticker, value
                        FROM valuation
                        WHERE ticker IN ({placeholders})
                          AND metric = 'PE-TTM'
                          AND value IS NOT NULL
                          AND date >= CURRENT_DATE - INTERVAL 10 YEAR
                    )
                    SELECT l.ticker,
                           SUM(CASE WHEN s.value <= l.value THEN 1 ELSE 0 END)
                             * 1.0 / NULLIF(COUNT(s.value), 0) AS pct
                    FROM latest l
                    LEFT JOIN series s ON s.ticker = l.ticker
                    GROUP BY l.ticker, l.value
                    """,
                    [*tickers, *tickers],
                ).fetchall()
                for ticker, pct in val_rows:
                    info = _ensure(str(ticker))
                    info["pe_pct"] = float(pct) if pct is not None else None
            finally:
                con.close()

        # 普通行业 ETF:etf.duckdb
        if ETF_DB.exists():
            con = duckdb.connect(str(ETF_DB), read_only=True)
            try:
                placeholders = ",".join("?" for _ in tickers)
                rows = con.execute(
                    f"""
                    SELECT etf_code, close, date
                    FROM (
                        SELECT etf_code, close, date,
                               ROW_NUMBER() OVER (PARTITION BY etf_code ORDER BY date DESC) AS rn
                        FROM etf_prices
                        WHERE etf_code IN ({placeholders})
                    )
                    WHERE rn = 1
                    """,
                    list(tickers),
                ).fetchall()
                for ticker, px, dt in rows:
                    info = _ensure(str(ticker))
                    info["last_price"] = float(px) if px is not None else None
                    info["source"] = "etf"
                    info["data_note"] = f"ETF行情至 {dt}"
            finally:
                con.close()

        # 黄金 / 金股 / 有色金矿 ETF:gold.duckdb
        if GOLD_DB.exists():
            con = duckdb.connect(str(GOLD_DB), read_only=True)
            try:
                for table in ("gold_etf_prices", "gold_stock_etf_prices"):
                    placeholders = ",".join("?" for _ in tickers)
                    rows = con.execute(
                        f"""
                        SELECT etf_code, close, date
                        FROM (
                            SELECT etf_code, close, date,
                                   ROW_NUMBER() OVER (PARTITION BY etf_code ORDER BY date DESC) AS rn
                            FROM {table}
                            WHERE etf_code IN ({placeholders})
                        )
                        WHERE rn = 1
                        """,
                        list(tickers),
                    ).fetchall()
                    for ticker, px, dt in rows:
                        info = _ensure(str(ticker))
                        info["last_price"] = float(px) if px is not None else None
                        info["source"] = "gold"
                        info["data_note"] = f"黄金/金股行情至 {dt}"
            finally:
                con.close()
        for ticker, note in STATIC_DATA_NOTES.items():
            if ticker in tickers and ticker not in out:
                info = _ensure(ticker)
                info["source"] = "static"
                info["data_note"] = note
        return out
    except Exception:
        return out


def _status_label(row: Any | None) -> tuple[str, str, str]:
    if row is None:
        return "待录入", "#F8FAFC", "#64748B"
    status = str(getattr(row, "status", "") or "")
    if status == "active":
        return "账本持仓", "#ECFDF3", "#15803D"
    if status == "watch":
        return "账本观察", "#EFF6FF", "#2563EB"
    return status or "已记录", "#F8FAFC", "#64748B"


def _card_html(item: FocusHolding, row: Any | None, market: dict[str, float | None]) -> str:
    label, bg, fg = _status_label(row)
    last_price = getattr(row, "last_price", None) if row is not None else market.get("last_price")
    pe_pct = getattr(row, "pe_pct", None) if row is not None else market.get("pe_pct")
    target_weight = getattr(row, "target_weight", None) if row is not None else None
    actual_weight = getattr(row, "actual_weight", None) if row is not None else None
    market_value = getattr(row, "market_value", None) if row is not None else None
    shares = getattr(row, "shares", None) if row is not None else None
    thesis = getattr(row, "thesis", "") if row is not None else ""
    thesis_line = thesis or item.role
    note = f'<div class="hf-note">{escape(item.note)}</div>' if item.note else ""
    pe_label = "PE分位" if item.kind == "股票" else "估值口径"
    pe_value = _fmt_pct(pe_pct) if item.kind == "股票" else "ETF不适用"
    weight_value = _fmt_pct(target_weight) if target_weight is not None else "待设定"
    if row is not None and shares is None:
        actual_value = "未录入数量"
    else:
        actual_value = _fmt_pct(actual_weight) if actual_weight is not None else "待录入"
    data_note = str(market.get("data_note") or "未接入行情")
    ledger_value = "未录入数量" if row is not None and shares is None else _fmt_money(market_value)
    price_band = _price_band_html(row)
    position_band = _position_band_html(row)

    return f"""
    <div class="hf-card">
      <div class="hf-card-top">
        <div>
          <div class="hf-kind">{escape(item.kind)} · {escape(item.sleeve)}</div>
          <div class="hf-name">{escape(item.name)} <span>{escape(item.ticker)}</span></div>
        </div>
        <div class="hf-status" style="background:{bg};color:{fg};">{escape(label)}</div>
      </div>
      <div class="hf-thesis">{escape(thesis_line)}</div>
      <div class="hf-metrics">
        <div><span>最新价</span><b>{escape(_fmt_price(last_price))}</b></div>
        <div><span>{escape(pe_label)}</span><b>{escape(pe_value)}</b></div>
        <div><span>目标权重</span><b>{escape(weight_value)}</b></div>
        <div><span>实际权重</span><b>{escape(actual_value)}</b></div>
      </div>
      <div class="hf-question">
        <span>决策问题</span>
        <p>{escape(item.decision_question)}</p>
      </div>
      <div class="hf-bands">
        {price_band}
        {position_band}
      </div>
      <div class="hf-bottom">
        <div><span>复盘重点</span><p>{escape(item.review_focus)}</p></div>
        <div><span>当前动作</span><p>{escape(item.default_action)}</p></div>
      </div>
      <div class="hf-ledger">账本市值: {escape(ledger_value)} · {escape(data_note)}</div>
      {note}
    </div>
    """


def _inject_css() -> None:
    st.html(
        """
        <style>
          .holding-focus-wrap {
            font-family: var(--preson-font-sans, -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif);
          }
          .hf-hero {
            background:#FFFFFF;
            border:1px solid #E5E7EB;
            border-left:4px solid #111827;
            border-radius:8px;
            padding:14px 16px;
            margin:4px 0 12px;
          }
          .hf-hero h3 {
            font-family: var(--preson-font-report, "Songti SC", "STSong", serif);
            font-size:22px;
            line-height:1.2;
            margin:0 0 6px;
            color:#111827;
          }
          .hf-hero p {
            margin:0;
            color:#667085;
            font-size:13px;
            line-height:1.55;
          }
          .hf-grid {
            display:grid;
            grid-template-columns:repeat(2,minmax(0,1fr));
            gap:12px;
            margin-top:10px;
          }
          .hf-card {
            background:#FFFFFF;
            border:1px solid #E5E7EB;
            border-radius:8px;
            padding:13px 14px 12px;
            min-height:250px;
          }
          .hf-card-top {
            display:flex;
            justify-content:space-between;
            gap:12px;
            align-items:flex-start;
          }
          .hf-kind {
            color:#667085;
            font-size:11px;
            font-weight:650;
            margin-bottom:5px;
          }
          .hf-name {
            font-family: var(--preson-font-report, "Songti SC", "STSong", serif);
            color:#111827;
            font-size:20px;
            line-height:1.2;
            font-weight:700;
          }
          .hf-name span {
            font-family:var(--preson-font-number, "Helvetica Neue", Arial, sans-serif);
            color:#667085;
            font-size:12px;
            font-weight:500;
            margin-left:6px;
          }
          .hf-status {
            border-radius:999px;
            padding:5px 9px;
            font-size:12px;
            font-weight:700;
            white-space:nowrap;
          }
          .hf-thesis {
            color:#344054;
            font-size:13px;
            line-height:1.45;
            margin-top:10px;
            min-height:38px;
          }
          .hf-metrics {
            display:grid;
            grid-template-columns:repeat(4,minmax(0,1fr));
            gap:6px;
            margin-top:10px;
          }
          .hf-metrics div {
            background:#F8FAFC;
            border:1px solid #EEF2F7;
            border-radius:7px;
            padding:7px 8px;
          }
          .hf-metrics span,
          .hf-question span,
          .hf-bottom span {
            display:block;
            color:#667085;
            font-size:11px;
            font-weight:650;
            margin-bottom:4px;
          }
          .hf-metrics b {
            color:#111827;
            font-family:var(--preson-font-number, "Helvetica Neue", Arial, sans-serif);
            font-size:14px;
            font-weight:500;
          }
          .hf-question {
            border-top:1px solid #EEF2F7;
            margin-top:11px;
            padding-top:10px;
          }
          .hf-question p {
            color:#111827;
            font-size:14px;
            line-height:1.45;
            margin:0;
            font-weight:650;
          }
          .hf-bands {
            display:grid;
            grid-template-columns:1fr;
            gap:7px;
            margin-top:10px;
          }
          .hf-band {
            background:#FFFBEB;
            border:1px solid #FDE68A;
            border-radius:7px;
            padding:7px 8px;
          }
          .hf-band-muted {
            background:#F8FAFC;
            border-color:#EEF2F7;
          }
          .hf-band span {
            display:block;
            color:#92400E;
            font-size:11px;
            font-weight:700;
            margin-bottom:3px;
          }
          .hf-band-muted span {
            color:#667085;
          }
          .hf-band p {
            color:#111827;
            font-size:12px;
            line-height:1.35;
            margin:0;
            font-weight:650;
          }
          .hf-band-muted p {
            color:#667085;
            font-weight:500;
          }
          .hf-bottom {
            display:grid;
            grid-template-columns:1.45fr .72fr;
            gap:10px;
            margin-top:10px;
          }
          .hf-bottom p {
            color:#344054;
            font-size:12px;
            line-height:1.45;
            margin:0;
          }
          .hf-ledger,
          .hf-note {
            color:#98A2B3;
            font-size:11px;
            margin-top:9px;
          }
          @media (max-width: 900px) {
            .hf-grid { grid-template-columns:1fr; }
            .hf-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); }
          }
        </style>
        """
    )


def render(snap: Any) -> None:
    _inject_css()
    by_ticker = _snap_row_by_ticker(snap)
    tickers = tuple(item.ticker for item in FOCUS_HOLDINGS)
    market_info = _latest_market_info(tickers)
    in_ledger = sum(1 for item in FOCUS_HOLDINGS if item.ticker in by_ticker)

    st.html(
        f"""
        <div class="holding-focus-wrap">
          <div class="hf-hero">
            <h3>我的持仓视角</h3>
            <p>当前按你确认的 {len(FOCUS_HOLDINGS)} 个标的聚焦复盘：股票负责公司判断，ETF 负责行业 / 资产配置判断。
            已在账本中识别 {in_ledger} / {len(FOCUS_HOLDINGS)} 个；未识别的不影响本视角展示，后续可再补金额和权重。</p>
          </div>
        </div>
        """
    )

    stock_count = sum(1 for item in FOCUS_HOLDINGS if item.kind == "股票")
    etf_count = len(FOCUS_HOLDINGS) - stock_count
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("聚焦标的", f"{len(FOCUS_HOLDINGS)} 个")
    c2.metric("股票", f"{stock_count} 个")
    c3.metric("ETF", f"{etf_count} 个")
    c4.metric("账本识别", f"{in_ledger} 个")

    mode = st.radio(
        "显示范围",
        ["全部", "股票", "ETF", "待录入账本"],
        horizontal=True,
        label_visibility="collapsed",
        key="holding_focus_filter",
    )
    items = list(FOCUS_HOLDINGS)
    if mode == "股票":
        items = [item for item in items if item.kind == "股票"]
    elif mode == "ETF":
        items = [item for item in items if item.kind == "ETF"]
    elif mode == "待录入账本":
        items = [item for item in items if item.ticker not in by_ticker]

    cards = [
        _card_html(item, by_ticker.get(item.ticker), market_info.get(item.ticker, {}))
        for item in items
    ]
    st.html(
        '<div class="holding-focus-wrap"><div class="hf-grid">'
        + "".join(cards)
        + "</div></div>"
    )

    st.caption(
        "下一步建议：先确认 ETF 代码和每个标的目标权重，再把“待录入账本”的标的写入 portfolio。"
    )


__all__ = ["FOCUS_HOLDINGS", "render"]
