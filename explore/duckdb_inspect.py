#!/usr/bin/env python3
"""只读探测一个 DuckDB 文件:列表、schema、行数、样例。

固化脚本 — 强制 read_only=True,SQL 模板写死,不接受任意 SQL。

用法:
    .venv/bin/python .tools/explore/duckdb_inspect.py <db路径> [表名] [样例行数=5]

不带表名 — 列出所有表 + 各自行数。
带表名     — 打印该表 schema + 前 N 行样例。
"""
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    db_path = Path(sys.argv[1]).resolve()
    table = sys.argv[2] if len(sys.argv) > 2 else None
    sample = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    if not db_path.exists():
        print(f"文件不存在: {db_path}")
        return 2
    if db_path.suffix != ".duckdb":
        print(f"仅支持 .duckdb 文件: {db_path}")
        return 2

    if table is not None and not table.replace("_", "").isalnum():
        print(f"表名只允许字母数字下划线: {table!r}")
        return 2

    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)

    if table is None:
        tables = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY table_name"
        ).fetchall()
        print(f"=== {db_path.name} 共 {len(tables)} 张表 ===")
        for (name,) in tables:
            cnt = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            print(f"  {name:32s} {cnt:>12,d} 行")
        return 0

    schema = con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema='main' AND table_name=? ORDER BY ordinal_position",
        [table],
    ).fetchall()
    if not schema:
        print(f"表不存在: {table}")
        return 2

    cnt = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    print(f"=== {db_path.name}::{table}  ({cnt:,d} 行) ===")
    for col, ty in schema:
        print(f"  {col:32s} {ty}")
    print()
    print(f"--- 前 {sample} 行样例 ---")
    df = con.execute(f'SELECT * FROM "{table}" LIMIT {sample}').df()
    print(df.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
