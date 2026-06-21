"""lynch_extras.py — 林奇评分体系辅助函数 (v2.5 L2-L5)

提供 4 个函数，对应 lynch.yaml 中 4 条优化规则：

  L2: insider_proxy_score()         — 内部人净买入代理（股东户数变动）
  L3: institutional_holding_proxy() — 机构持仓比例代理（主力资金流向）
  L4: peg_curve_grade()             — PEG 曲线规则化（近 5 年低估占比）
  L5: quarterly_continuity_score()  — 季度营收连续性评分

所有 AkShare 相关函数：
  - 接口失败时优雅降级，返回 None（调用方跳过该项打分）
  - verified=False，需在 UI 显示"未校验"标注

依赖：
  - akshare（可选，缺失时自动降级）
  - duckdb（读 preson.duckdb）
  - 同目录 peg_curve.build_peg_series
  - 同目录 lynch_classifier.quarterly_continuity
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "data" / "preson.duckdb"


# ──────────────────────────────────────────────────────────────────
# 公共 Result 结构
# ──────────────────────────────────────────────────────────────────

@dataclass
class LynchExtraResult:
    """单条辅助指标结果。"""
    score: Optional[int]         # None = 数据不可用，跳过打分
    value: Optional[float]       # 原始数值（供 UI 展示）
    verified: bool               # False = AkShare 代理 / 手动
    note: str                    # 说明文字（UI 展示）
    source: str                  # 数据来源标识


# ──────────────────────────────────────────────────────────────────
# L2: 内部人净买入代理
# ──────────────────────────────────────────────────────────────────

def insider_proxy_score(ticker: str, window_months: int = 6) -> LynchExtraResult:
    """L2 — 内部人净买入代理（股东户数变动）。

    逻辑：
      用 AkShare stock_zh_a_gdhs（股东户数变动）代理。
      股东户数持续收缩（近 6 个月变动 < -3%）≈ 筹码集中 ≈ 内部人买入信号。

    评分：
      - 变动 < -3%  → 2 分（代理"内部人净买入"）
      - 变动 ≥ 0%   → 0 分（户数未缩减）
      - 数据不可用  → None（跳过）

    Args:
        ticker: A 股代码（如 '600519'）
        window_months: 观察窗口（月），默认 6

    Returns:
        LynchExtraResult(score, value, verified=False, note, source)
    """
    try:
        import akshare as ak  # type: ignore
    except ImportError:
        return LynchExtraResult(
            score=None,
            value=None,
            verified=False,
            note="AkShare 未安装，insider_proxy 不可用",
            source="akshare.stock_zh_a_gdhs",
        )

    try:
        df = ak.stock_zh_a_gdhs(symbol=ticker)
        if df is None or df.empty:
            raise ValueError("空数据")

        # 标准化列名（akshare 返回列名可能因版本而异）
        df.columns = [str(c).strip() for c in df.columns]

        # 寻找报告日期列和股东户数列
        date_col = next(
            (c for c in df.columns if "日期" in c or "date" in c.lower()), None
        )
        count_col = next(
            (c for c in df.columns if "户数" in c or "股东" in c), None
        )

        if date_col is None or count_col is None:
            raise ValueError(f"列名识别失败: {df.columns.tolist()}")

        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col]).sort_values(date_col)

        # 取最近 window_months 内的数据
        cutoff = pd.Timestamp.now() - pd.DateOffset(months=window_months)
        recent = df[df[date_col] >= cutoff].copy()

        if len(recent) < 2:
            # 数据不足，退回全量首尾对比
            if len(df) < 2:
                raise ValueError("数据量不足（< 2 行）")
            first_val = float(df[count_col].iloc[0])
            last_val = float(df[count_col].iloc[-1])
        else:
            first_val = float(recent[count_col].iloc[0])
            last_val = float(recent[count_col].iloc[-1])

        if first_val <= 0:
            raise ValueError(f"股东户数为 0 或负数: {first_val}")

        change_ratio = (last_val - first_val) / first_val  # 负 = 户数收缩

        if change_ratio < -0.03:
            score = 2
            note = f"股东户数近 {window_months}m 变动 {change_ratio:.1%}（收缩），代理内部人买入"
        else:
            score = 0
            note = f"股东户数近 {window_months}m 变动 {change_ratio:.1%}（未收缩）"

        return LynchExtraResult(
            score=score,
            value=round(change_ratio, 4),
            verified=False,
            note=note,
            source="akshare.stock_zh_a_gdhs",
        )

    except Exception as exc:
        return LynchExtraResult(
            score=None,
            value=None,
            verified=False,
            note=f"股东户数接口失败（{exc}），insider_proxy 不可用",
            source="akshare.stock_zh_a_gdhs",
        )


# ──────────────────────────────────────────────────────────────────
# L3: 机构持仓比例代理
# ──────────────────────────────────────────────────────────────────

def institutional_holding_proxy(ticker: str) -> LynchExtraResult:
    """L3 — 机构持仓比例代理（主力资金净流入占比）。

    逻辑：
      用 AkShare stock_main_fund_flow 代理主力资金净流入占成交额比例。
      林奇偏好"被机构忽视"的低关注度股票。

      代理规则：
        - 主力净流入/成交额 < 0（主力净流出）→ 机构低关注 → 1 分
        - 主力净流入/成交额 >= 0              → 机构高关注 → 0 分
        - 数据不可用                          → None

    Note:
      这是"机构关注度"的代理，不等于机构持股比例；
      verified=False，权重 0.5（见 lynch.yaml）。

    Args:
        ticker: A 股代码（如 '600519'）

    Returns:
        LynchExtraResult(score, value, verified=False, note, source)
    """
    try:
        import akshare as ak  # type: ignore
    except ImportError:
        return LynchExtraResult(
            score=None,
            value=None,
            verified=False,
            note="AkShare 未安装，institutional_proxy 不可用",
            source="akshare.stock_main_fund_flow",
        )

    try:
        df = ak.stock_main_fund_flow(symbol=ticker, market="北京")
    except Exception:
        # 尝试不带 market 参数
        try:
            df = ak.stock_main_fund_flow(symbol=ticker)
        except Exception as exc2:
            return LynchExtraResult(
                score=None,
                value=None,
                verified=False,
                note=f"主力资金流向接口失败（{exc2}），institutional_proxy 不可用",
                source="akshare.stock_main_fund_flow",
            )

    try:
        if df is None or df.empty:
            raise ValueError("空数据")

        df.columns = [str(c).strip() for c in df.columns]

        # 寻找净流入金额列
        net_col = next(
            (c for c in df.columns if "净流入" in c or "net" in c.lower()), None
        )
        total_col = next(
            (c for c in df.columns if "成交额" in c or "total" in c.lower() or "流入" == c), None
        )

        if net_col is None:
            raise ValueError(f"找不到净流入列: {df.columns.tolist()}")

        # 取最近一行
        row = df.iloc[-1]
        net_inflow = float(row[net_col])

        # 计算占比（如有成交额列）
        ratio = None
        if total_col and total_col != net_col:
            try:
                total = float(row[total_col])
                if total > 0:
                    ratio = net_inflow / total
            except Exception:
                pass

        # 主力净流出 = 机构低关注 = 林奇偏好
        if net_inflow < 0:
            score = 1
            note = f"主力净流出 {net_inflow/1e8:.2f}亿（代理机构低关注），林奇偏好"
        else:
            score = 0
            note = f"主力净流入 {net_inflow/1e8:.2f}亿（代理机构高关注）"

        return LynchExtraResult(
            score=score,
            value=ratio if ratio is not None else round(net_inflow, 2),
            verified=False,
            note=note,
            source="akshare.stock_main_fund_flow",
        )

    except Exception as exc:
        return LynchExtraResult(
            score=None,
            value=None,
            verified=False,
            note=f"主力资金流向解析失败（{exc}），institutional_proxy 不可用",
            source="akshare.stock_main_fund_flow",
        )


# ──────────────────────────────────────────────────────────────────
# L4: PEG 曲线规则化
# ──────────────────────────────────────────────────────────────────

def peg_curve_grade(
    ticker: str,
    years: int = 5,
    db_path: Optional[Path] = None,
) -> LynchExtraResult:
    """L4 — 近 N 年 PEG 曲线中 PEG < 1.0 占比。

    规则（来自 lynch.yaml peg_curve_grade）：
      - PEG < 1.0 天数 / 总有效天数 >= 60% → 1 分
      - < 60%                                → 0 分
      - 数据不足（有效行 < 30）              → None

    使用 peg_curve.build_peg_series 读 DuckDB。

    Args:
        ticker: A 股代码
        years:  回溯年数，默认 5
        db_path: DuckDB 路径（None = 使用默认 preson.duckdb）

    Returns:
        LynchExtraResult(score, value=比例, verified=True, note, source)
    """
    try:
        # 延迟导入，避免循环依赖
        sys.path.insert(0, str(Path(__file__).parent))
        from valuation.peg_curve import build_peg_series  # type: ignore

        df = build_peg_series(ticker, db_path=db_path or DB_PATH, lookback_years=years)

        if df.empty:
            return LynchExtraResult(
                score=None,
                value=None,
                verified=True,
                note="PEG 数据为空（DuckDB 无 valuation/growth 数据）",
                source="peg_curve.build_peg_series",
            )

        valid = df.dropna(subset=["peg"]).copy()
        valid["peg"] = pd.to_numeric(valid["peg"], errors="coerce")
        valid = valid.dropna(subset=["peg"])

        if len(valid) < 30:
            return LynchExtraResult(
                score=None,
                value=None,
                verified=True,
                note=f"有效 PEG 行数不足（{len(valid)} < 30），跳过",
                source="peg_curve.build_peg_series",
            )

        below_1_count = int((valid["peg"] < 1.0).sum())
        total_count = len(valid)
        ratio = below_1_count / total_count

        score = 1 if ratio >= 0.60 else 0

        return LynchExtraResult(
            score=score,
            value=round(ratio, 4),
            verified=True,
            note=(
                f"近 {years}y PEG<1.0 占比 {ratio:.1%}"
                f"（{below_1_count}/{total_count} 天）"
                + ("，≥60% → +1分" if score == 1 else "，< 60% → 0分")
            ),
            source="peg_curve.build_peg_series",
        )

    except Exception as exc:
        return LynchExtraResult(
            score=None,
            value=None,
            verified=True,
            note=f"PEG 曲线计算失败（{exc}）",
            source="peg_curve.build_peg_series",
        )


# ──────────────────────────────────────────────────────────────────
# L5: 季度营收连续性评分
# ──────────────────────────────────────────────────────────────────

def quarterly_continuity_score(
    ticker: str,
    n_quarters: int = 8,
    db_path: Optional[Path] = None,
) -> LynchExtraResult:
    """L5 — 季度营收增速连续性评分。

    规则（来自 lynch.yaml quarterly_continuity_score）：
      - 8 季中 hits_10（单季 YoY > 10%）≥ 7 → 2 分
      - 8 季中 hits_10 ≥ 6                   → 1 分
      - hits_10 < 6                           → 0 分
      - 数据不足（n_quarters < 6）            → None

    使用 lynch_classifier.quarterly_continuity 计算。

    适用类型：fast_grower / stalwart。
    slow_grower / cyclical / turnaround / asset_play 建议调用方跳过。

    Args:
        ticker: A 股代码
        n_quarters: 考察季度数，默认 8
        db_path: DuckDB 路径（None = 使用默认 preson.duckdb）

    Returns:
        LynchExtraResult(score, value=hits_10pct, verified=True, note, source)
    """
    db = Path(db_path) if db_path else DB_PATH

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from masters.lynch.classifier import quarterly_continuity  # type: ignore

        if not db.exists():
            return LynchExtraResult(
                score=None,
                value=None,
                verified=True,
                note=f"DuckDB 文件不存在: {db}",
                source="lynch_classifier.quarterly_continuity",
            )

        con = duckdb.connect(str(db), read_only=True)
        try:
            result = quarterly_continuity(con, ticker=ticker, n_quarters=n_quarters)
        finally:
            con.close()

        if result.n_quarters < 6:
            return LynchExtraResult(
                score=None,
                value=float(result.n_quarters),
                verified=True,
                note=f"季度数据不足（{result.n_quarters} 季 < 6），跳过",
                source="lynch_classifier.quarterly_continuity",
            )

        hits = result.hits_10pct

        if hits >= 7:
            score = 2
            note = f"8季 hits_10={hits}（≥7）→ +2分"
        elif hits >= 6:
            score = 1
            note = f"8季 hits_10={hits}（≥6）→ +1分"
        else:
            score = 0
            note = f"8季 hits_10={hits}（<6）→ 0分"

        return LynchExtraResult(
            score=score,
            value=float(hits),
            verified=True,
            note=note,
            source="lynch_classifier.quarterly_continuity",
        )

    except Exception as exc:
        return LynchExtraResult(
            score=None,
            value=None,
            verified=True,
            note=f"quarterly_continuity 计算失败（{exc}）",
            source="lynch_classifier.quarterly_continuity",
        )


# ──────────────────────────────────────────────────────────────────
# CLI 冒烟测试（直接运行时展示 4 家公司结果）
# ──────────────────────────────────────────────────────────────────

_SMOKE_TEST_COMPANIES = [
    ("600519", "贵州茅台",   "stalwart"),
    ("600036", "招商银行",   "slow_grower"),
    ("02097",  "蜜雪集团",   "fast_grower"),
    ("603232", "三美股份",   "cyclical"),
]

if __name__ == "__main__":
    print("=" * 60)
    print("Lynch Extras — 4 公司冒烟测试")
    print("=" * 60)

    for ticker, name, cls in _SMOKE_TEST_COMPANIES:
        print(f"\n▸ {name} ({ticker}) [{cls}]")

        r_insider = insider_proxy_score(ticker)
        print(f"  L2 insider_proxy  : score={r_insider.score!r:5}  value={r_insider.value!r}  | {r_insider.note[:60]}")

        r_inst = institutional_holding_proxy(ticker)
        print(f"  L3 inst_holding   : score={r_inst.score!r:5}  value={r_inst.value!r}  | {r_inst.note[:60]}")

        r_peg = peg_curve_grade(ticker)
        print(f"  L4 peg_curve      : score={r_peg.score!r:5}  value={r_peg.value!r}  | {r_peg.note[:60]}")

        r_qc = quarterly_continuity_score(ticker)
        print(f"  L5 qtly_cont      : score={r_qc.score!r:5}  value={r_qc.value!r}  | {r_qc.note[:60]}")
