"""industry_master.yaml + companies.csv 合并加载.

yaml 是"深度研究版本"(含 knowledge_md / cycle_attrs 等),覆盖少数 L2;
csv 是项目自选池真实成员表,提供 (industry_l2, industry, stock, name) 列。

合并策略:yaml 条目原样保留;csv 中存在但 yaml 缺失的 L2,合成最小 meta dict
带 sw_l1 / type=stalwart / leaders / _members,并标记 _synthetic=True 以便
下游(drilldown / 行业概况)按需识别。
"""
from __future__ import annotations

import csv
import functools
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[4]
_INDUSTRY_MASTER_YAML = _ROOT / ".config" / "industry_master.yaml"
_COMPANIES_CSV = _ROOT / ".config" / "companies.csv"


def _load_yaml_map() -> dict[str, dict]:
    if not _INDUSTRY_MASTER_YAML.exists():
        return {}
    try:
        d = yaml.safe_load(_INDUSTRY_MASTER_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return {i["name"]: i for i in (d.get("industries") or []) if i.get("name")}


def _synthesize_from_csv() -> dict[str, dict]:
    if not _COMPANIES_CSV.exists():
        return {}
    by_l2: dict[str, dict] = {}
    try:
        with _COMPANIES_CSV.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                l2 = (row.get("industry_l2") or "").strip()
                l1 = (row.get("industry") or "").strip()
                stock = (row.get("stock") or "").strip().zfill(6)
                name = (row.get("name") or "").strip()
                if not l2 or l2 == "nan":
                    continue
                entry = by_l2.setdefault(l2, {
                    "name": l2,
                    "sw_l1": l1,
                    "type": "stalwart",
                    "leaders": [],
                    "_members": [],
                    "_synthetic": True,
                })
                if stock and stock not in entry["leaders"]:
                    entry["leaders"].append(stock)
                if name and stock:
                    entry["_members"].append((name, stock))
    except Exception:
        return {}
    for v in by_l2.values():
        v["leaders"] = v["leaders"][:5]
    return by_l2


@functools.lru_cache(maxsize=1)
def load_master_merged() -> dict[str, dict]:
    """yaml(优先) ∪ csv(兜底) 的 name → meta 字典."""
    merged = dict(_synthesize_from_csv())
    merged.update(_load_yaml_map())
    return merged


def clear_cache() -> None:
    load_master_merged.cache_clear()


__all__ = ["load_master_merged", "clear_cache"]
