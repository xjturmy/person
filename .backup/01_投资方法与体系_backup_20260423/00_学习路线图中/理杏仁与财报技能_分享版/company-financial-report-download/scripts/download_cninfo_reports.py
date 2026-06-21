#!/usr/bin/env python3
"""
公司财报下载：从巨潮资讯网按股票代码与公告分类下载定期报告 PDF（依赖公开接口，请控制频率）。

标准化命名：{公司名}_{年份}年{报告类型}.pdf。
原始文件名（公告标题+ID）会写入 `财报下载映射.md`，通过映射判定增量是否已完成。
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
STOCK_LIST_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"
STATIC_BASE = "http://static.cninfo.com.cn/"

_EXISTING_ID_SUFFIX = re.compile(r"_(\d{8,})\.pdf$", re.IGNORECASE)
_MD_TABLE_ROW_RE = re.compile(r"^\|.*\|$")
_YEAR_RE = re.compile(r"(20\d{2})年")

CATEGORY_TO_PERIOD = {
    "category_ndbg_szsh": ("Q4", "Q4财报"),
    "category_yjdbg_szsh": ("Q1", "Q1财报"),
    "category_bndbg_szsh": ("Q2", "Q2财报"),
    "category_sjdbg_szsh": ("Q3", "Q3财报"),
}

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research/1.0)",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


def _should_retry(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionResetError, TimeoutError, socket.timeout)):
        return True
    if isinstance(exc, urllib.error.URLError):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500 or exc.code == 429
    return False


def _http_json_post(url: str, data: dict, timeout: int = 60, retries: int = 4) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=DEFAULT_HEADERS, method="POST")
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= retries or not _should_retry(exc):
                raise
            wait_s = min(8.0, 0.8 * (2**attempt))
            print(f"  retry post ({attempt + 1}/{retries}) after {wait_s:.1f}s: {exc}")
            time.sleep(wait_s)
    raise RuntimeError(f"_http_json_post failed unexpectedly: {last_exc}")


def _http_get_bytes(url: str, timeout: int = 120, retries: int = 4) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_HEADERS["User-Agent"]})
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= retries or not _should_retry(exc):
                raise
            wait_s = min(8.0, 0.8 * (2**attempt))
            print(f"  retry get ({attempt + 1}/{retries}) after {wait_s:.1f}s: {exc}")
            time.sleep(wait_s)
    raise RuntimeError(f"_http_get_bytes failed unexpectedly: {last_exc}")


_stock_list_map: dict[str, str] | None = None


def _fetch_stock_list_map() -> dict[str, str]:
    global _stock_list_map
    if _stock_list_map is not None:
        return _stock_list_map
    req = urllib.request.Request(STOCK_LIST_URL, headers={"User-Agent": DEFAULT_HEADERS["User-Agent"]})
    last_exc: Exception | None = None
    payload: dict = {}
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt >= 4 or not _should_retry(exc):
                raise
            wait_s = min(8.0, 0.8 * (2**attempt))
            print(f"  retry stock list ({attempt + 1}/4) after {wait_s:.1f}s: {exc}")
            time.sleep(wait_s)
    if not payload and last_exc:
        raise last_exc
    _stock_list_map = {
        str(row.get("code", "")).zfill(6): str(row["orgId"])
        for row in (payload.get("stockList") or [])
        if row.get("orgId")
    }
    return _stock_list_map


def load_org_id(code: str) -> str:
    code = code.strip().zfill(6)
    oid = _fetch_stock_list_map().get(code)
    if oid:
        return oid
    raise SystemExit(f"在 {STOCK_LIST_URL} 中未找到代码 {code} 的 orgId")


def guess_column(code: str) -> str:
    c = code.strip()
    if c.startswith(("6", "5")):
        return "sse"
    if c.startswith(("0", "3")):
        return "szse"
    if c.startswith("8") or c.startswith("4"):
        return "szse"
    return "szse"


def sanitize_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.strip() or "file"
    if len(name) > max_len:
        name = name[:max_len]
    return name


def _md_escape(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ").strip()


def _derive_company_name(company_name: str | None, out_dir: Path, code: str) -> str:
    if company_name:
        return company_name.strip()
    folder = out_dir.parent.name if out_dir.name in ("90_财报", "02_公司财报") else out_dir.name
    m = re.match(r"^\d+_(.+)$", folder)
    if m:
        return m.group(1)
    return code


def _extract_year(title: str, announcement_time_ms: int | None) -> int:
    m = _YEAR_RE.search(title)
    if m:
        return int(m.group(1))
    if announcement_time_ms:
        return datetime.fromtimestamp(announcement_time_ms / 1000).year
    return datetime.now().year


def _period_for_category(category: str) -> tuple[str, str]:
    return CATEGORY_TO_PERIOD.get(category, ("OTHER", "其他财报"))


def _report_key_aliases(year: int, period_code: str) -> list[str]:
    aliases = [f"{year}_{period_code}"]
    if period_code == "Q2":
        aliases.append(f"{year}_H1")
    if period_code == "Q4":
        aliases.append(f"{year}_ANNUAL")
    return aliases


def _standard_filename(company: str, year: int, period_label: str) -> str:
    return sanitize_filename(f"{company}_{year}年{period_label}.pdf")


def scan_existing_announcement_ids(out_dir: Path) -> set[str]:
    found: set[str] = set()
    if not out_dir.is_dir():
        return found
    for p in out_dir.glob("*.pdf"):
        m = _EXISTING_ID_SUFFIX.search(p.name)
        if m:
            found.add(m.group(1))
    return found


def find_existing_file_by_announcement_id(out_dir: Path, announcement_id: str) -> Path | None:
    if not announcement_id:
        return None
    pattern = f"*_{announcement_id}.pdf"
    for p in out_dir.glob(pattern):
        if p.is_file():
            return p
    return None


def load_report_mapping(md_path: Path) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    if not md_path.is_file():
        return mapping

    for line in md_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not _MD_TABLE_ROW_RE.match(line.strip()):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 9:
            continue
        if cells[0] in {"报告键", "---", ""}:
            continue
        report_key, std_name, category, year, aid, orig_name, title, url, updated_at = cells
        mapping[report_key] = {
            "report_key": report_key,
            "std_name": std_name,
            "category": category,
            "year": year,
            "announcement_id": aid,
            "orig_name": orig_name,
            "title": title,
            "url": url,
            "updated_at": updated_at,
        }
    return mapping


def write_report_mapping(md_path: Path, mapping: dict[str, dict[str, str]]) -> None:
    rows = sorted(
        mapping.values(),
        key=lambda x: (
            int(x.get("year", "0") or 0),
            x.get("category", ""),
            x.get("report_key", ""),
        ),
        reverse=True,
    )

    lines = [
        "# 财报下载映射",
        "",
        "用于记录标准化文件名与巨潮原始公告文件名/公告ID的对应关系。",
        "增量更新时优先依据 `报告键`（年份+报告类型）判断是否已下载。",
        "",
        "| 报告键 | 标准文件名 | 分类 | 年份 | 公告ID | 原始文件名 | 公告标题 | 下载URL | 更新时间 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for r in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_escape(r.get("report_key", "")),
                    _md_escape(r.get("std_name", "")),
                    _md_escape(r.get("category", "")),
                    _md_escape(r.get("year", "")),
                    _md_escape(r.get("announcement_id", "")),
                    _md_escape(r.get("orig_name", "")),
                    _md_escape(r.get("title", "")),
                    _md_escape(r.get("url", "")),
                    _md_escape(r.get("updated_at", "")),
                ]
            )
            + " |"
        )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _candidate_sort_key(title: str) -> int:
    """返回排序键，值越小越优先被选中。"""
    t = title or ""
    if "取消" in t:
        return 99
    score = 0
    if "更新后" in t or "更正后" in t:
        score -= 5
    if "正文" in t:
        score += 3
    if "全文" in t:
        score += 2
    if "英文" in t or "English" in t:
        score += 4
    if "摘要" in t:
        score += 6
    return score


def _make_mapping_entry(c: dict, aid: str) -> dict[str, str]:
    return {
        "report_key": c["report_key"],
        "std_name": c["std_name"],
        "category": c["category"],
        "year": str(c["year"]),
        "announcement_id": aid,
        "orig_name": c["orig_name"],
        "title": c["title"],
        "url": c["url"],
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def download_reports(
    code: str,
    org_id: str | None,
    column: str | None,
    category: str,
    start_date: str,
    end_date: str,
    out_dir: Path,
    sleep_s: float,
    dry_run: bool,
    title_exclude_substrings: list[str] | None = None,
    company_name: str | None = None,
    mapping_filename: str = "财报下载映射.md",
) -> None:
    code = code.strip().zfill(6)
    oid = org_id or load_org_id(code)
    col = column or guess_column(code)
    se_date = f"{start_date}~{end_date}"
    stock_param = f"{code},{oid}"
    period_code, period_label = _period_for_category(category)

    out_dir.mkdir(parents=True, exist_ok=True)
    company = _derive_company_name(company_name, out_dir, code)
    mapping_path = out_dir / mapping_filename
    report_mapping = load_report_mapping(mapping_path)
    existing_ids = scan_existing_announcement_ids(out_dir)
    if existing_ids:
        print(f"增量：目录中已有 {len(existing_ids)} 个可识别公告 ID")
    if report_mapping:
        print(f"映射：已有 {len(report_mapping)} 条记录 ({mapping_path.name})")

    page = 1
    page_size = 30
    candidates: dict[str, dict] = {}

    while True:
        form = {
            "pageNum": str(page),
            "pageSize": str(page_size),
            "column": col,
            "tabName": "fulltext",
            "plate": "",
            "stock": stock_param,
            "searchkey": "",
            "secid": "",
            "category": category,
            "trade": "",
            "seDate": se_date,
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        data = _http_json_post(QUERY_URL, form)
        rows = data.get("announcements") or []
        if not rows:
            break

        for ann in rows:
            title = (ann.get("announcementTitle") or "untitled").strip()
            if title_exclude_substrings and any(
                sub in title for sub in title_exclude_substrings if sub
            ):
                continue

            adjunct = (ann.get("adjunctUrl") or "").strip()
            if not adjunct:
                continue
            if (ann.get("adjunctType") or "").upper() != "PDF":
                continue

            announcement_id = str(ann.get("announcementId") or "").strip()
            announcement_time = int(ann.get("announcementTime") or 0)
            year = _extract_year(title, announcement_time)
            report_key = f"{year}_{period_code}"

            raw_name = sanitize_filename(f"{title}_{announcement_id}.pdf")
            std_name = _standard_filename(company, year, period_label)
            url = STATIC_BASE + adjunct.lstrip("/")

            cand = {
                "report_key": report_key,
                "std_name": std_name,
                "year": year,
                "category": category,
                "announcement_id": announcement_id,
                "orig_name": raw_name,
                "title": title,
                "url": url,
                "announcement_time": announcement_time,
                "sort_key": _candidate_sort_key(title),
            }

            old = candidates.get(report_key)
            if old is None:
                candidates[report_key] = cand
                continue

            old_rank = (old["sort_key"], -old["announcement_time"])
            new_rank = (cand["sort_key"], -cand["announcement_time"])
            if new_rank < old_rank:
                candidates[report_key] = cand

        if len(rows) < page_size:
            break
        page += 1
        time.sleep(sleep_s)

    total_saved = 0
    total_skipped = 0
    total_normalized = 0
    mapping_changed = False

    sorted_candidates = sorted(candidates.values(), key=lambda x: x["year"], reverse=True)
    for c in sorted_candidates:
        report_key = c["report_key"]
        std_path = out_dir / c["std_name"]
        aid = c["announcement_id"]

        key_aliases = _report_key_aliases(c["year"], report_key.split("_", 1)[1])
        mapped_key = next((k for k in key_aliases if k in report_mapping), None)
        mapped = report_mapping.get(mapped_key) if mapped_key else None
        if mapped:
            old_std_name = (mapped.get("std_name") or "").strip()
            old_std_path = out_dir / old_std_name if old_std_name else None

            if not std_path.exists() and old_std_path and old_std_path.exists() and old_std_path != std_path:
                if dry_run:
                    print(f"would migrate filename: {old_std_path.name} -> {std_path.name}")
                else:
                    old_std_path.rename(std_path)
                    print(f"migrate filename: {old_std_path.name} -> {std_path.name}")
                    total_normalized += 1

            report_mapping[report_key] = _make_mapping_entry(c, aid)
            if mapped_key and mapped_key != report_key:
                report_mapping.pop(mapped_key, None)
            mapping_changed = True

            if std_path.exists():
                print(f"skip mapped: {report_key} -> {std_path.name}")
                total_skipped += 1
                continue

        legacy = find_existing_file_by_announcement_id(out_dir, aid) if aid else None
        if legacy and legacy != std_path:
            if dry_run:
                if std_path.exists():
                    print(f"would clean legacy duplicate: {legacy.name}")
                else:
                    print(f"would normalize rename: {legacy.name} -> {std_path.name}")
            else:
                if std_path.exists():
                    legacy.unlink(missing_ok=True)
                    print(f"clean legacy duplicate: {legacy.name}")
                else:
                    legacy.rename(std_path)
                    print(f"normalize rename: {legacy.name} -> {std_path.name}")
                    total_normalized += 1

            report_mapping[report_key] = _make_mapping_entry(c, aid)
            mapping_changed = True
            total_skipped += 1
            continue

        if std_path.exists():
            print(f"skip exists standardized: {std_path.name}")
            report_mapping[report_key] = _make_mapping_entry(c, aid)
            mapping_changed = True
            total_skipped += 1
            continue

        print(f"get: {c['title'][:60]}... -> {std_path.name}")
        if dry_run:
            print(f"  -> {c['url']}")
            total_saved += 1
            continue

        time.sleep(sleep_s)
        try:
            blob = _http_get_bytes(c["url"])
        except urllib.error.HTTPError as e:
            print(f"  HTTP error {e.code}: {c['url']}")
            continue

        std_path.write_bytes(blob)
        total_saved += 1
        if aid:
            existing_ids.add(aid)

        report_mapping[report_key] = _make_mapping_entry(c, aid)
        mapping_changed = True

    if mapping_changed and not dry_run:
        write_report_mapping(mapping_path, report_mapping)

    if dry_run:
        print(
            f"完成（dry-run）。将新下载约 {total_saved} 个，跳过 {total_skipped} 个，标准化重命名 {total_normalized} 个 -> {out_dir}"
        )
    else:
        print(
            f"完成。新下载 {total_saved} 个，跳过 {total_skipped} 个，标准化重命名 {total_normalized} 个 -> {out_dir}"
        )
        print(f"映射文件: {mapping_path}")


def main() -> None:
    p = argparse.ArgumentParser(description="公司财报下载（巨潮资讯定期报告 PDF）")
    p.add_argument("--code", required=True, help="A 股证券代码，如 600519")
    p.add_argument("--org-id", default=None, help="可选，orgId；不传则从 szse_stock.json 查找")
    p.add_argument("--column", default=None, help="可选，sse / szse；不传则按代码猜测")
    p.add_argument(
        "--category",
        default="category_ndbg_szsh",
        help="公告分类，如 category_ndbg_szsh（年报）",
    )
    p.add_argument("--start-date", required=True, help="开始日期 YYYY-MM-DD")
    p.add_argument("--end-date", required=True, help="结束日期 YYYY-MM-DD")
    p.add_argument("--out-dir", required=True, type=Path, help="输出目录")
    p.add_argument("--company-name", default=None, help="标准化文件名前缀公司名，如 新华保险")
    p.add_argument("--sleep", type=float, default=0.8, help="请求间隔秒数，默认 0.8")
    p.add_argument("--dry-run", action="store_true", help="只打印 URL，不下载")
    p.add_argument(
        "--exclude-in-title",
        default="",
        help="逗号分隔；标题含任一子串则跳过（如 摘要,英文版）",
    )
    args = p.parse_args()

    excl = [s.strip() for s in args.exclude_in_title.split(",") if s.strip()]

    download_reports(
        code=args.code,
        org_id=args.org_id,
        column=args.column,
        category=args.category,
        start_date=args.start_date,
        end_date=args.end_date,
        out_dir=args.out_dir,
        sleep_s=args.sleep,
        dry_run=args.dry_run,
        title_exclude_substrings=excl or None,
        company_name=args.company_name,
    )


if __name__ == "__main__":
    main()
