"""持仓文本解析器(M4-#1).

输入:用户从券商 App / Wind / 同花顺导出的多行文本。
输出:list[ParsedHolding] — 每行一条候选,带 raw_line + parse_error 便于 UI 标红。

支持格式(详见 OPTIMIZATION_M4_决策中心.md):
    600519,100,1500
    600519\t100\t1500
    600519 100 1500
    美的集团 000333 200 65.0
    000333 美的集团 200股 成本65.00
    600519 贵州茅台 100 1500.00 1612.00 11.20% +11200

规则:
    - ticker = 6 位数字(A 股)/ 5 位数字(港股)
    - shares = 第 1 个非 ticker 数字 token(允许小数,通常整数)
    - cost_basis = 第 2 个数字 token
    - last_price = 第 3 个数字 token(可选)
    - 含 % 的 token 视为收益率,丢弃
    - 含中文的 token 视为 name 候选
    - 噪声词("浮盈"/"盈亏"/"账户"等)过滤掉
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TICKER_RE = re.compile(r"(?<!\d)(\d{6}|\d{5})(?!\d)")
NUMBER_RE = re.compile(r"^[+\-]?\d+(\.\d+)?$")
CHINESE_RE = re.compile(r"[一-鿿]")
NOISE_WORDS = {
    "浮盈", "浮亏", "盈亏", "盈利", "亏损", "涨跌", "持仓", "股", "股数",
    "成本", "成本价", "现价", "市价", "市值", "账户", "余额", "可用",
    "持有", "总成本", "市场", "可卖", "买入", "卖出", "成交",
}


@dataclass
class ParsedHolding:
    """单行解析结果。所有字段均允许 None,UI 据此判断 ⚠️/🔴。"""

    raw_line: str
    ticker: str | None = None
    name: str | None = None
    shares: float | None = None
    cost_basis: float | None = None
    last_price: float | None = None
    parse_error: str | None = None

    @property
    def ok(self) -> bool:
        return self.parse_error is None and self.ticker is not None and self.shares is not None

    @property
    def has_min_fields(self) -> bool:
        """ticker + shares + cost_basis 三件齐全才算"完整"."""
        return self.ok and self.cost_basis is not None


def _strip_decorations(line: str) -> str:
    """剥离非数据字符:¥/¥/$ 等货币符号,以及独立的标点。"""
    line = re.sub(r"[¥￥$]", " ", line)
    return line


def _tokenize(line: str) -> list[str]:
    """按 [, \\t \\s] 切分,丢空 token。"""
    return [t for t in re.split(r"[,\t\s]+", line.strip()) if t]


def _classify_token(tok: str) -> tuple[str, str | float | None]:
    """返回 (kind, value)。kind ∈ {ticker, number, name, noise, percent, ignore}."""
    if not tok:
        return "ignore", None

    # ticker(独立的 6 位 / 5 位数字,排除日期 20260505 这种 8 位)
    if re.fullmatch(r"\d{5}|\d{6}", tok):
        return "ticker", tok

    # 含 % 的 token = 收益率,丢
    if "%" in tok:
        return "percent", None

    # 噪声词(可能附数字,如 "200股" / "成本65.00")— 剥离汉字后看剩余
    chinese_part = "".join(CHINESE_RE.findall(tok))
    if chinese_part:
        # 含中文 — 看是不是噪声词或公司名
        non_chinese = re.sub(r"[一-鿿]", "", tok).strip()
        if chinese_part in NOISE_WORDS:
            # 噪声词 — 检查附带数字
            if non_chinese and NUMBER_RE.match(non_chinese):
                return "number", float(non_chinese)
            return "noise", None
        # 不在噪声词表 — 尝试剥离数字后视为 name
        if non_chinese and NUMBER_RE.match(non_chinese):
            # "美的集团200" 之类 — 罕见,优先取数
            return "number", float(non_chinese)
        return "name", chinese_part

    # 纯数字
    cleaned = tok.lstrip("+")  # +11200 → 11200
    if NUMBER_RE.match(cleaned):
        return "number", float(cleaned)

    # 其他(英文公司名等)
    return "ignore", None


def parse_line(line: str) -> ParsedHolding | None:
    """解析单行。返回 None 表示空行/注释行,应跳过。"""
    raw = line
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    cleaned = _strip_decorations(line)
    tokens = _tokenize(cleaned)
    if not tokens:
        return ParsedHolding(raw_line=raw, parse_error="空行")

    ticker: str | None = None
    name: str | None = None
    numbers: list[float] = []

    for tok in tokens:
        kind, value = _classify_token(tok)
        if kind == "ticker" and ticker is None:
            ticker = value  # type: ignore
        elif kind == "number":
            numbers.append(value)  # type: ignore
        elif kind == "name" and name is None:
            name = value  # type: ignore

    if ticker is None:
        return ParsedHolding(
            raw_line=raw,
            name=name,
            parse_error="未识别到 6 位 A 股 / 5 位港股代码",
        )

    if not numbers:
        return ParsedHolding(
            raw_line=raw, ticker=ticker, name=name,
            parse_error="缺数值字段(股数/成本)",
        )

    shares = numbers[0] if len(numbers) >= 1 else None
    cost_basis = numbers[1] if len(numbers) >= 2 else None
    last_price = numbers[2] if len(numbers) >= 3 else None

    return ParsedHolding(
        raw_line=raw,
        ticker=ticker,
        name=name,
        shares=shares,
        cost_basis=cost_basis,
        last_price=last_price,
        parse_error=None if shares is not None else "无法定位股数",
    )


def parse_text(raw: str) -> list[ParsedHolding]:
    """主入口。多行文本 → 候选清单(跳过空行/注释)。"""
    out: list[ParsedHolding] = []
    for line in raw.splitlines():
        ph = parse_line(line)
        if ph is not None:
            out.append(ph)
    return out


# ─── 状态识别(M4-#4)─────────────────────────────────────────────────
# 把解析结果与 companies.csv + portfolio.yaml 比对,决定 UI 颜色档位。

@dataclass
class CandidateStatus:
    """候选状态。code 决定 UI 颜色档,message 是给用户看的一句话。"""

    code: str          # ok_existing / ok_new / not_in_universe / parse_failed / incomplete
    label: str         # 🟡 / 🆕 / ⚠️ / 🔴
    message: str
    default_check: bool  # data_editor 默认是否勾选


def classify(
    ph: ParsedHolding,
    universe_tickers: set[str],
    held_tickers: set[str],
) -> CandidateStatus:
    """用 universe(companies.csv 15 家) + held(已在 portfolio.yaml.holdings)分档。"""
    if ph.parse_error or not ph.ok:
        return CandidateStatus(
            code="parse_failed",
            label="🔴 识别失败",
            message=ph.parse_error or "字段缺失",
            default_check=False,
        )

    if not ph.has_min_fields:
        return CandidateStatus(
            code="incomplete",
            label="🔴 字段不全",
            message="缺成本价(cost_basis),请编辑后再写入",
            default_check=False,
        )

    if ph.ticker not in universe_tickers:
        return CandidateStatus(
            code="not_in_universe",
            label="⚠️ 不在 15 家",
            message="不在 companies.csv,勾选则自动追加",
            default_check=False,
        )

    if ph.ticker in held_tickers:
        return CandidateStatus(
            code="ok_existing",
            label="🟡 更新",
            message="已在 portfolio,默认更新数量/成本",
            default_check=True,
        )

    return CandidateStatus(
        code="ok_new",
        label="🆕 新增",
        message="新加入 holdings",
        default_check=True,
    )


@dataclass
class CandidateRow:
    """打包给 Streamlit data_editor 的一行。"""

    parsed: ParsedHolding
    status: CandidateStatus

    def to_dict(self) -> dict:
        ph = self.parsed
        return {
            "加入": self.status.default_check,
            "代码": ph.ticker or "",
            "公司": ph.name or "",
            "股数": ph.shares,
            "成本价": ph.cost_basis,
            "现价": ph.last_price,
            "状态": self.status.label,
            "备注": self.status.message,
            "原文": ph.raw_line,
        }


def build_candidates(
    parsed: list[ParsedHolding],
    universe_tickers: set[str],
    held_tickers: set[str],
    name_map: dict[str, str] | None = None,
) -> list[CandidateRow]:
    """主装配函数。name_map 提供 ticker → 公司名 兜底(从 companies.csv)."""
    out: list[CandidateRow] = []
    for ph in parsed:
        if name_map and ph.ticker and not ph.name and ph.ticker in name_map:
            ph.name = name_map[ph.ticker]
        out.append(CandidateRow(parsed=ph, status=classify(ph, universe_tickers, held_tickers)))
    return out
