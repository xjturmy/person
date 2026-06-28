# 测试

## 目录布局

```
.tools/dashboard/tests/
├── test_app.py              # AppTest headless 冒烟（5 大 Tab）
├── test_navigation.py       # goto / consume_intent
├── test_watchlist.py
├── test_technicals.py
├── test_nav_*.py            # 跨 Tab 导航集成
├── gold/                    # 黄金引擎
├── industry/
├── masters/
├── screening/
├── valuation/
├── tabs/
└── ui/
```

测试统一集中在 `.tools/dashboard/tests/`（已无项目根 `tests/` 历史布局）。

## 运行

```bash
cd /Users/gongyong/Desktop/Keyi/preson
source .venv/bin/activate
pytest .tools/dashboard/tests/ -q
```

单模块：
```bash
pytest .tools/dashboard/tests/test_navigation.py -v
pytest .tools/dashboard/tests/valuation/ -q
```

## 测试分层

| 层 | 测什么 | 示例 |
|----|--------|------|
| 引擎 | 纯计算、边界值 | `test_buffett_classifier.py` |
| 数据层 | loader、YAML 读写 | `test_portfolio_write.py` |
| 导航 | session 协议 | `test_navigation.py` |
| UI 冒烟 | Tab 不抛异常 | `test_app.py` |

## 编写约定

1. **引擎测试不 import streamlit**（除非测导航/session）
2. 使用 fixture 或 tmp_path 隔离 YAML 写入
3. DuckDB 测试可用内存库或项目内小样本
4. 导航测试 mock `st.rerun`（`navigation.goto` 已吞异常）

## CI / 本地检查清单

改 Dashboard 后建议跑：

```bash
pytest .tools/dashboard/tests/test_app.py .tools/dashboard/tests/test_navigation.py -q
```

改引擎后跑对应子目录：
```bash
pytest .tools/dashboard/tests/masters/ -q
pytest .tools/dashboard/tests/valuation/ -q
```

改 ingest/抓数后：
```bash
python .tools/db/validate.py
```
