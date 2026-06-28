#!/usr/bin/env python3
"""离线分析预计算 — 把所有 per-company / 跨公司重计算落盘到 data/analytics.duckdb。

目的:Dashboard 页面切换时不再 live 算分(选股 100 家评分 ~4s / 公司页 ~0.6s),
改为读预算好的表/blob(<30ms),让每次切换 <100ms。

产出 data/analytics.duckdb:
  screener_wide   — score_lynch_classifier_all(load_all(year)) 的 100 行扁平表(选股页)
  company_bundle  — ticker -> pickle({score, price_range, peers, lynch_metrics})(公司页)
  meta            — built_at / src_mtime / year / n_companies

新鲜度:分数是"本次运行时"的快照。数据周日 cron 更新后,由 update_pipeline.py
末尾自动重跑;Dashboard sidebar「🔄 刷新预计算」按钮也可手动触发(后台 subprocess)。
读层(analytics_store.py)按 analytics.duckdb mtime 失效缓存;blob 缺失/损坏时
页面降级回 live 计算,所以首次预计算前一切照常工作。

Run:
  cd /Users/gongyong/Desktop/Keyi/preson && .venv/bin/python .tools/analytics/precompute.py
  .venv/bin/python .tools/analytics/precompute.py --year 2024
"""
from __future__ import annotations

import argparse
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / ".tools" / "dashboard"
for _p in (DASH, ROOT / ".tools", ROOT / ".tools" / "score"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

PRESON_DB = ROOT / "data" / "preson.duckdb"
ANALYTICS_DB = ROOT / "data" / "analytics.duckdb"


def _src_mtime() -> float:
    try:
        return PRESON_DB.stat().st_mtime
    except OSError:
        return 0.0


def _build_screener_wide(year: int):
    """选股页全市场扁平表:load_all + 林奇分类评分。"""
    from screening import screener as scr
    df = scr.load_all(fscore_year=year)
    try:
        df = scr.score_lynch_classifier_all(df)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ score_lynch_classifier_all 失败,wide 表仅含基础列: {e}")
    return df


def _classify_graham_one(ticker: str) -> tuple[str, str, str]:
    try:
        from masters.graham.steps import classify_graham_type, load_graham_metrics
        m = load_graham_metrics(ticker)
        r = classify_graham_type(m)
        return (r.cls_id, r.cls_name, r.cls_emoji)
    except Exception:
        return ("skip", "不适用", "❓")


def _build_value_scored(wide_df, year: int) -> dict:
    """格雷厄姆选股页:graham / buffett 价值评分全市场表(+ graham 四类判定)。

    复用 wide_df 作为 load_all 基表(同列),对全市场跑 score_with_master,
    与 graham_pick 的 _value_scored 逐 ticker 过滤等价。
    """
    from screening import screener as scr
    out: dict = {}
    base = wide_df.copy()
    for master_id in ("graham", "buffett"):
        try:
            scored = scr.score_with_master(base.copy(), master_id, year)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ score_with_master({master_id}) 失败: {e}")
            continue
        if master_id == "graham" and not scored.empty:
            cls = [_classify_graham_one(str(t)) for t in scored["ticker"]]
            scored["graham_class"] = [c[0] for c in cls]
            scored["价值类型"] = [f"{c[2]} {c[1]}" for c in cls]
        out[master_id] = scored
    return out


def _build_company_bundle(ticker: str, name: str, year: int) -> bytes:
    """单家公司的页面所需重计算打包成 pickle blob。"""
    import ui.score_card as sc

    bundle: dict = {"ticker": ticker, "name": name}

    # 6 维 + 7 大师评分(CompanyScore,含 .masters / .strategies_year)
    try:
        bundle["score"] = sc.compute_dimensions(ticker, db_path=PRESON_DB, strategies_year=year)
    except Exception as e:  # noqa: BLE001
        bundle["score"] = None
        bundle["score_err"] = f"{type(e).__name__}: {e}"

    # 下季度合理价格区间(三模型加权,权重看 lynch_type)
    try:
        from masters.lynch.classifier import lynch_type_of
        from valuation.price_range import compute_next_quarter_range
        lt = lynch_type_of(ticker, _src_mtime())
        bundle["price_range"] = compute_next_quarter_range(ticker, name=name, lynch_type=lt)
        bundle["lynch_type"] = lt
    except Exception as e:  # noqa: BLE001
        bundle["price_range"] = None
        bundle["price_range_err"] = f"{type(e).__name__}: {e}"

    # 同行池(self + peers 的 ticker/name),供 block_b 大师矩阵 / 雷达
    try:
        import peers.radar as pr
        bundle["peers"] = pr.peer_pool(ticker, db_path=PRESON_DB, max_n=4) if pr else []
    except Exception:  # noqa: BLE001
        bundle["peers"] = []

    # 林奇 metrics dict(部分卡片直接读)
    try:
        from masters.lynch.classifier import load_metrics_from_db
        bundle["lynch_metrics"] = load_metrics_from_db(ticker)
    except Exception:  # noqa: BLE001
        bundle["lynch_metrics"] = {}

    return pickle.dumps(bundle, protocol=pickle.HIGHEST_PROTOCOL)


def _all_companies() -> list[tuple[str, str]]:
    con = duckdb.connect(str(PRESON_DB), read_only=True)
    try:
        return con.execute("SELECT ticker, name FROM companies ORDER BY folder").fetchall()
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=None, help="财年(默认去年)")
    args = ap.parse_args()
    year = args.year or (datetime.now().year - 1)  # noqa: DTZ005 (本地脚本可接受)

    if not PRESON_DB.exists():
        print(f"❌ 找不到 {PRESON_DB},先跑 ingest")
        return 1

    t0 = time.perf_counter()
    print(f"📊 预计算开始 · year={year} · 源 {PRESON_DB.name}")

    companies = _all_companies()
    print(f"  公司数: {len(companies)}")

    # 1) 选股扁平表
    print("  → screener_wide …", flush=True)
    wide = _build_screener_wide(year)

    # 1b) 格雷厄姆/巴菲特价值评分表
    print("  → value_scored(graham/buffett) …", flush=True)
    value = _build_value_scored(wide, year)

    # 2) 公司 bundle
    print("  → company_bundle …", flush=True)
    rows: list[tuple[str, bytes]] = []
    ok = 0
    for ticker, name in companies:
        try:
            rows.append((ticker, _build_company_bundle(ticker, name, year)))
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"    ⚠️ {ticker} {name}: {e}")
    print(f"    bundle 成功 {ok}/{len(companies)}")

    # 3) 原子写入:先写临时库再替换
    tmp = ANALYTICS_DB.with_suffix(".duckdb.tmp")
    if tmp.exists():
        tmp.unlink()
    con = duckdb.connect(str(tmp))
    try:
        con.register("wide_df", wide)
        con.execute("CREATE TABLE screener_wide AS SELECT * FROM wide_df")
        con.unregister("wide_df")

        for master_id, sdf in value.items():
            con.register("value_df", sdf)
            con.execute(f"CREATE TABLE value_scored_{master_id} AS SELECT * FROM value_df")
            con.unregister("value_df")

        con.execute("CREATE TABLE company_bundle (ticker VARCHAR PRIMARY KEY, payload BLOB)")
        con.executemany("INSERT INTO company_bundle VALUES (?, ?)", rows)

        con.execute("CREATE TABLE meta (key VARCHAR, value VARCHAR)")
        con.executemany("INSERT INTO meta VALUES (?, ?)", [
            ("built_at", datetime.now().isoformat(timespec="seconds")),  # noqa: DTZ005
            ("src_mtime", str(_src_mtime())),
            ("year", str(year)),
            ("n_companies", str(len(companies))),
            ("n_bundle", str(ok)),
        ])
    finally:
        con.close()

    # 原子替换
    ANALYTICS_DB.unlink(missing_ok=True)
    tmp.rename(ANALYTICS_DB)

    dt = (time.perf_counter() - t0)
    print(f"✅ 预计算完成 · {ANALYTICS_DB.relative_to(ROOT)} · {len(wide)} 行 wide / {ok} bundle · {dt:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
