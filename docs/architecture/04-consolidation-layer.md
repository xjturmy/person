# 整合层

路径：`.tools/data_consolidator/`

## 模块

| 脚本 | 职责 |
|------|------|
| `consolidate.py` | 从各公司原始抓取目录 → `历史数据/*.csv` + `摘要.md` |
| `update_pipeline.py` | 端到端：抓数 → 整合 → 验证 |
| `cross_analysis.py` | 跨公司全景对比（估值/盈利/规模/安全性）→ `02_companies/_汇总/` |

## consolidate 输入/输出

**输入**：
```
02_companies/{folder}/01_基本面数据/
  ├── 01_估值分析/
  ├── 02_盈利分析/
  ├── 03_成长性分析/
  ├── 04_现金流分析/
  └── 05_安全性分析/
```

**输出**：
```
02_companies/{folder}/01_基本面数据/
  ├── 历史数据/估值.csv | 盈利.csv | 成长.csv | 现金流.csv | 安全性.csv
  └── 摘要.md
```

## 与 ingest 的衔接

```
consolidate.py  →  历史数据/*.csv  →  ingest.py  →  preson.duckdb
```

整合层只写 CSV/Markdown，不写 DuckDB。DuckDB 重建由 `db/ingest.py` 负责。

## cross_analysis 输出

`02_companies/_汇总/`：
- `全景.md` — 一屏看全所有公司
- `估值对比.csv` / `盈利对比.csv` / 等

## 使用场景

| 场景 | 命令 |
|------|------|
| 仅重新整合（不抓新数据） | `python .tools/data_consolidator/consolidate.py` |
| 整合单家 | `consolidate.py --only=新华保险` |
| 完整流水线 | `python .tools/data_consolidator/update_pipeline.py` |
| 跨公司对比 | `python .tools/data_consolidator/cross_analysis.py` |
