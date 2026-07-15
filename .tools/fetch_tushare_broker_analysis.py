#!/usr/bin/env python3
"""
使用 Tushare Pro 抓取券商研报数据，并写入公司档案库的券商分析模块。

默认目标：
- 公司：新华保险（601336.SH）
- 输出目录：02_公司档案库/01_新华保险/26_券商分析
"""

from __future__ import annotations

import argparse
import csv
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

import tushare as ts


RATING_ORDER = {
    "卖出": 1,
    "减持": 2,
    "中性": 3,
    "持有": 3,
    "增持": 4,
    "买入": 5,
    "强烈推荐": 6,
}


def _kb_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _to_ymd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


def _to_iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d")


def _token_from_account_md(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""

    patterns = [
        r"^Tushare(?:\s*Pro)?\s*Token\s*[:：]\s*(.+)$",
        r"^TS(?:_PRO)?_TOKEN\s*[:：=]\s*(.+)$",
        r"^通联?Tushare\s*Token\s*[:：]\s*(.+)$",
    ]
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        for p in patterns:
            m = re.match(p, line, flags=re.IGNORECASE)
            if not m:
                continue
            token = m.group(1).strip()
            if token:
                return token
    return ""


def resolve_tushare_token(cli_token: str | None) -> str:
    token = (cli_token or os.getenv("TUSHARE_TOKEN") or "").strip()
    if token:
        return token

    root = _kb_root()
    token_file = (os.getenv("TUSHARE_TOKEN_FILE") or "").strip()
    candidates = [Path(token_file).expanduser()] if token_file else []
    candidates.append(root / ".tushare_token")

    for p in candidates:
        if not p.is_file():
            continue
        try:
            first_line = p.read_text(encoding="utf-8").splitlines()[0].strip()
        except OSError:
            continue
        if first_line:
            return first_line

    return _token_from_account_md(root / "03_行业与宏观" / "账号密码.md")


def _pick(row: dict[str, Any], *cols: str) -> Any:
    for c in cols:
        if c in row and row[c] not in (None, ""):
            return row[c]
    return ""


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _rating_score(text: str) -> int | None:
    t = str(text or "").strip()
    if not t:
        return None
    for k, v in RATING_ORDER.items():
        if k in t:
            return v
    return None


@dataclass
class Row:
    dt: datetime
    org: str
    rating: str
    target: float | None
    eps1: float | None
    eps2: float | None
    eps3: float | None
    raw: dict[str, Any]


def _extract_rows(df) -> list[Row]:
    out: list[Row] = []
    for _, rec in df.iterrows():
        row = rec.to_dict()
        date_raw = _pick(row, "report_date", "ann_date", "create_date")
        dt = _parse_date(str(date_raw))
        if dt is None:
            continue
        org = str(_pick(row, "org_name", "institution", "name")).strip()
        rating = str(_pick(row, "rating", "rate", "rate_name")).strip()
        target = _to_float(_pick(row, "target_price", "tp", "target"))

        eps1 = _to_float(_pick(row, "eps", "eps1", "eps_1y"))
        eps2 = _to_float(_pick(row, "eps2", "eps_2y"))
        eps3 = _to_float(_pick(row, "eps3", "eps_3y"))

        out.append(
            Row(
                dt=dt,
                org=org,
                rating=rating,
                target=target,
                eps1=eps1,
                eps2=eps2,
                eps3=eps3,
                raw=row,
            )
        )
    out.sort(key=lambda x: (x.org, x.dt))
    return out


def _latest_close(pro, ts_code: str) -> float | None:
    end = datetime.now()
    start = end - timedelta(days=30)
    is_hk = ts_code.upper().endswith(".HK")
    if is_hk:
        daily = pro.hk_daily(ts_code=ts_code, start_date=_to_ymd(start), end_date=_to_ymd(end))
    else:
        daily = pro.daily(ts_code=ts_code, start_date=_to_ymd(start), end_date=_to_ymd(end))
    if daily is None or daily.empty:
        return None
    try:
        daily = daily.sort_values(by="trade_date", ascending=False)
    except Exception:
        pass
    close = _to_float(daily.iloc[0].get("close"))
    return close


def _build_target_file(rows: list[Row], latest_close: float | None, out_path: Path) -> None:
    header = [
        "报告日期",
        "券商名称",
        "评级",
        "当前目标价",
        "前次目标价",
        "调整方向",
        "最新收盘价",
        "目标价空间",
        "核心观点",
    ]
    records: list[list[Any]] = []

    # 逆序，输出最近记录在上方
    prev_target_by_org: dict[str, float | None] = {}
    for r in rows:
        prev_target_by_org.setdefault(r.org, None)

    for r in rows:
        pass

    # 先按正序构建“前次目标价”
    expanded: list[tuple[Row, float | None]] = []
    last_target: dict[str, float | None] = {}
    for r in rows:
        expanded.append((r, last_target.get(r.org)))
        if r.target is not None:
            last_target[r.org] = r.target

    for r, prev_target in reversed(expanded):
        direction = "维持"
        if r.target is not None and prev_target is not None:
            if r.target > prev_target:
                direction = "上调"
            elif r.target < prev_target:
                direction = "下调"
        elif r.target is not None and prev_target is None:
            direction = "首次覆盖"

        space = ""
        if r.target is not None and latest_close:
            try:
                space = f"{(r.target / latest_close - 1.0) * 100:.2f}%"
            except ZeroDivisionError:
                space = ""

        records.append(
            [
                _to_iso(r.dt),
                r.org,
                r.rating,
                "" if r.target is None else f"{r.target:.2f}",
                "" if prev_target is None else f"{prev_target:.2f}",
                direction,
                "" if latest_close is None else f"{latest_close:.2f}",
                space,
                str(_pick(r.raw, "title", "report_title", "remark")),
            ]
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(records)


def _build_consensus_file(rows: list[Row], out_path: Path) -> None:
    header = [
        "统计日期",
        "机构覆盖数",
        "EPS_FY1",
        "EPS_FY2",
        "EPS_FY3",
        "净利润_亿元_FY1",
        "净利润_亿元_FY2",
        "净利润_亿元_FY3",
        "营收_亿元_FY1",
        "营收_亿元_FY2",
        "营收_亿元_FY3",
        "EPS分歧度",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        with out_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(header)
        return

    latest_day = max(r.dt for r in rows)
    latest_rows = [r for r in rows if r.dt == latest_day]
    covered_org = {r.org for r in latest_rows if r.org}

    eps1_vals = [x for x in (r.eps1 for r in latest_rows) if x is not None]
    eps2_vals = [x for x in (r.eps2 for r in latest_rows) if x is not None]
    eps3_vals = [x for x in (r.eps3 for r in latest_rows) if x is not None]

    eps1_std = ""
    if len(eps1_vals) >= 2:
        eps1_std = f"{pstdev(eps1_vals):.4f}"

    row = [
        _to_iso(latest_day),
        len(covered_org),
        "" if not eps1_vals else f"{mean(eps1_vals):.4f}",
        "" if not eps2_vals else f"{mean(eps2_vals):.4f}",
        "" if not eps3_vals else f"{mean(eps3_vals):.4f}",
        "",
        "",
        "",
        "",
        "",
        "",
        eps1_std,
    ]
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerow(row)


def _build_revision_file(rows: list[Row], out_path: Path) -> None:
    header = [
        "统计日期",
        "近30天EPS上修家数",
        "近30天EPS下修家数",
        "近90天EPS上修家数",
        "近90天EPS下修家数",
        "一致预期变化幅度",
        "评级净上调比例",
        "预期分歧度",
        "备注",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        with out_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(header)
        return

    by_org: dict[str, list[Row]] = {}
    for r in rows:
        by_org.setdefault(r.org or "未知机构", []).append(r)

    latest_day = max(r.dt for r in rows)
    cutoff_30 = latest_day - timedelta(days=30)
    cutoff_90 = latest_day - timedelta(days=90)

    up30 = down30 = up90 = down90 = 0
    rating_up = rating_down = 0
    newest_eps: list[float] = []
    older_eps: list[float] = []

    for org_rows in by_org.values():
        org_rows.sort(key=lambda x: x.dt)
        prev: Row | None = None
        for cur in org_rows:
            if cur.eps1 is not None:
                if cur.dt >= cutoff_30:
                    newest_eps.append(cur.eps1)
                elif cutoff_90 <= cur.dt < cutoff_30:
                    older_eps.append(cur.eps1)

            if prev is not None:
                if cur.eps1 is not None and prev.eps1 is not None:
                    if cur.dt >= cutoff_90:
                        if cur.eps1 > prev.eps1:
                            up90 += 1
                            if cur.dt >= cutoff_30:
                                up30 += 1
                        elif cur.eps1 < prev.eps1:
                            down90 += 1
                            if cur.dt >= cutoff_30:
                                down30 += 1

                s1 = _rating_score(prev.rating)
                s2 = _rating_score(cur.rating)
                if s1 is not None and s2 is not None and cur.dt >= cutoff_90:
                    if s2 > s1:
                        rating_up += 1
                    elif s2 < s1:
                        rating_down += 1
            prev = cur

    consensus_change = ""
    if newest_eps and older_eps:
        old_mean = mean(older_eps)
        if old_mean != 0:
            consensus_change = f"{(mean(newest_eps) / old_mean - 1.0) * 100:.2f}%"

    net_upgrade_ratio = ""
    if rating_up + rating_down > 0:
        net_upgrade_ratio = f"{(rating_up - rating_down) / (rating_up + rating_down):.4f}"

    divergence = ""
    if len(newest_eps) >= 2:
        divergence = f"{pstdev(newest_eps):.4f}"

    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerow(
            [
                _to_iso(latest_day),
                up30,
                down30,
                up90,
                down90,
                consensus_change,
                net_upgrade_ratio,
                divergence,
                "基于 report_rc 历史序列近似计算",
            ]
        )


def _write_summary_md(rows: list[Row], out_path: Path, company_name: str = "") -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    label = company_name or "未知公司"
    if not rows:
        content = "\n".join(
            [
                f"# 券商观点摘要（{label}）",
                "",
                "## 本期结论",
                "",
                "- 结论等级：暂无数据",
                "- 主要共识：暂无可用研报数据",
                "- 主要分歧：暂无可用研报数据",
                "",
                "## 数据说明",
                "",
                "- 当前脚本已运行，但在指定时间范围内未返回 report_rc 数据。",
            ]
        )
        out_path.write_text(content, encoding="utf-8")
        return

    latest_day = max(r.dt for r in rows)
    latest = [r for r in rows if r.dt == latest_day]
    rating_texts = [r.rating for r in latest if r.rating]
    target_prices = [r.target for r in latest if r.target is not None]
    coverage = len({r.org for r in latest if r.org})

    avg_target = f"{mean(target_prices):.2f}" if target_prices else "N/A"
    rating_stat = ", ".join(sorted(set(rating_texts))) if rating_texts else "N/A"
    lines = [
        f"# 券商观点摘要（{label}）",
        "",
        "## 本期结论",
        "",
        "- 结论等级：自动生成，需人工复核",
        f"- 主要共识：{_to_iso(latest_day)} 共 {coverage} 家机构覆盖，主要评级分布为 {rating_stat}。",
        f"- 主要分歧：目标价均值约 {avg_target}，建议结合历史分位判断分歧程度。",
        "",
        "## 一、观点共识",
        "",
        "- 一致预期与评级信息已写入对应 CSV。",
        "",
        "## 二、观点分歧",
        "",
        "- 分歧度使用 EPS 标准差近似度量，详见 03_预期修正与分歧跟踪.csv。",
        "",
        "## 三、与基本面核验",
        "",
        "- 与 `02_盈利分析/` 核验：建议对照净利润增速与 EPS 修正方向。",
        "- 与 `03_成长性分析/` 核验：建议对照营收预测与订单/保费增长趋势。",
        "- 与 `01_估值分析/` 核验：建议对照目标价空间与当前估值分位。",
        "",
        "## 四、纳入投资决策",
        "",
        "- 对应 `05_投资决策/` 策略分歧审视与综合决策的影响：待人工补充。",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取 Tushare 券商分析数据")
    parser.add_argument("--token", default="", help="Tushare Pro token")
    parser.add_argument("--ts-code", default="601336.SH", help="股票代码，默认 601336.SH")
    parser.add_argument("--company-name", default="", help="公司名称，用于输出文件标题")
    parser.add_argument(
        "--start-date",
        default=(datetime.now() - timedelta(days=365 * 2)).strftime("%Y%m%d"),
        help="开始日期，格式 YYYYMMDD，默认近2年",
    )
    parser.add_argument(
        "--end-date",
        default=datetime.now().strftime("%Y%m%d"),
        help="结束日期，格式 YYYYMMDD，默认今天",
    )
    parser.add_argument(
        "--output-dir",
        default="02_companies/01_新华保险/04_券商分析",
        help="输出目录（相对知识库根目录）",
    )
    args = parser.parse_args()

    token = resolve_tushare_token(args.token)
    if not token:
        print("未找到 Tushare Token。请通过 --token 或环境变量 TUSHARE_TOKEN 提供。")
        return 2

    pro = ts.pro_api(token)
    try:
        df = pro.report_rc(ts_code=args.ts_code, start_date=args.start_date, end_date=args.end_date)
    except Exception as exc:
        print(f"拉取 report_rc 失败：{exc}")
        return 1

    output_dir = (_kb_root() / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = _extract_rows(df if df is not None else [])
    latest_close = None
    try:
        latest_close = _latest_close(pro, args.ts_code)
    except Exception:
        latest_close = None

    company_name = args.company_name or args.ts_code
    _build_consensus_file(rows, output_dir / "01_盈利预测与一致预期.csv")
    _build_target_file(rows, latest_close, output_dir / "02_评级与目标价.csv")
    _build_revision_file(rows, output_dir / "03_预期修正与分歧跟踪.csv")
    _write_summary_md(rows, output_dir / "04_券商观点摘要.md", company_name=company_name)

    print(f"完成：{args.ts_code}（{company_name}）券商分析数据已写入 {output_dir}")
    print(f"report_rc 行数：{0 if df is None else len(df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
