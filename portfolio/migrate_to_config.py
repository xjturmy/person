"""v2.8 一次性迁移:把 .config/portfolio.yaml.positions[] 5 字段合并进
.tools/portfolio/portfolio.yaml.holdings[],然后写完整 doc 回 .config/portfolio.yaml,
让 .config 成为唯一持仓数据源。

字段合并(positions → holdings,按 ticker 对齐):
  school / rationale / criteria_met / review_triggers / name

合并优先级:positions[i] 字段非空时覆盖 holdings[i] 同名字段
(positions.name 已存在但 holdings.name 也存在;让 positions 赢以保留中文名)。

用法:
  python3 .tools/portfolio/migrate_to_config.py --dry-run    # 只打印计划
  python3 .tools/portfolio/migrate_to_config.py              # 实际写入
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_YAML = ROOT / ".config" / "portfolio.yaml"
TOOLS_YAML = ROOT / ".tools" / "portfolio" / "portfolio.yaml"

MERGE_FIELDS = ["school", "rationale", "criteria_met", "review_triggers"]


def _load(p: Path) -> dict:
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _backup(p: Path, suffix: str) -> Path | None:
    if not p.exists():
        return None
    bak = p.with_suffix(p.suffix + f".bak.{suffix}")
    shutil.copy2(p, bak)
    return bak


def merge(config_doc: dict, tools_doc: dict) -> tuple[dict, list[str]]:
    """返回 (merged_doc, log_lines)。

    merged_doc 以 tools_doc 为模板(含 _meta / account / rebalance / holdings / exited /
    benchmarks),把 config_doc.positions[] 的 5 字段按 ticker 注入 holdings[]。
    """
    log: list[str] = []
    positions = {str(p.get("ticker", "")).strip(): p
                 for p in (config_doc.get("positions") or [])
                 if p.get("ticker")}
    holdings = tools_doc.get("holdings") or []
    holdings_by_tkr = {str(h.get("ticker", "")).strip(): h for h in holdings}

    matched = 0
    pos_only = []  # positions 有但 holdings 没有 — 需要新建
    for tkr, pos in positions.items():
        h = holdings_by_tkr.get(tkr)
        if h is None:
            # positions 独有:在 holdings 里新建一条 watch
            new_h = {"ticker": tkr, "status": "watch"}
            if pos.get("name"):
                new_h["name"] = pos["name"]
            for f in MERGE_FIELDS:
                v = pos.get(f)
                if v:
                    new_h[f] = v
            holdings.append(new_h)
            holdings_by_tkr[tkr] = new_h
            pos_only.append(tkr)
            log.append(f"  + 新建 {tkr} {pos.get('name','')} (positions 独有,设为 watch)")
            continue

        # positions.name 非空且 holdings.name 为空时补
        if pos.get("name") and not h.get("name"):
            h["name"] = pos["name"]
        for f in MERGE_FIELDS:
            v = pos.get(f)
            if not v:
                continue
            # 已存在且非空 → 跳过(holdings 优先);否则注入
            if h.get(f):
                continue
            h[f] = v
        matched += 1
        log.append(f"  ✓ {tkr} {h.get('name','')} (merge {len([f for f in MERGE_FIELDS if pos.get(f)])} 字段)")

    holdings_only = [t for t in holdings_by_tkr if t not in positions]
    log.insert(0,
        f"统计:positions {len(positions)} / holdings {len(holdings_by_tkr)} / "
        f"匹配 {matched} / positions-独有 {len(pos_only)} / holdings-独有 {len(holdings_only)}"
    )

    # 写完整 doc(以 tools_doc 为底)
    merged = dict(tools_doc)
    merged["holdings"] = holdings
    merged.setdefault("_meta", {})["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    merged["_meta"]["schema_version"] = "2.8"
    return merged, log


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="只打印计划,不写文件")
    args = ap.parse_args()

    if not TOOLS_YAML.exists():
        print(f"❌ 找不到 {TOOLS_YAML},无法迁移", file=sys.stderr)
        sys.exit(1)

    config_doc = _load(CONFIG_YAML)
    tools_doc = _load(TOOLS_YAML)
    merged, log = merge(config_doc, tools_doc)

    print("=" * 60)
    print(f"迁移源:")
    print(f"  .config/portfolio.yaml  (positions[{len(config_doc.get('positions') or [])}])")
    print(f"  .tools/portfolio/portfolio.yaml  (holdings[{len(tools_doc.get('holdings') or [])}])")
    print(f"迁移目标:.config/portfolio.yaml(完整 doc)")
    print("=" * 60)
    for line in log:
        print(line)
    print("=" * 60)

    if args.dry_run:
        print("DRY-RUN 模式,未写入。加 --no-dry-run 或去掉 --dry-run 执行实际迁移。")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cb = _backup(CONFIG_YAML, f"v2.8-pre-merge-{ts}")
    tb = _backup(TOOLS_YAML, f"v2.8-pre-merge-{ts}")
    if cb:
        print(f"💾 .config/portfolio.yaml 备份:{cb.name}")
    if tb:
        print(f"💾 .tools/portfolio/portfolio.yaml 备份:{tb.name}")

    CONFIG_YAML.write_text(
        yaml.safe_dump(merged, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"✅ 已写入 {CONFIG_YAML}")

    # rename tools yaml 为 .deprecated(下个 patch 删)
    dep = TOOLS_YAML.with_suffix(TOOLS_YAML.suffix + ".deprecated")
    TOOLS_YAML.rename(dep)
    print(f"🗑️  原 .tools/portfolio/portfolio.yaml → {dep.name}(留缓冲,下个 patch 删)")


if __name__ == "__main__":
    main()
