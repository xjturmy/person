"""理杏仁 API Token 解析（供 generate_wide_valuation / batch_update_recent_wide 共用）。"""

from __future__ import annotations

import os
import re
from pathlib import Path


def _kb_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _token_from_account_md(path: Path) -> str:
    """从「03_行业与宏观/账号密码.md」中解析 `开放API Token:` / `Token:` 行。"""
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(?:开放API\s*)?[Tt]oken\s*[:：]\s*(.*)$", line)
        if not m:
            continue
        v = m.group(1).strip()
        if not v:
            continue
        # 跳过明显占位说明
        if v.startswith("（") or v.startswith("(") or "请" in v[:4]:
            continue
        return v
    return ""


def resolve_lixinger_token(cli_token: str | None) -> str:
    """优先 CLI，其次 LIXINGER_TOKEN，再次 LIXINGER_TOKEN_FILE / .lixinger_token，最后 账号密码.md。"""
    t = (cli_token or os.getenv("LIXINGER_TOKEN") or "").strip()
    if t:
        return t
    root = _kb_root()
    for raw in (
        (os.getenv("LIXINGER_TOKEN_FILE") or "").strip(),
        str(root / ".lixinger_token"),
    ):
        if not raw:
            continue
        p = Path(raw).expanduser()
        if not p.is_file():
            continue
        try:
            line = p.read_text(encoding="utf-8").splitlines()[0].strip()
        except OSError:
            continue
        if line:
            return line
    t2 = _token_from_account_md(root / "03_行业与宏观" / "账号密码.md")
    if t2:
        return t2
    return ""
