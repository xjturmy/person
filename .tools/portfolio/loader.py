"""portfolio.yaml 加载器与查询 API。

任何模块需要持仓信息时:
    from portfolio.loader import load_portfolio
    p = load_portfolio()
    p.holdings        # list[Holding]
    p.active()        # 仅 status=active
    p.weight_of("600519")
    p.deviation_of("600519")
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator

import yaml

ROOT = Path(__file__).resolve().parents[2]
# v2.8+ 持仓数据源切到 .config/portfolio.yaml(positions 已 merge 进 holdings).
# 旧 .tools/portfolio/portfolio.yaml 已 rename 为 .deprecated。
DEFAULT_YAML = ROOT / ".config" / "portfolio.yaml"


@dataclass
class Holding:
    ticker: str
    name: str
    status: str = "watch"           # active / watch / exited
    shares: float | None = None
    cost_basis: float | None = None
    last_price: float | None = None
    first_buy_date: str | None = None
    target_weight: float = 0.0
    max_weight: float = 0.0
    thesis: str = ""
    tags: list[str] = field(default_factory=list)

    # —— v2.8+ positions section 字段合并(从 .config/portfolio.yaml.positions[] 迁移过来) ——
    school: str = ""                                      # 价值 / 成长 / 周期 / 防御
    rationale: str = ""                                   # 买入逻辑 60-120 字
    criteria_met: list[str] = field(default_factory=list)
    review_triggers: list[str] = field(default_factory=list)

    # —— v2.7+ 持仓详情扩展字段(全部可选) ——
    buy_rationale: str = ""
    buy_criteria_met: list[str] = field(default_factory=list)
    sell_rationale: str = ""
    exit_triggers: list[str] = field(default_factory=list)
    price_band: dict = field(default_factory=dict)
    position_band: dict = field(default_factory=dict)
    short_term_signals: dict = field(default_factory=dict)
    exit_date: str | None = None
    exit_price: float | None = None
    closed_at: str | None = None
    closed_reason: str = ""

    @property
    def cost_total(self) -> float | None:
        if self.shares is None or self.cost_basis is None:
            return None
        return self.shares * self.cost_basis


@dataclass
class Account:
    total_capital: float = 0.0
    target_equity_ratio: float = 0.7
    cash_min_ratio: float = 0.10
    cash_max_ratio: float = 0.50


@dataclass
class RebalanceRules:
    max_position_weight: float = 0.20
    max_deviation_pct: float = 0.05
    score_floor: int = 4
    valuation_ceiling_pct: float = 0.85
    valuation_floor_pct: float = 0.15
    review_cadence_days: int = 30


@dataclass
class Portfolio:
    status: str
    last_updated: str
    account: Account
    rebalance: RebalanceRules
    holdings: list[Holding]
    exited: list[Holding] = field(default_factory=list)
    benchmarks: list[dict] = field(default_factory=list)

    def active(self) -> list[Holding]:
        return [h for h in self.holdings if h.status == "active"]

    def watch(self) -> list[Holding]:
        return [h for h in self.holdings if h.status == "watch"]

    def by_ticker(self, ticker: str) -> Holding | None:
        for h in self.holdings:
            if h.ticker == ticker:
                return h
        return None

    def total_market_value(self, prices: dict[str, float] | None = None) -> float:
        """active 持仓的当前市值。prices 缺失时用 cost_basis 兜底。"""
        total = 0.0
        for h in self.active():
            if h.shares is None:
                continue
            px = (prices or {}).get(h.ticker) or h.cost_basis or 0.0
            total += h.shares * px
        return total

    def actual_weights(self, prices: dict[str, float] | None = None) -> dict[str, float]:
        """active 持仓的实际权重(分母为持仓市值合计,不含现金)。"""
        mv = self.total_market_value(prices)
        if mv <= 0:
            return {}
        result = {}
        for h in self.active():
            if h.shares is None:
                continue
            px = (prices or {}).get(h.ticker) or h.cost_basis or 0.0
            result[h.ticker] = h.shares * px / mv
        return result

    def deviations(self, prices: dict[str, float] | None = None) -> dict[str, float]:
        """实际权重 - 目标权重(正=超配,负=低配),仅 active。"""
        actual = self.actual_weights(prices)
        return {h.ticker: actual.get(h.ticker, 0.0) - h.target_weight for h in self.active()}

    def rebalance_alerts(
        self,
        prices: dict[str, float] | None = None,
        scores: dict[str, int] | None = None,
        valuation_pct: dict[str, float] | None = None,
    ) -> list[str]:
        """根据 rebalance 规则生成提示清单。任一字典缺失则跳过对应检查。"""
        alerts: list[str] = []
        actual = self.actual_weights(prices)

        # 单仓上限
        for ticker, w in actual.items():
            if w > self.rebalance.max_position_weight:
                alerts.append(f"⚠️  {ticker} 实际权重 {w:.1%} 超单仓上限 {self.rebalance.max_position_weight:.0%}")

        # 偏离阈值
        for ticker, dev in self.deviations(prices).items():
            if abs(dev) > self.rebalance.max_deviation_pct:
                direction = "超配" if dev > 0 else "低配"
                alerts.append(f"📊 {ticker} {direction} {abs(dev):.1%}(偏离阈值 {self.rebalance.max_deviation_pct:.0%})")

        # 评分跌破
        if scores:
            for h in self.active():
                s = scores.get(h.ticker)
                if s is not None and s < self.rebalance.score_floor:
                    alerts.append(f"🔴 {h.ticker} {h.name} F-Score {s} < 阈值 {self.rebalance.score_floor},触发清仓评估")

        # 估值分位高/低
        if valuation_pct:
            for h in self.active():
                pct = valuation_pct.get(h.ticker)
                if pct is None:
                    continue
                if pct > self.rebalance.valuation_ceiling_pct:
                    alerts.append(f"🔥 {h.ticker} PE-TTM 分位 {pct:.1%} > {self.rebalance.valuation_ceiling_pct:.0%},触发减仓评估")
                elif pct < self.rebalance.valuation_floor_pct:
                    alerts.append(f"💰 {h.ticker} PE-TTM 分位 {pct:.1%} < {self.rebalance.valuation_floor_pct:.0%},触发加仓评估")

        return alerts

    def __iter__(self) -> Iterator[Holding]:
        return iter(self.holdings)


def load_portfolio(path: Path | None = None) -> Portfolio:
    p = path or DEFAULT_YAML
    if not p.exists():
        raise FileNotFoundError(f"portfolio.yaml 不存在: {p}")

    doc = yaml.safe_load(p.read_text(encoding="utf-8"))

    meta = doc.get("_meta", {})
    account = Account(**(doc.get("account") or {}))
    rebalance = RebalanceRules(**(doc.get("rebalance") or {}))

    def parse_holding(d: dict) -> Holding:
        return Holding(
            ticker=str(d["ticker"]),
            name=d.get("name", ""),
            status=d.get("status", "watch"),
            shares=d.get("shares"),
            cost_basis=d.get("cost_basis"),
            last_price=d.get("last_price"),
            first_buy_date=d.get("first_buy_date"),
            target_weight=d.get("target_weight", 0.0),
            max_weight=d.get("max_weight", 0.0),
            thesis=d.get("thesis", ""),
            tags=d.get("tags") or [],
            school=d.get("school", "") or "",
            rationale=d.get("rationale", "") or "",
            criteria_met=d.get("criteria_met") or [],
            review_triggers=d.get("review_triggers") or [],
            buy_rationale=d.get("buy_rationale", "") or "",
            buy_criteria_met=d.get("buy_criteria_met") or [],
            sell_rationale=d.get("sell_rationale", "") or "",
            exit_triggers=d.get("exit_triggers") or [],
            price_band=d.get("price_band") or {},
            position_band=d.get("position_band") or {},
            short_term_signals=d.get("short_term_signals") or {},
            exit_date=d.get("exit_date"),
            exit_price=d.get("exit_price"),
            closed_at=d.get("closed_at"),
            closed_reason=d.get("closed_reason", "") or "",
        )

    holdings = [parse_holding(h) for h in (doc.get("holdings") or [])]
    exited = [parse_holding(h) for h in (doc.get("exited") or [])]

    return Portfolio(
        status=meta.get("status", "demo"),
        last_updated=meta.get("last_updated", ""),
        account=account,
        rebalance=rebalance,
        holdings=holdings,
        exited=exited,
        benchmarks=doc.get("benchmarks") or [],
    )


# ─── 写回(M4) ───────────────────────────────────────────────────────
def _backup_yaml(path: Path) -> Path | None:
    """写入前备份。返回备份路径(若原文件不存在则返回 None)."""
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = path.with_suffix(path.suffix + f".bak.{ts}")
    shutil.copy2(path, bak)
    return bak


def save_portfolio(
    doc: dict,
    path: Path | None = None,
    backup: bool = True,
) -> Path | None:
    """把 dict 写回 portfolio.yaml,先备份。返回备份路径。

    doc 应包含 _meta / account / rebalance / holdings / exited / benchmarks 顶层键。
    保留中文 + 注释丢失(yaml.safe_dump 不能保留注释,这是已知妥协)。
    """
    p = path or DEFAULT_YAML
    bak_path = _backup_yaml(p) if backup else None

    p.write_text(
        yaml.safe_dump(
            doc,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )
    return bak_path


def load_yaml_dict(path: Path | None = None) -> dict:
    """读原始 dict(不解析为 dataclass),用于增量修改。"""
    p = path or DEFAULT_YAML
    if not p.exists():
        return {
            "_meta": {"version": "1.0", "status": "demo", "base_currency": "CNY"},
            "account": {}, "rebalance": {}, "holdings": [], "exited": [],
        }
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def upsert_holdings(
    new_rows: list[dict],
    path: Path | None = None,
    backup: bool = True,
) -> tuple[Path | None, dict]:
    """把 new_rows 合并进 portfolio.yaml.holdings,已有 ticker → 更新,新 ticker → 追加。

    new_rows 每条字段:
        ticker (str, 必填)
        name (str)
        shares (float)
        cost_basis (float)
        last_price (float, optional)
        first_buy_date (str, optional)
        target_weight (float, optional, 默认 0)
        max_weight (float, optional)
        thesis (str, optional)
        tags (list[str], optional)
        status (str, optional, 默认 active)

    返回 (备份路径, 更新统计 {added: int, updated: int, status_flipped: bool})
    """
    doc = load_yaml_dict(path)
    holdings = doc.setdefault("holdings", []) or []
    by_ticker = {str(h.get("ticker")): h for h in holdings}

    added = 0
    updated = 0
    for row in new_rows:
        t = str(row.get("ticker", "")).strip()
        if not t:
            continue
        existing = by_ticker.get(t)
        if existing:
            for k, v in row.items():
                if v is None or v == "":
                    continue
                existing[k] = v
            updated += 1
        else:
            new = {"ticker": t, "status": row.get("status", "active")}
            for k in ("name", "shares", "cost_basis", "last_price", "first_buy_date",
                     "target_weight", "max_weight", "thesis", "tags"):
                v = row.get(k)
                if v is not None and v != "":
                    new[k] = v
            holdings.append(new)
            by_ticker[t] = new
            added += 1

    # status: demo → live(首次写入 active)
    meta = doc.setdefault("_meta", {})
    status_flipped = False
    if meta.get("status") == "demo" and any(
        h.get("status") == "active" and h.get("shares") for h in holdings
    ):
        meta["status"] = "live"
        status_flipped = True

    meta["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    doc["holdings"] = holdings

    bak = save_portfolio(doc, path=path, backup=backup)
    return bak, {"added": added, "updated": updated, "status_flipped": status_flipped}


# ─── v2.7+ 软删 / 硬删 / 详情更新 ─────────────────────────────────
def close_holding(
    ticker: str,
    reason: str = "",
    exit_price: float | None = None,
    sell_rationale: str = "",
    exit_triggers: list[str] | None = None,
    path: Path | None = None,
    backup: bool = True,
) -> tuple[Path | None, bool]:
    """软删 — status=exited + 写卖出归档字段(exit_date/exit_price/sell_rationale/exit_triggers).

    holdings_view.build_snapshot 只装配 active+watch,exited 立即从持仓总览消失,
    yaml 保留供复盘。返回 (备份路径, 是否命中)。
    """
    doc = load_yaml_dict(path)
    holdings = doc.get("holdings") or []
    hit = False
    today = datetime.now().strftime("%Y-%m-%d")
    for h in holdings:
        if str(h.get("ticker", "")).strip() == str(ticker).strip():
            h["status"] = "exited"
            h["closed_at"] = today
            h["exit_date"] = today
            if reason:
                h["closed_reason"] = reason
            if sell_rationale:
                h["sell_rationale"] = sell_rationale
            if exit_price is not None:
                h["exit_price"] = float(exit_price)
            if exit_triggers:
                h["exit_triggers"] = list(exit_triggers)
            hit = True
            break
    if not hit:
        return None, False
    doc.setdefault("_meta", {})["last_updated"] = today
    doc["holdings"] = holdings
    bak = save_portfolio(doc, path=path, backup=backup)
    return bak, True


def delete_holding(
    ticker: str,
    path: Path | None = None,
    backup: bool = True,
) -> tuple[Path | None, bool]:
    """硬删 — 从 holdings 列表彻底移除指定 ticker。返回 (备份路径, 是否命中)。"""
    doc = load_yaml_dict(path)
    holdings = doc.get("holdings") or []
    before = len(holdings)
    holdings = [h for h in holdings if str(h.get("ticker", "")).strip() != str(ticker).strip()]
    if len(holdings) == before:
        return None, False
    doc["holdings"] = holdings
    doc.setdefault("_meta", {})["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    bak = save_portfolio(doc, path=path, backup=backup)
    return bak, True


def update_holding_details(
    ticker: str,
    updates: dict,
    path: Path | None = None,
    backup: bool = True,
) -> tuple[Path | None, bool]:
    """更新指定 ticker 的持仓详情字段(支持 v2.7+ 扩展字段)。空值忽略。"""
    doc = load_yaml_dict(path)
    holdings = doc.get("holdings") or []
    hit = False
    for h in holdings:
        if str(h.get("ticker", "")).strip() == str(ticker).strip():
            for k, v in updates.items():
                if v is None:
                    continue
                if isinstance(v, str) and not v.strip():
                    continue
                if isinstance(v, (list, dict)) and len(v) == 0:
                    continue
                h[k] = v
            hit = True
            break
    if not hit:
        return None, False
    doc.setdefault("_meta", {})["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    doc["holdings"] = holdings
    bak = save_portfolio(doc, path=path, backup=backup)
    return bak, True
