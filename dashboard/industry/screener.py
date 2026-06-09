"""industry_screener · 行业级 Top N 选优引擎(候选 ⑪ 重启 / E4)。

接口契约:README.md H

数据池三级降级:
  Path 1. data/market.duckdb · market_spot(全市场快照 ~5400 行)
          - 字段:ticker / name / industry_em / total_market_cap / pe / pb / snapshot_date
          - 启用 market_cap_min 过滤
  Path 2. data/peers.duckdb · peers + self_metrics(同行池 ~80 家)
          - peers:    ticker / peer_ticker / peer_name / peer_pe / peer_pb / peer_market_cap / industry_em
          - self_metrics: ticker / name / industry_em / market_cap / pe / pb
  Path 3. .config/companies.csv 自选(industry_l2 == industry,15 家覆盖)

评分链路:
  · industry_type_map.yaml 拿 type → primary/secondary masters + weights
  · type ∈ {stalwart/fast_grower/cyclical/slow_grower}:
      primary  → score_lynch_classifier_all(lynch_classifier 自动 6 类)
      secondary → score_with_master(df, m)
  · type ∈ {bank/insurance}:
      不能用 lynch_classifier(银行保险特殊会抛错);
      primary  → score_with_master(df, "graham_bank" / "graham_insurance")
      secondary → score_with_master(df, "piotroski_bank" / "piotroski_insurance")
  · 加权:从 industry_type_map.yaml 读 weights;数据缺失项不计入,剩余项按权重归一化

复用 .tools/dashboard/screener.py 的:
  - score_with_master(df, master_id, year=None) -> df + score/max_score/rating/...
  - score_lynch_classifier_all(df) -> df + score/rating/lynch_type/...

性能:
  · 8 行业 × 平均 10 候选 × 1-3 master ≈ 100-300 次评分,首次 ~30s
  · lynch_classifier 慢(~3-5s/家),首次跑全聚焦最长可能 1 分钟+
  · 引擎层不缓存(留给 UI @st.cache_data)

边界保护:
  · 任何评分异常 → score=NaN, rating="⚪ 数据不足",不阻断其他公司
  · 候选池为空 → 返回空 DataFrame(列结构保留)
  · companies.csv 自选 1 家时 → data_source="self_only"(member_count=1)
"""
from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import duckdb
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FOCUS_YAML = PROJECT_ROOT / ".config" / "focus_industries.yaml"
TYPE_MAP_YAML = PROJECT_ROOT / ".tools" / "rules" / "industry_type_map.yaml"
COMPANIES_CSV = PROJECT_ROOT / ".config" / "companies.csv"
MARKET_DB = PROJECT_ROOT / "data" / "market.duckdb"
PEERS_DB = PROJECT_ROOT / "data" / "peers.duckdb"

# 让 screener 模块可被导入(本模块跟 screener.py 同目录,但走 import 也兼容)
_DASH_DIR = str(Path(__file__).resolve().parent)
if _DASH_DIR not in sys.path:
    sys.path.insert(0, _DASH_DIR)

from screening.screener import score_with_master, score_lynch_classifier_all  # noqa: E402

# ─── 数据类 ──────────────────────────────────────────────────────────────


@dataclass
class IndustryCandidate:
    """单家公司在某行业内的评分结果(F2 Tab UI 直接消费)。"""
    ticker: str
    name: str
    score: Optional[float]
    rating: str               # 🟢/🟡/🟠/🔴/⚪
    reason: str               # 一句话理由
    is_owned: bool            # 是否在 .config/companies.csv 自选
    primary_master: str       # 主评分大师 id(lynch / graham_bank / ...)
    breakdown: dict = field(default_factory=dict)  # {master_id: score_0_100}


# ─── yaml 加载 ───────────────────────────────────────────────────────────


def _load_focus_yaml(path: str | Path = FOCUS_YAML) -> dict:
    p = Path(path)
    if not p.exists():
        return {"focus": [], "top_n": 7, "market_cap_min": 5_000_000_000}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _load_type_map(path: str | Path = TYPE_MAP_YAML) -> dict:
    p = Path(path)
    if not p.exists():
        return {"type_to_scoring": {}}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _load_companies_csv() -> pd.DataFrame:
    """读 .config/companies.csv → DataFrame(stock/name/industry_l2/category)。"""
    if not COMPANIES_CSV.exists():
        return pd.DataFrame(columns=["stock", "name", "industry_l2", "category"])
    rows: list[dict] = []
    with COMPANIES_CSV.open() as f:
        for r in csv.DictReader(f):
            rows.append(r)
    df = pd.DataFrame(rows)
    if not df.empty and "stock" in df.columns:
        df["stock"] = df["stock"].astype(str).str.zfill(6)
    return df


def _self_tickers_for_industry(industry: str) -> set[str]:
    """自选 ticker 集合(用于 is_owned 标注)。"""
    df = _load_companies_csv()
    if df.empty or "industry_l2" not in df.columns:
        return set()
    return set(df.loc[df["industry_l2"] == industry, "stock"].astype(str).tolist())


# ─── 候选池:三级降级 ────────────────────────────────────────────────────


def list_industry_candidates(industry: str,
                             market_cap_min: float = 5_000_000_000) -> list[dict]:
    """返回行业候选公司列表 [{ticker, name, market_cap?, data_source}]。

    数据源标注:
      - "market.duckdb"  全市场快照(~5400 行)
      - "peers.duckdb"   同行池(~80 家)
      - "self_only"      仅 companies.csv 自选(降级兜底)

    market_cap_min 仅在数据源含 total_market_cap 字段时启用过滤;
    peers/self_only 阶段若 market_cap 字段缺失,跳过过滤(避免误删)。
    """
    self_tickers = _self_tickers_for_industry(industry)

    # Path 1 · market.duckdb
    pool = _candidates_from_market_db(industry, market_cap_min)
    if pool:
        # 自选公司若不在 market_spot 池中,补回(避免漏掉)
        existing = {c["ticker"] for c in pool}
        for t in self_tickers - existing:
            n = _name_for_ticker(t) or t
            pool.append({"ticker": t, "name": n,
                         "market_cap": None, "data_source": "self_only"})
        return pool

    # Path 2 · peers.duckdb
    pool = _candidates_from_peers_db(industry, self_tickers)
    if pool:
        existing = {c["ticker"] for c in pool}
        for t in self_tickers - existing:
            n = _name_for_ticker(t) or t
            pool.append({"ticker": t, "name": n,
                         "market_cap": None, "data_source": "self_only"})
        return pool

    # Path 3 · companies.csv 自选
    return _candidates_from_companies_csv(industry)


def _name_for_ticker(ticker: str) -> Optional[str]:
    df = _load_companies_csv()
    if df.empty:
        return None
    sub = df[df["stock"] == ticker]
    if sub.empty:
        return None
    return str(sub.iloc[0].get("name", "")) or None


def _candidates_from_market_db(industry: str,
                               market_cap_min: float) -> list[dict]:
    if not MARKET_DB.exists():
        return []
    try:
        con = duckdb.connect(str(MARKET_DB), read_only=True)
    except Exception:
        return []
    try:
        # 表存在性 + 非空检查
        t_exists = con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name='market_spot'"
        ).fetchone()
        if not t_exists or t_exists[0] == 0:
            return []
        cnt = con.execute("SELECT count(*) FROM market_spot").fetchone()[0]
        if cnt == 0:
            return []
        # 最新快照日 + 行业模糊匹配 + 市值过滤
        q = """
            WITH last AS (SELECT max(snapshot_date) AS d FROM market_spot)
            SELECT ticker, name, total_market_cap
            FROM market_spot, last
            WHERE snapshot_date = last.d
              AND (industry_em = ? OR industry_em LIKE ?)
              AND (total_market_cap IS NULL OR total_market_cap >= ?)
            ORDER BY total_market_cap DESC NULLS LAST
        """
        df = con.execute(q, [industry, f"%{industry}%", market_cap_min]).df()
    except Exception:
        df = pd.DataFrame()
    finally:
        con.close()

    if df.empty:
        return []
    return [
        {
            "ticker": str(r["ticker"]).zfill(6),
            "name": str(r.get("name") or ""),
            "market_cap": (None if pd.isna(r.get("total_market_cap"))
                           else float(r["total_market_cap"])),
            "data_source": "market.duckdb",
        }
        for _, r in df.iterrows()
    ]


def _candidates_from_peers_db(industry: str,
                              self_tickers: set[str]) -> list[dict]:
    """从 peers.duckdb 拉同 industry_em 的 self+peer 池。

    industry_em 解析:先用 self_tickers 反查,失败时直接用 SW L2 名匹配
    (多数行业名 SW 与 EM 重合,如「白酒」「保险」)。
    """
    if not PEERS_DB.exists():
        return []
    try:
        con = duckdb.connect(str(PEERS_DB), read_only=True)
    except Exception:
        return []
    try:
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        if "peers" not in tables:
            return []

        industry_em: Optional[str] = None
        if self_tickers:
            placeholders = ",".join(["?"] * len(self_tickers))
            row = con.execute(
                f"""
                SELECT industry_em FROM peers
                WHERE ticker IN ({placeholders}) AND industry_em IS NOT NULL
                LIMIT 1
                """,
                list(self_tickers),
            ).fetchone()
            if row and row[0]:
                industry_em = row[0]
        if not industry_em:
            row = con.execute(
                """
                SELECT industry_em FROM peers
                WHERE industry_em = ? OR industry_em LIKE ?
                LIMIT 1
                """,
                [industry, f"%{industry}%"],
            ).fetchone()
            if row and row[0]:
                industry_em = row[0]
        if not industry_em:
            return []

        # peer 池 unique
        peer_df = con.execute(
            """
            SELECT DISTINCT peer_ticker AS ticker, peer_name AS name,
                            peer_market_cap AS market_cap
            FROM peers
            WHERE industry_em = ? AND peer_ticker IS NOT NULL
            """,
            [industry_em],
        ).df()
        # self 也加进来
        self_df = pd.DataFrame()
        if "self_metrics" in tables:
            try:
                self_df = con.execute(
                    """
                    SELECT ticker, name, market_cap FROM self_metrics
                    WHERE industry_em = ?
                    """,
                    [industry_em],
                ).df()
            except Exception:
                self_df = pd.DataFrame()
    except Exception:
        return []
    finally:
        con.close()

    parts = [d for d in [peer_df, self_df] if not d.empty]
    if not parts:
        return []
    pool = pd.concat(parts, ignore_index=True)
    pool = pool.dropna(subset=["ticker"]).drop_duplicates(
        subset=["ticker"], keep="first")

    return [
        {
            "ticker": str(r["ticker"]).zfill(6),
            "name": str(r.get("name") or ""),
            "market_cap": (None if pd.isna(r.get("market_cap"))
                           else float(r["market_cap"])),
            "data_source": "peers.duckdb",
        }
        for _, r in pool.iterrows()
    ]


def _candidates_from_companies_csv(industry: str) -> list[dict]:
    df = _load_companies_csv()
    if df.empty or "industry_l2" not in df.columns:
        return []
    sub = df[df["industry_l2"] == industry]
    return [
        {
            "ticker": str(r["stock"]).zfill(6),
            "name": str(r.get("name") or ""),
            "market_cap": None,
            "data_source": "self_only",
        }
        for _, r in sub.iterrows()
    ]


# ─── 单股评分 ────────────────────────────────────────────────────────────


# lynch primary 适用类型(走 score_lynch_classifier_all)
_LYNCH_PRIMARY_TYPES = {"stalwart", "fast_grower", "cyclical", "slow_grower"}
# bank/insurance 直接走对应大师 yaml(不能用 lynch_classifier)
_DIRECT_GRAHAM_PRIMARY = {
    "bank": "graham_bank",
    "insurance": "graham_insurance",
}


def _normalize_to_100(score: Any, max_score: Any) -> Optional[float]:
    """把 (score, max_score) 归一化到 0-100;NaN/None/0 max 时返回 None。"""
    if score is None or pd.isna(score):
        return None
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    if max_score is None or pd.isna(max_score) or float(max_score) <= 0:
        # 部分大师 max_score=None — 已是 0-100 量级时直接用,异常时丢弃
        if 0 <= s <= 100:
            return s
        return None
    m = float(max_score)
    if m == 100:
        return s
    return round(s / m * 100.0, 2)


def _master_score_for_ticker(ticker: str, name: str, master_id: str) -> Optional[float]:
    """单大师 yaml 评分,归一化到 0-100。失败返回 None。"""
    df1 = pd.DataFrame({"ticker": [ticker], "name": [name]})
    try:
        out = score_with_master(df1, master_id)
        if out.empty:
            return None
        return _normalize_to_100(out.iloc[0]["score"],
                                 out.iloc[0].get("max_score"))
    except Exception:
        return None


def _lynch_score_for_ticker(ticker: str, name: str) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """lynch_classifier 评分 → (score_0_100, lynch_type_cn, dim_top)。"""
    df1 = pd.DataFrame({"ticker": [ticker], "name": [name]})
    try:
        out = score_lynch_classifier_all(df1)
        if out.empty:
            return None, None, None
        s = out.iloc[0]["score"]
        s_norm = None if pd.isna(s) else float(s)
        return (s_norm,
                out.iloc[0].get("lynch_type_cn") or None,
                out.iloc[0].get("dim_top") or None)
    except Exception:
        return None, None, None


def _rating_from_score(score: Optional[float]) -> str:
    if score is None or pd.isna(score):
        return "⚪ 数据不足"
    if score >= 75:
        return "🟢 优秀"
    if score >= 60:
        return "🟡 合格"
    if score >= 45:
        return "🟠 警戒"
    return "🔴 不及格"


def _build_reason(breakdown: dict, primary_master: str,
                  lynch_type_cn: Optional[str] = None,
                  dim_top: Optional[str] = None) -> str:
    """从 breakdown 构造一句话理由。"""
    parts: list[str] = []
    if lynch_type_cn:
        parts.append(f"林奇·{lynch_type_cn}")
    if dim_top:
        parts.append(f"强项 {dim_top}")
    # 列出最高分大师 + 最低分大师(前 3 项)
    valid = {k: v for k, v in breakdown.items() if v is not None}
    if valid:
        top = max(valid.items(), key=lambda kv: kv[1])
        parts.append(f"{top[0]} {top[1]:.0f}")
        if len(valid) > 1:
            bot = min(valid.items(), key=lambda kv: kv[1])
            if bot[0] != top[0]:
                parts.append(f"{bot[0]} {bot[1]:.0f}")
    if not parts:
        parts.append(f"主评分:{primary_master}(数据不足)")
    return " / ".join(parts)


def score_company(ticker: str, scoring_type: str,
                  name: str = "",
                  type_map: Optional[dict] = None,
                  is_owned: bool = False) -> IndustryCandidate:
    """单股评分。

    Args:
      ticker:        股票代码(6 位)
      scoring_type:  6 类型之一
      name:          可选,公司中文名(打 reason 用)
      type_map:      可选,提前加载的 type_to_scoring dict(批量调用时传入避免重复 IO)
      is_owned:      该 ticker 是否在自选

    Returns:
      IndustryCandidate(score 0-100, breakdown 各 master 分数)
    """
    if type_map is None:
        type_map = (_load_type_map() or {}).get("type_to_scoring", {})
    cfg = type_map.get(scoring_type)
    if not cfg:
        return IndustryCandidate(
            ticker=ticker, name=name, score=None,
            rating="⚪ 数据不足",
            reason=f"未知评分类型: {scoring_type}",
            is_owned=is_owned, primary_master="",
            breakdown={},
        )

    primary = cfg.get("primary", "")
    secondary = cfg.get("secondary", []) or []
    weights: dict = cfg.get("weights", {}) or {}

    breakdown: dict = {}
    lynch_type_cn = None
    dim_top = None

    # 1) primary
    if scoring_type in _LYNCH_PRIMARY_TYPES and primary == "lynch":
        s, lynch_type_cn, dim_top = _lynch_score_for_ticker(ticker, name)
        breakdown["lynch"] = s
    else:
        # bank/insurance 直接走 yaml(graham_bank / graham_insurance)
        master_id = _DIRECT_GRAHAM_PRIMARY.get(scoring_type, primary)
        s = _master_score_for_ticker(ticker, name, master_id)
        breakdown[master_id] = s

    # 2) secondary
    for m in secondary:
        if m in breakdown:  # 避免重复
            continue
        breakdown[m] = _master_score_for_ticker(ticker, name, m)

    # 3) 加权(数据缺失项不计入 → 剩余权重归一化)
    valid_pairs = [(k, v) for k, v in breakdown.items()
                   if v is not None and not pd.isna(v) and k in weights]
    if valid_pairs:
        total_w = sum(weights[k] for k, _ in valid_pairs)
        if total_w > 0:
            final = sum(v * weights[k] for k, v in valid_pairs) / total_w
        else:
            final = None
    else:
        final = None

    primary_master_label = primary if primary == "lynch" else \
        _DIRECT_GRAHAM_PRIMARY.get(scoring_type, primary)

    return IndustryCandidate(
        ticker=ticker,
        name=name,
        score=(round(final, 2) if final is not None else None),
        rating=_rating_from_score(final),
        reason=_build_reason(breakdown, primary_master_label,
                             lynch_type_cn=lynch_type_cn, dim_top=dim_top),
        is_owned=is_owned,
        primary_master=primary_master_label,
        breakdown=breakdown,
    )


# ─── 行业级 Top N ────────────────────────────────────────────────────────


_OUT_COLS = [
    "rank", "ticker", "name", "score", "rating", "reason",
    "is_owned", "primary_master", "data_source",
]


def _empty_result_df() -> pd.DataFrame:
    return pd.DataFrame(columns=_OUT_COLS)


def screen_industry(industry: str, type: str,
                    top_n: int = 7,
                    market_cap_min: float = 5_000_000_000,
                    type_map: Optional[dict] = None) -> pd.DataFrame:
    """单行业 Top N 选优。

    返回固定列:rank / ticker / name / score / rating / reason
                / is_owned / primary_master / data_source

    Args:
      industry:        SW L2 行业名(必须与 industry_master.yaml.name 对齐)
      type:            林奇 6 类之一
      top_n:           取前 N 家
      market_cap_min:  市值下限(仅 market.duckdb 阶段启用)
      type_map:        预加载的 type_map(批量场景传入)
    """
    if type_map is None:
        type_map = (_load_type_map() or {}).get("type_to_scoring", {})

    cands = list_industry_candidates(industry, market_cap_min=market_cap_min)
    if not cands:
        return _empty_result_df()

    self_tickers = _self_tickers_for_industry(industry)

    rows: list[dict] = []
    for c in cands:
        ticker = c["ticker"]
        name = c.get("name", "")
        is_owned = ticker in self_tickers
        cand = score_company(ticker, type, name=name,
                             type_map=type_map, is_owned=is_owned)
        rows.append({
            "ticker": cand.ticker,
            "name": cand.name,
            "score": cand.score,
            "rating": cand.rating,
            "reason": cand.reason,
            "is_owned": cand.is_owned,
            "primary_master": cand.primary_master,
            "data_source": c.get("data_source", ""),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return _empty_result_df()

    # 排序:有效分数优先,自选公司同分时优先(便于 UI 高亮)
    df["_score_sort"] = df["score"].fillna(-1.0)
    df["_owned_sort"] = df["is_owned"].astype(int)
    df = df.sort_values(
        by=["_score_sort", "_owned_sort"], ascending=[False, False]
    ).head(top_n).reset_index(drop=True)
    df = df.drop(columns=["_score_sort", "_owned_sort"])
    df.insert(0, "rank", range(1, len(df) + 1))

    return df[_OUT_COLS]


def screen_all_focus(focus_yaml_path: str | Path = FOCUS_YAML
                     ) -> dict[str, pd.DataFrame]:
    """批量跑所有聚焦行业。

    Returns:
      {industry_name: DataFrame(...)} dict;
      若 yaml 缺失或 focus 为空,返回 {}。
    """
    cfg = _load_focus_yaml(focus_yaml_path)
    focus = cfg.get("focus", []) or []
    top_n = int(cfg.get("top_n", 7))
    market_cap_min = float(cfg.get("market_cap_min", 5_000_000_000))
    type_map = (_load_type_map() or {}).get("type_to_scoring", {})

    results: dict[str, pd.DataFrame] = {}
    for item in focus:
        industry = item.get("industry")
        type_ = item.get("type")
        if not industry or not type_:
            continue
        try:
            df = screen_industry(industry, type_,
                                 top_n=top_n,
                                 market_cap_min=market_cap_min,
                                 type_map=type_map)
        except Exception as e:  # 单行业异常不阻断其他行业
            df = _empty_result_df()
            df.attrs["error"] = str(e)
        results[industry] = df
    return results


__all__ = [
    "IndustryCandidate",
    "list_industry_candidates",
    "score_company",
    "screen_industry",
    "screen_all_focus",
]


# ─── CLI ─────────────────────────────────────────────────────────────────


def _cli() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="行业 Top N 选优(候选 ⑪)")
    ap.add_argument("--industry", default=None,
                    help="单行业测试(SW L2 名);省略则跑全聚焦")
    ap.add_argument("--type", default="stalwart",
                    help="林奇 6 类之一 (stalwart/fast_grower/cyclical/"
                         "slow_grower/bank/insurance)")
    ap.add_argument("--top-n", type=int, default=7)
    args = ap.parse_args()

    if args.industry:
        df = screen_industry(args.industry, args.type, top_n=args.top_n)
        print(f"\n=== {args.industry} Top {args.top_n} ({args.type}) ===")
        if df.empty:
            print("(空 — 无候选)")
        else:
            print(df.to_string(index=False))
    else:
        results = screen_all_focus()
        print(f"\n=== 全聚焦 {len(results)} 行业 ===")
        for ind, df in results.items():
            print(f"\n--- {ind} ({len(df)} 家) ---")
            if df.empty:
                print("(空)")
            else:
                print(df[["rank", "ticker", "name", "score", "rating",
                          "reason"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
