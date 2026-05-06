"""持仓截图 VLM 识别(M4-#3).

用 Anthropic Claude Vision 识别券商 App / Wind / 同花顺持仓截图,
返回与 parse_holdings.parse_text 相同结构的 list[ParsedHolding],
后续 build_candidates / classify / upsert_holdings 全部复用.

依赖:
    anthropic>=0.40
    ANTHROPIC_API_KEY 环境变量(或 ~/.claude 凭据)
"""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from typing import Any

from parse_holdings import ParsedHolding

PROMPT_PATH = Path(__file__).parent / "prompts" / "holdings_extract.md"
MODEL = "claude-sonnet-4-6"

# tool_use 强约束 schema:LLM 必须以工具调用形式返回数组,不能自由发挥
EXTRACT_TOOL = {
    "name": "submit_holdings",
    "description": "提交从持仓截图识别出的持仓数组",
    "input_schema": {
        "type": "object",
        "properties": {
            "holdings": {
                "type": "array",
                "description": "识别出的持仓清单(无内容则空数组)",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": ["string", "null"],
                            "description": "A 股 6 位 / 港股 5 位代码",
                        },
                        "name": {"type": ["string", "null"]},
                        "shares": {"type": ["number", "null"]},
                        "cost_basis": {"type": ["number", "null"]},
                        "last_price": {"type": ["number", "null"]},
                    },
                    "required": ["ticker", "name", "shares", "cost_basis", "last_price"],
                },
            }
        },
        "required": ["holdings"],
    },
}

# 留接缝:测试时可注入 fake client(返回 list[dict])
_client_factory = None


def _load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"提示词模板缺失:{PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def _detect_media_type(image_bytes: bytes) -> str:
    """根据 magic bytes 识别格式。仅支持 png/jpeg/gif/webp(VLM 要求)."""
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("不支持的图片格式 — 仅接受 PNG / JPEG / GIF / WebP")


def _build_vision_message(image_bytes: bytes, prompt: str) -> list[dict]:
    media_type = _detect_media_type(image_bytes)
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": base64.standard_b64encode(image_bytes).decode("ascii"),
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]


def _extract_json_array(text: str) -> list[dict]:
    """从 LLM 响应中提取 JSON 数组(容忍 markdown fence + 前后说明)."""
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        candidate = fence.group(1)
    else:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            raise ValueError(f"响应中找不到 JSON 数组:{text[:200]}")
        candidate = m.group(0)
    return json.loads(candidate)


def _row_to_parsed(row: dict, idx: int) -> ParsedHolding:
    raw = json.dumps(row, ensure_ascii=False)
    ticker = row.get("ticker")
    if ticker is not None:
        ticker = str(ticker).strip()
        if not re.fullmatch(r"\d{5}|\d{6}", ticker):
            return ParsedHolding(
                raw_line=raw,
                name=row.get("name"),
                parse_error=f"ticker 格式异常:{ticker!r}",
            )

    if ticker is None:
        return ParsedHolding(raw_line=raw, parse_error="VLM 未识别到代码")

    def _num(v):
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    return ParsedHolding(
        raw_line=raw,
        ticker=ticker,
        name=row.get("name") or None,
        shares=_num(row.get("shares")),
        cost_basis=_num(row.get("cost_basis")),
        last_price=_num(row.get("last_price")),
    )


def parse_image(image_bytes: bytes, model: str = MODEL) -> list[ParsedHolding]:
    """主入口:截图 bytes → list[ParsedHolding].

    抛错场景:
        - 未设 ANTHROPIC_API_KEY
        - 不支持的图片格式
        - VLM 调用失败
        - 响应非 JSON
    """
    if _client_factory is not None:
        client_or_response = _client_factory(image_bytes)
        # 测试注入支持两种返回:已是 list[dict] 直接转,或仿真 client
        if isinstance(client_or_response, list):
            return [_row_to_parsed(r, i) for i, r in enumerate(client_or_response)]
        client = client_or_response
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY 未设置 — 请在 .env / shell 设置 API key 后重试"
            )
        import anthropic
        client = anthropic.Anthropic()

    prompt = _load_prompt()
    messages = _build_vision_message(image_bytes, prompt)

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=messages,
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": EXTRACT_TOOL["name"]},
    )

    # tool_use 强约束:从 content blocks 找 tool_use,直接拿 input.holdings
    rows: list[dict] | None = None
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            rows = (block.input or {}).get("holdings")
            break

    # 兜底:LLM 仍可能返回纯文本(model 异常时)— 回退原 JSON 提取
    if rows is None:
        text_blocks = [b.text for b in response.content if hasattr(b, "text")]
        text = "\n".join(text_blocks).strip()
        if not text:
            raise ValueError("VLM 响应为空且无 tool_use 块")
        rows = _extract_json_array(text)

    return [_row_to_parsed(r, i) for i, r in enumerate(rows)]


def set_test_client(factory) -> None:
    """单测注入接缝.factory: bytes → list[dict] | mock_client."""
    global _client_factory
    _client_factory = factory


def reset_test_client() -> None:
    global _client_factory
    _client_factory = None
