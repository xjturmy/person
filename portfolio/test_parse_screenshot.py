"""parse_screenshot 离线单测 — 用 set_test_client 注入,不调真 API."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parse_screenshot import (
    _detect_media_type,
    _extract_json_array,
    parse_image,
    reset_test_client,
    set_test_client,
)

errs: list[str] = []


def expect(c: bool, msg: str) -> None:
    print(f"  {'✅' if c else '❌'} {msg}")
    if not c:
        errs.append(msg)


# ─── _detect_media_type ───
print("─── _detect_media_type ───")
expect(_detect_media_type(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100) == "image/png", "PNG 头识别")
expect(_detect_media_type(b"\xff\xd8\xff" + b"\x00" * 100) == "image/jpeg", "JPEG 头识别")
try:
    _detect_media_type(b"<html>")
    expect(False, "应抛错(不支持的格式)")
except ValueError:
    expect(True, "不支持格式抛 ValueError")

# ─── _extract_json_array ───
print("─── _extract_json_array ───")
arr = _extract_json_array('[{"ticker": "600519", "shares": 100}]')
expect(arr == [{"ticker": "600519", "shares": 100}], "纯 JSON")

arr = _extract_json_array('```json\n[{"ticker":"600519"}]\n```')
expect(arr == [{"ticker": "600519"}], "markdown fence 包裹")

arr = _extract_json_array('好的,识别结果如下:\n[{"ticker":"600519"}]\n这是给你的')
expect(arr == [{"ticker": "600519"}], "前后有说明文字")

try:
    _extract_json_array("没有 JSON 数组")
    expect(False, "应抛错")
except ValueError:
    expect(True, "无 JSON 抛 ValueError")

# ─── parse_image 用注入路径(不调 API)───
print("─── parse_image 注入测试 ───")

set_test_client(lambda img_bytes: [
    {"ticker": "600519", "name": "贵州茅台", "shares": 100, "cost_basis": 1500.0, "last_price": 1612.0},
    {"ticker": "000333", "name": "美的集团", "shares": 200, "cost_basis": 65.0, "last_price": None},
    {"ticker": "INVALID", "name": "X", "shares": 100, "cost_basis": 10},
    {"ticker": None, "name": None, "shares": None, "cost_basis": None, "last_price": None},
])

result = parse_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
expect(len(result) == 4, f"4 条返回(得到 {len(result)})")
expect(result[0].ticker == "600519" and result[0].shares == 100.0, "第 1 行 OK")
expect(result[1].last_price is None, "null 字段保留 None")
expect(result[2].parse_error and "格式异常" in result[2].parse_error, "INVALID ticker 标记错误")
expect(result[3].parse_error and "未识别" in result[3].parse_error, "全 null 标记错误")

reset_test_client()

# ─── tool_use mock client(确保 tool_use 路径走通)───
print("─── tool_use 强 schema mock ───")


class _FakeBlock:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeResponse:
    def __init__(self, blocks):
        self.content = blocks


class _FakeClient:
    def __init__(self, blocks):
        self._blocks = blocks
        self.last_kwargs = None

    class _Messages:
        def __init__(self, parent):
            self.parent = parent

        def create(self, **kw):
            self.parent.last_kwargs = kw
            return _FakeResponse(self.parent._blocks)

    @property
    def messages(self):
        return self._Messages(self)


tool_use_block = _FakeBlock(
    "tool_use",
    input={"holdings": [
        {"ticker": "600519", "name": "贵州茅台", "shares": 100,
         "cost_basis": 1500.0, "last_price": 1612.0},
    ]},
)
fake_client = _FakeClient([tool_use_block])
set_test_client(lambda _b: fake_client)

result = parse_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
expect(len(result) == 1, "tool_use 1 条")
expect(result[0].ticker == "600519", "ticker 600519")

# 验证 tools/tool_choice 实际被传入
expect("tools" in fake_client.last_kwargs, "create() 收到 tools=")
expect(fake_client.last_kwargs.get("tool_choice", {}).get("name") == "submit_holdings",
       "tool_choice.name=submit_holdings")
reset_test_client()

# ─── 文本兜底(模拟 model 不返回 tool_use)───
print("─── tool_use 缺失时回退文本 JSON ───")
text_block = _FakeBlock("text", text='[{"ticker":"000333","name":"美的","shares":200,"cost_basis":65}]')
fake_client2 = _FakeClient([text_block])
set_test_client(lambda _b: fake_client2)
result = parse_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
expect(len(result) == 1 and result[0].ticker == "000333", "文本回退路径")
reset_test_client()

print()
if errs:
    print(f"❌ 失败 {len(errs)} 项")
    for e in errs:
        print(f"  - {e}")
    sys.exit(1)
print("✅ parse_screenshot 全部用例通过")
