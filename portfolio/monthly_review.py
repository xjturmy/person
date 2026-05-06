"""月度复盘自动填充器 — 把持仓 / 评分 / 估值 / 偏离 / 候选打成 markdown,
供 .claude/prompts/monthly_review.md 中的 Claude prompt 消费。

用法:
    .venv/bin/python .tools/portfolio/monthly_review.py             # 当月
    .venv/bin/python .tools/portfolio/monthly_review.py --month 2026-04
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".tools" / "portfolio"))
sys.path.insert(0, str(ROOT / ".tools" / "score"))

from loader import load_portfolio  # noqa: E402

ENGINE = SourceFileLoader("engine", str(ROOT / ".tools" / "score" / "engine.py")).load_module()
MULTI = SourceFileLoader("multi_master", str(ROOT / ".tools" / "score" / "multi_master.py")).load_module()

DB_PATH = ROOT / "data" / "preson.duckdb"
OUT_DIR = ROOT / ".temp"
RULES_DIR = ROOT / ".tools" / "rules"


def latest_pe_and_pct(ticker: str) -> tuple[float | None, float | None]:
    try:
        import duckdb
        con = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            row = con.execute(
                """
                WITH latest AS (
                    SELECT value FROM valuation
                    WHERE ticker = ? AND metric = 'PE-TTM'
                    ORDER BY date DESC LIMIT 1
                ),
                series AS (
                    SELECT value FROM valuation
                    WHERE ticker = ? AND metric = 'PE-TTM' AND value IS NOT NULL
                )
                SELECT
                    (SELECT value FROM latest),
                    (SELECT COUNT(*) FROM series WHERE value <= (SELECT value FROM latest))
                        * 1.0 / NULLIF((SELECT COUNT(*) FROM series), 0)
                """,
                [ticker, ticker],
            ).fetchone()
            return (float(row[0]) if row and row[0] is not None else None,
                    float(row[1]) if row and row[1] is not None else None)
        finally:
            con.close()
    except Exception:
        return None, None


def fetch_multi_scores(ticker: str, year: int) -> dict[str, str]:
    """每个大师的得分字符串,失败/无数据用 '—'。"""
    out: dict[str, str] = {}
    for yaml_path in MULTI.list_executable_yamls():
        master = yaml_path.stem
        res = MULTI.run_one(yaml_path, ticker, year)
        if res is None:
            out[master] = "—"
        else:
            score, valid, total = res
            out[master] = f"{int(score)}/{total}({valid})" if valid else "—"
    return out


def aggregate_styles(per_master_raw: dict[str, str]) -> tuple[float, float]:
    """从字符串重算价值/成长聚合。"""
    style_score = {"value": (0.0, 0), "growth": (0.0, 0)}
    for master, s in per_master_raw.items():
        if s == "—" or "(" not in s:
            continue
        # parse "6/9(9)"
        head, _, valid_str = s.partition("(")
        score_str, _, total_str = head.partition("/")
        try:
            score = float(score_str)
            total = float(total_str)
            valid = int(valid_str.rstrip(")"))
        except ValueError:
            continue
        if valid == 0:
            continue
        style = MULTI.MASTER_STYLE.get(master)
        if not style:
            continue
        normalized = score / total if total else 0
        prev_s, prev_n = style_score[style]
        style_score[style] = (prev_s + normalized, prev_n + 1)
    out = {}
    for s, (sum_score, n) in style_score.items():
        out[s] = round(100 * sum_score / n, 1) if n else 0.0
    return out["value"], out["growth"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM(默认本月)")
    ap.add_argument("--year", type=int, help="评分年份(默认 month 上一年的年报)")
    args = ap.parse_args()

    today = date.today()
    if args.month:
        ym = args.month
        y, m = (int(x) for x in ym.split("-"))
    else:
        ym = today.strftime("%Y-%m")
        y, m = today.year, today.month

    score_year = args.year or (y - 1)  # 上一年年报最稳定

    p = load_portfolio()

    out_path = OUT_DIR / f"monthly_review_{ym}.md"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# 月度持仓数据快照 · {ym}",
        "",
        f"> 自动生成 · 评分基准年 {score_year}(上一年年报)· 估值用 valuation 表最新值",
        f"> 用法:配合 `.claude/prompts/monthly_review.md` 让 Claude 写完整复盘",
        "",
        f"## 1. 组合状态",
        "",
        f"- 配置版本:status={p.status}, last_updated={p.last_updated}",
        f"- 总资本:¥{p.account.total_capital:,.0f}",
        f"- 目标权益占比:{p.account.target_equity_ratio:.0%}",
        f"- active 持仓:{len(p.active())} 家  ·  watch:{len(p.watch())} 家  ·  exited:{len(p.exited)} 家",
        "",
        "## 2. 持仓 / 观察池评分快照",
        "",
        "| 公司 | 状态 | 目标权重 | piotroski | graham | lynch | buffett | 价值 | 成长 | 当前 PE | PE 分位 |",
        "|------|------|---------:|-----------|--------|-------|---------|-----:|-----:|--------:|--------:|",
    ]

    rows_data: list[dict] = []  # 用于段 3 加仓候选筛选
    for h in p.active() + p.watch():
        per_master = fetch_multi_scores(h.ticker, score_year)
        value, growth = aggregate_styles(per_master)
        pe, pct = latest_pe_and_pct(h.ticker)

        weight_str = f"{h.target_weight:.0%}" if h.target_weight else "—"
        pe_str = f"{pe:.1f}" if pe is not None else "—"
        pct_str = f"{pct:.1%}" if pct is not None else "—"

        # 取 piotroski 主分作"快速判断"
        piotroski_int = None
        if per_master.get("piotroski") not in (None, "—") and "/" in per_master["piotroski"]:
            try:
                piotroski_int = int(per_master["piotroski"].split("/")[0])
            except ValueError:
                pass

        rows_data.append({
            "ticker": h.ticker, "name": h.name, "status": h.status,
            "thesis": h.thesis, "piotroski": piotroski_int,
            "value": value, "growth": growth, "pe": pe, "pct": pct,
        })

        lines.append(
            f"| {h.name} | {h.status} | {weight_str} | "
            f"{per_master.get('piotroski','—')} | {per_master.get('graham','—')} | "
            f"{per_master.get('lynch','—')} | {per_master.get('buffett','—')} | "
            f"**{value:.1f}** | **{growth:.1f}** | {pe_str} | {pct_str} |"
        )

    # 候选 / 警报
    lines += [
        "",
        "## 3. watch 池加仓候选(F-Score ≥ 7 且 PE 分位 < 30%)",
        "",
    ]
    candidates = [r for r in rows_data
                  if r["status"] == "watch"
                  and r["piotroski"] is not None and r["piotroski"] >= 7
                  and r["pct"] is not None and r["pct"] < 0.30]
    if not candidates:
        lines.append("(本月无候选)")
    else:
        for r in candidates:
            lines.append(f"- 💎 **{r['name']}** ({r['ticker']}) — F-Score {r['piotroski']}/9, "
                         f"PE 分位 {r['pct']:.1%},价值 {r['value']:.1f},成长 {r['growth']:.1f}")
            lines.append(f"  - thesis:{r['thesis']}")

    lines += [
        "",
        "## 4. 高估警报(PE 分位 > 85%)",
        "",
    ]
    high_pct = [r for r in rows_data if r["pct"] is not None and r["pct"] > 0.85]
    if not high_pct:
        lines.append("(本月无高估)")
    else:
        for r in high_pct:
            lines.append(f"- 🔥 **{r['name']}** ({r['ticker']}) — PE {r['pe']:.1f}, 分位 {r['pct']:.1%}")

    lines += [
        "",
        "## 5. 评分恶化预警(F-Score < 4)",
        "",
    ]
    weak = [r for r in rows_data if r["piotroski"] is not None and r["piotroski"] < 4]
    if not weak:
        lines.append("(本月无评分恶化)")
    else:
        for r in weak:
            lines.append(f"- 🔴 **{r['name']}** ({r['ticker']}) — F-Score {r['piotroski']}/9")

    # 历史对比
    prev_files = sorted(OUT_DIR.glob("monthly_review_*.md"))
    prev_files = [p for p in prev_files if p != out_path]
    lines += [
        "",
        "## 6. 上月对比",
        "",
        f"上月报告:{prev_files[-1].name if prev_files else '(无)'}",
        "",
        '提示:让 Claude 读上月文件做"评分变化追踪"和"建议执行回顾"',
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ {out_path}")
    print(f"   持仓 {len(rows_data)} 家  ·  加仓候选 {len(candidates)}  ·  高估警报 {len(high_pct)}  ·  评分恶化 {len(weak)}")
    print('\n下一步:对 Claude 说"按 .claude/prompts/monthly_review.md 写本月复盘"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
