"""dash-02 筛选引擎(纯数据层,不依赖 streamlit)。

API:
  load_all(db_path)                            -> pd.DataFrame  (15 家 × 全指标 + F-Score)
  apply_filters(df, filters)                   -> pd.DataFrame  按一组 {metric, op, value} 过滤
  apply_preset(df, preset_id)                  -> pd.DataFrame  应用 presets.yaml 中的预设
  load_presets(yaml_path)                      -> dict          {presets: [...], metrics: {...}}
  load_prelim_presets(yaml_path)               -> list[dict]    初步筛选硬过滤预设
  load_master_rules(master_id)                 -> dict          读 .tools/rules/{master_id}.yaml
  score_with_master(df, master_id, year)       -> pd.DataFrame  追加 score / max_score / rating / valid_rules / total_rules
  format_rating(score, thresholds, valid)      -> str           emoji 评级

CLI:
  .venv/bin/python .tools/dashboard/screener.py                      # 跑全 15 家全指标
  .venv/bin/python .tools/dashboard/screener.py --preset buffett     # 旧硬过滤
  .venv/bin/python .tools/dashboard/screener.py --master graham      # 新大师评分(graham/buffett/lynch)
"""
from __future__ import annotations

import argparse
import functools
import sys
from datetime import date, timedelta
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[3]
DB_PATH = ROOT / "data" / "preson.duckdb"
PRESETS_PATH = ROOT / ".tools" / "dashboard" / "presets.yaml"
SCORE_DIR = ROOT / ".tools" / "score"
RULES_DIR = ROOT / ".tools" / "rules"

# ─── 指标 → DuckDB (table, metric_name) 映射 ───────────────────────────
# 估值口径(.config/数据更新规则.md):PE/PB 用扣非主,GAAP 备 — 见下方 _latest_with_fallback
METRIC_SOURCE: dict[str, tuple[str, str]] = {
    "pe":             ("valuation",     "PE-TTM(扣非)"),    # 主用扣非
    "pb":             ("valuation",     "PB(不含商誉)"),    # 主用不含商誉
    "dividend_yield": ("valuation",     "股息率"),
    "roe":            ("profitability", "净资产收益率(ROE)"),
    "gm":             ("profitability", "毛利率(GM)"),
    "rev_yoy":        ("growth",        "累积同比"),
    "cfo_to_ni":      ("cashflow",      "经营活动产生的现金流量净额对净利润的比率"),
    "debt_ratio":     ("safety",        "资产负债率"),
}

# fallback 映射(主字段 → 备用字段);仅用于 valuation 表
METRIC_FALLBACK: dict[str, str] = {
    "PE-TTM(扣非)":   "PE-TTM",
    "PB(不含商誉)":   "PB",
}


def load_presets(path: Path | str = PRESETS_PATH) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_prelim_presets(path: Path | str = PRESETS_PATH) -> list[dict]:
    """初步筛选专用预设(仅硬过滤,无大师评分)。"""
    cfg = load_presets(path)
    return list(cfg.get("prelim_presets") or [])


def _conn(db_path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True)


def _latest(con, table: str, ticker: str, metric: str) -> float | None:
    """读最新值;若主字段缺且配置了 fallback,自动用备用字段(.config/数据更新规则.md)。"""
    row = con.execute(
        f"SELECT value FROM {table} "
        f"WHERE ticker = ? AND metric = ? AND value IS NOT NULL "
        f"ORDER BY date DESC LIMIT 1",
        [ticker, metric],
    ).fetchone()
    if row and row[0] is not None:
        return float(row[0])
    fb = METRIC_FALLBACK.get(metric)
    if fb:
        row = con.execute(
            f"SELECT value FROM {table} "
            f"WHERE ticker = ? AND metric = ? AND value IS NOT NULL "
            f"ORDER BY date DESC LIMIT 1",
            [ticker, fb],
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None
    return None


def _pe_percentile_10y(con, ticker: str) -> float | None:
    cutoff = date.today() - timedelta(days=365 * 10)
    row = con.execute(
        """
        WITH series AS (
            SELECT value FROM valuation
            WHERE ticker = ? AND metric = 'PE-TTM' AND value IS NOT NULL
              AND date >= ?
        ),
        latest AS (
            SELECT value FROM valuation
            WHERE ticker = ? AND metric = 'PE-TTM' AND value IS NOT NULL
            ORDER BY date DESC LIMIT 1
        )
        SELECT
            (SELECT COUNT(*) FROM series WHERE value <= (SELECT value FROM latest)) * 1.0
            / NULLIF((SELECT COUNT(*) FROM series), 0)
        """,
        [ticker, cutoff, ticker],
    ).fetchone()
    return float(row[0]) if row and row[0] is not None else None


def _fscore(ticker: str, year: int) -> int | None:
    """跑 Piotroski 9 项,返回 0-9 整数得分。失败返回 None。"""
    try:
        engine = _engine_module()
        rules_path = RULES_DIR / "piotroski.yaml"
        data = _load_duckdb_data_cached(ticker, _db_mtime())
        result = engine.run_score(rules_path, data, year)
        return int(result.total_score) if result is not None else None
    except Exception:
        return None


def load_all(db_path: Path | str = DB_PATH, fscore_year: int | None = None) -> pd.DataFrame:
    """返回 15 家公司一行的宽表。

    columns:
      ticker / name / folder / category
      pe / pb / dividend_yield / roe / gm / rev_yoy / cfo_to_ni / debt_ratio
      pe_pct_10y / fscore
    """
    if fscore_year is None:
        fscore_year = pd.Timestamp.now().year - 1

    con = _conn(db_path)
    try:
        companies = con.execute(
            "SELECT ticker, folder, name, category FROM companies ORDER BY folder"
        ).fetchall()
        rows: list[dict[str, Any]] = []
        for ticker, folder, name, category in companies:
            row: dict[str, Any] = {
                "ticker": ticker, "folder": folder, "name": name,
                "category": category or "",
            }
            for key, (table, metric) in METRIC_SOURCE.items():
                row[key] = _latest(con, table, ticker, metric)
            row["pe_pct_10y"] = _pe_percentile_10y(con, ticker)
            row["fscore"] = _fscore(ticker, fscore_year)
            rows.append(row)
        return pd.DataFrame(rows)
    finally:
        con.close()


# ─── filter 应用 ─────────────────────────────────────────────────────
_OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">":  lambda a, b: a >  b,
    "<":  lambda a, b: a <  b,
    "==": lambda a, b: a == b,
}


def apply_filters(df: pd.DataFrame, filters: list[dict]) -> pd.DataFrame:
    """逐条 AND 过滤;某 metric 缺数据(NaN)的公司被过滤掉。"""
    if not filters:
        return df.copy()
    mask = pd.Series([True] * len(df), index=df.index)
    for f in filters:
        m = f.get("metric")
        op = f.get("op", ">=")
        v = f.get("value")
        if m is None or m not in df.columns or v is None:
            continue
        op_fn = _OPS.get(op)
        if op_fn is None:
            continue
        col = pd.to_numeric(df[m], errors="coerce")
        sub_mask = col.apply(lambda x: False if pd.isna(x) else op_fn(x, v))
        mask &= sub_mask
    return df[mask].copy()


def apply_preset(df: pd.DataFrame, preset_id: str,
                 presets: dict | None = None) -> pd.DataFrame:
    presets = presets or load_presets()
    for p in presets.get("presets", []):
        if p.get("id") == preset_id:
            return apply_filters(df, p.get("filters", []))
    return df.copy()


# ─── 大师评分(M2 #3 数据底座)───────────────────────────────────────

def _normalize_rules_doc(doc: dict) -> dict:
    """lynch.yaml 用 garp_rules 而不是 rules — 统一为 rules 别名。"""
    if "rules" not in doc:
        for alt in ("garp_rules", "core_rules"):
            if alt in doc:
                doc["rules"] = doc[alt]
                break
    return doc


def load_master_rules(master_id: str, rules_dir: Path | str = RULES_DIR) -> dict:
    """读 .tools/rules/{master_id}.yaml,返回带 rules 别名归一化的 dict。"""
    path = Path(rules_dir) / f"{master_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Master rules not found: {path}")
    return _normalize_rules_doc(yaml.safe_load(path.read_text(encoding="utf-8")))


def format_rating(score: float | None, thresholds: dict, valid_rules: int = 1) -> str:
    """按 yaml threshold 字段映射 emoji 评级;valid_rules=0 时降级。"""
    if score is None or pd.isna(score):
        return "—"
    if valid_rules == 0:
        return "⚪ 数据不足"
    if "excellent" in thresholds and score >= thresholds["excellent"]:
        return "🟢 优秀"
    if "good" in thresholds and score >= thresholds["good"]:
        return "🟡 合格"
    if "warning" in thresholds and score >= thresholds["warning"]:
        return "🟠 警戒"
    return "🔴 不及格"


@functools.lru_cache(maxsize=1)
def _engine_module():
    """engine.py 单例,避免每行公司重复 SourceFileLoader().load_module()
    (load_all 对 100 家各重载一次,实测占首屏一半成本)。"""
    return SourceFileLoader("engine", str(SCORE_DIR / "engine.py")).load_module()


@functools.lru_cache(maxsize=256)
def _load_duckdb_data_cached(ticker: str, db_mtime: float):
    """按 (ticker, db_mtime) 缓存 engine.load_duckdb_data;mtime 变即失效。"""
    return _engine_module().load_duckdb_data(ticker)


def _db_mtime() -> float:
    try:
        return DB_PATH.stat().st_mtime
    except OSError:
        return 0.0


def _score_one_master(engine, rules_doc: dict, rules_path: Path,
                      ticker: str, year: int) -> dict:
    """单家公司单大师评分。返回 dict(score / max_score / rating / valid / total)。

    与 multi_master.run_one 同款:跳过多行公式 / 数据缺失项不计入有效项。
    行业排除 → score=NaN, rating="🚫 不适用"。
    """
    total_rules = len(rules_doc.get("rules", []))
    max_score = rules_doc.get("max_score")
    excluded = rules_doc.get("exclude_industries", [])

    try:
        data = engine.load_duckdb_data(ticker)
    except Exception:
        return {"score": float("nan"), "max_score": max_score,
                "rating": "⚪ 数据不足", "valid_rules": 0, "total_rules": total_rules}

    if data.industry in excluded:
        return {"score": float("nan"), "max_score": max_score,
                "rating": "🚫 不适用", "valid_rules": 0, "total_rules": total_rules}

    # 行业自动切换(银行/保险版 piotroski)
    industry_files = rules_doc.get("industry_specific_files") or {}
    specific = industry_files.get(data.industry)
    actual_doc = rules_doc
    if specific:
        sp = rules_path.parent / specific
        if sp.exists() and sp != rules_path:
            actual_doc = _normalize_rules_doc(
                yaml.safe_load(sp.read_text(encoding="utf-8"))
            )
            total_rules = len(actual_doc.get("rules", []))
            max_score = actual_doc.get("max_score", max_score)

    rules = actual_doc.get("rules", []) or []
    if not rules:
        return {"score": float("nan"), "max_score": max_score,
                "rating": "—(无评分规则)", "valid_rules": 0, "total_rules": 0}

    evaluator = engine.FormulaEvaluator(data, year)
    score = 0.0
    valid = 0
    for rule in rules:
        f = rule.get("formula", "") or rule.get("formula_primary", "") or ""
        # 跳过多行/复合公式(damodaran DCF / Z'-score 等)
        if not f or "\n" in f or "Z'" in f or "DCF" in f:
            continue
        try:
            rule_score, passed, _ = engine.eval_rule(rule, evaluator)
        except Exception:
            passed = None
            rule_score = 0.0
        if passed is None:
            continue
        valid += 1
        score += rule_score

    return {
        "score": score,
        "max_score": max_score,
        "rating": format_rating(score, actual_doc.get("threshold", {}), valid),
        "valid_rules": valid,
        "total_rules": total_rules,
    }


def score_lynch_classifier_all(df: pd.DataFrame) -> pd.DataFrame:
    """M6 林奇分类器评分链路 · 替代旧 GARP 硬规则。

    每行公司:
      1. classify_ticker → 六类判定
      2. compute_lynch_dims → 类型专属 5 维评分(0-100)
      3. overall_lynch → 加权综合分(0-100)+ emoji 评级

    新增列(对齐 score_with_master 接口):
      score / max_score / rating / valid_rules / total_rules
      lynch_type / lynch_type_cn / lynch_type_emoji / lynch_confidence
      dim_top / dim_bot — 该类型评分最高/最低的维度
    """
    sys_path_dash = str(Path(__file__).resolve().parent)
    if sys_path_dash not in sys.path:
        sys.path.insert(0, sys_path_dash)
    from masters.lynch.classifier import (  # noqa: E402
        classify, compute_lynch_dims, load_metrics_from_db, overall_lynch,
    )

    out = df.copy()
    cols: dict[str, list] = {
        "score": [], "rating": [], "valid_rules": [],
        "lynch_type": [], "lynch_type_cn": [], "lynch_type_emoji": [],
        "lynch_confidence": [], "dim_top": [], "dim_bot": [],
    }

    for ticker in out["ticker"]:
        try:
            # 每家只读一次 metrics,复用给 classify + compute_lynch_dims
            # (旧代码 classify_ticker 内部已 load 一次,循环又 load 一次 → 2×)。
            m = load_metrics_from_db(ticker)
            cls = classify(m)
            if cls.cls_id == "not_applicable" or cls.extra.get("lynch_six_class_misfit"):
                cols["score"].append(float("nan"))
                cols["rating"].append("⚪ 不适用")
                cols["valid_rules"].append(0)
                cols["lynch_type"].append(cls.cls_id)
                cols["lynch_type_cn"].append(cls.cls_name)
                cols["lynch_type_emoji"].append(cls.cls_emoji)
                cols["lynch_confidence"].append(cls.confidence)
                cols["dim_top"].append("转行业专属框架")
                cols["dim_bot"].append("PEG/通用护栏不适用")
                continue
            dims = compute_lynch_dims(m, cls.cls_id)
            overall, _badge = overall_lynch(dims)

            if overall >= 75:
                rating = "🟢 优秀"
            elif overall >= 60:
                rating = "🟡 合格"
            elif overall >= 45:
                rating = "🟠 警戒"
            else:
                rating = "🔴 不及格"

            valid_dims = [d for d in dims if d.score is not None]
            if valid_dims:
                t = max(valid_dims, key=lambda d: d.score)
                b = min(valid_dims, key=lambda d: d.score)
                top = f"{t.badge} {t.label} {t.score:.0f}"
                bot = f"{b.badge} {b.label} {b.score:.0f}"
            else:
                top = bot = "—"

            cols["score"].append(overall)
            cols["rating"].append(rating)
            cols["valid_rules"].append(len(valid_dims))
            cols["lynch_type"].append(cls.cls_id)
            cols["lynch_type_cn"].append(cls.cls_name)
            cols["lynch_type_emoji"].append(cls.cls_emoji)
            cols["lynch_confidence"].append(cls.confidence)
            cols["dim_top"].append(top)
            cols["dim_bot"].append(bot)
        except Exception:
            cols["score"].append(float("nan"))
            cols["rating"].append("⚪ 数据不足")
            cols["valid_rules"].append(0)
            cols["lynch_type"].append("")
            cols["lynch_type_cn"].append("")
            cols["lynch_type_emoji"].append("⚪")
            cols["lynch_confidence"].append(float("nan"))
            cols["dim_top"].append("—")
            cols["dim_bot"].append("—")

    for k, v in cols.items():
        out[k] = v
    out["max_score"] = 100
    out["total_rules"] = 5
    return out


def score_with_master(df: pd.DataFrame, master_id: str,
                      year: int | None = None) -> pd.DataFrame:
    """对 df 每行公司跑大师评分,追加 5 列。

    新增列:
      score        — 0-max 浮点(数据缺失项计 0)
      max_score    — yaml 声明的总分上限(可能 None)
      rating       — 🟢 优秀 / 🟡 合格 / 🟠 警戒 / 🔴 不及格 / 🚫 不适用 / ⚪ 数据不足
      valid_rules  — 实际可评估项数
      total_rules  — 规则总数

    缺乏 per-company rules 的大师(如 greenblatt 仅 rank)→ score=NaN。
    """
    if year is None:
        year = pd.Timestamp.now().year - 1

    out = df.copy()
    rules_doc = load_master_rules(master_id)
    rules_path = RULES_DIR / f"{master_id}.yaml"

    if not rules_doc.get("rules"):
        n = len(out)
        out["score"] = [float("nan")] * n
        out["max_score"] = [rules_doc.get("max_score")] * n
        out["rating"] = ["—(全市场排名)"] * n
        out["valid_rules"] = [0] * n
        out["total_rules"] = [0] * n
        return out

    engine = _engine_module()

    # v2.5 G1: graham 按行业切 yaml(主/bank/insurance)
    rows = []
    for t in out["ticker"]:
        if master_id == "graham":
            try:
                from masters.graham.router import route_by_ticker
                routed_path = Path(route_by_ticker(t))
                routed_doc = _normalize_rules_doc(
                    yaml.safe_load(routed_path.read_text(encoding="utf-8"))
                )
                rows.append(_score_one_master(engine, routed_doc, routed_path, t, year))
            except Exception:
                rows.append(_score_one_master(engine, rules_doc, rules_path, t, year))
        else:
            rows.append(_score_one_master(engine, rules_doc, rules_path, t, year))

    for col in ("score", "max_score", "rating", "valid_rules", "total_rules"):
        out[col] = [r[col] for r in rows]
    return out



def _cli_print(df: pd.DataFrame, title: str) -> None:
    print(f"\n{'─' * 70}\n{title} · {len(df)} 家\n{'─' * 70}")
    if df.empty:
        print("  (空)")
        return
    show_cols = [c for c in [
        "name", "ticker", "pe", "pe_pct_10y", "pb", "dividend_yield",
        "roe", "rev_yoy", "cfo_to_ni", "debt_ratio", "fscore",
    ] if c in df.columns]
    print(df[show_cols].to_string(index=False))


def _cli_print_scores(df: pd.DataFrame, title: str) -> None:
    print(f"\n{'─' * 78}\n{title} · {len(df)} 家\n{'─' * 78}")
    if df.empty:
        print("  (空)")
        return
    show_cols = [c for c in [
        "name", "ticker", "score", "max_score", "rating",
        "valid_rules", "total_rules", "pe", "roe", "fscore",
    ] if c in df.columns]
    print(df.sort_values("score", ascending=False, na_position="last")[show_cols].to_string(index=False))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", choices=["buffett", "graham", "lynch", "greenblatt"],
                    default=None, help="硬过滤预设(presets.yaml)")
    ap.add_argument("--master", choices=["graham", "buffett", "lynch", "greenblatt"],
                    default=None, help="大师评分(M2 #3)— 跑全 15 家并排序")
    ap.add_argument("--year", type=int, default=None)
    args = ap.parse_args()

    df = load_all(fscore_year=args.year)
    _cli_print(df, "全 15 家公司原始指标")

    if args.master:
        scored = score_with_master(df, args.master, args.year)
        meta = load_master_rules(args.master)
        _cli_print_scores(
            scored,
            f"📊 大师评分:{meta.get('master_cn', args.master)} ({args.master}) · "
            f"max={meta.get('max_score', '—')} · "
            f"thresholds={meta.get('threshold', {})}",
        )
        return 0

    presets = load_presets()
    if args.preset:
        out = apply_preset(df, args.preset, presets)
        meta = next(p for p in presets["presets"] if p["id"] == args.preset)
        _cli_print(out, f"{meta['icon']} {meta['name']} — {meta['description']}")
    else:
        for p in presets["presets"]:
            out = apply_preset(df, p["id"], presets)
            _cli_print(out, f"{p['icon']} {p['name']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
