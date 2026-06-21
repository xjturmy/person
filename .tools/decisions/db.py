"""决策日志 DuckDB 数据层。

设计要点:
- 独立文件 data/decisions.duckdb,与主库 preson.duckdb 解耦,
  避免与 MCP server / Streamlit dashboard 的 read-only 锁冲突。
- 关键字段:三件事(rationale / thesis_5y / risks)+ 数据快照(capture-on-write)
- 快照存两份:扁平字段(snapshot_pe / pe_pct / fscore 等)便于 SQL 查询;
  完整 JSON(snapshot_json)避免后续新增指标时改表结构。

表结构:
    decisions(id PK, ticker, date, action, weight_change, price,
              rationale, thesis_5y, risks, tags,
              snapshot_pe, snapshot_pb, snapshot_pe_pct_10y,
              snapshot_fscore, snapshot_roe, snapshot_json,
              created_at)

CRUD:
    init_db()                 — 幂等建表
    insert(...)               — 新增一条决策
    list_all() / list_by_ticker(t)
    get(id) / update(id, **) / delete(id)
"""
from __future__ import annotations

import json
from datetime import date as _date, datetime
from pathlib import Path
from typing import Any, Optional

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "decisions.duckdb"

ACTIONS = ("买入", "加仓", "减仓", "清仓", "观察")

DDL = """
CREATE SEQUENCE IF NOT EXISTS decisions_id_seq START 1;

CREATE TABLE IF NOT EXISTS decisions (
    id                    INTEGER PRIMARY KEY DEFAULT nextval('decisions_id_seq'),
    ticker                VARCHAR NOT NULL,
    folder                VARCHAR,
    date                  DATE    NOT NULL,
    action                VARCHAR NOT NULL,
    weight_change         DOUBLE,
    price                 DOUBLE,
    rationale             VARCHAR,
    thesis_5y             VARCHAR,
    risks                 VARCHAR,
    tags                  VARCHAR,
    snapshot_pe           DOUBLE,
    snapshot_pb           DOUBLE,
    snapshot_pe_pct_10y   DOUBLE,
    snapshot_fscore       INTEGER,
    snapshot_roe          DOUBLE,
    snapshot_json         VARCHAR,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(DB_PATH), read_only=read_only)


def init_db() -> None:
    """幂等创建 schema。可重复调用。"""
    con = _connect()
    try:
        con.execute(DDL)
    finally:
        con.close()


def insert(
    *,
    ticker: str,
    folder: Optional[str],
    date: _date | str,
    action: str,
    weight_change: Optional[float] = None,
    price: Optional[float] = None,
    rationale: str = "",
    thesis_5y: str = "",
    risks: str = "",
    tags: str = "",
    snapshot: Optional[dict[str, Any]] = None,
) -> int:
    """写入一条决策,返回 id。"""
    if action not in ACTIONS:
        raise ValueError(f"action 必须是 {ACTIONS} 之一,得到 {action!r}")

    init_db()
    snap = snapshot or {}
    con = _connect()
    try:
        row_id = con.execute(
            """
            INSERT INTO decisions (
                ticker, folder, date, action, weight_change, price,
                rationale, thesis_5y, risks, tags,
                snapshot_pe, snapshot_pb, snapshot_pe_pct_10y,
                snapshot_fscore, snapshot_roe, snapshot_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            RETURNING id
            """,
            [
                ticker,
                folder,
                date if isinstance(date, _date) else _date.fromisoformat(str(date)),
                action,
                weight_change,
                price,
                rationale,
                thesis_5y,
                risks,
                tags,
                snap.get("pe"),
                snap.get("pb"),
                snap.get("pe_pct_10y"),
                snap.get("fscore"),
                snap.get("roe"),
                json.dumps(snap, ensure_ascii=False, default=str) if snap else None,
            ],
        ).fetchone()[0]
        return int(row_id)
    finally:
        con.close()


def update(decision_id: int, **fields: Any) -> int:
    """局部更新。仅允许已知字段。返回受影响行数。"""
    allowed = {
        "ticker", "folder", "date", "action", "weight_change", "price",
        "rationale", "thesis_5y", "risks", "tags",
        "snapshot_pe", "snapshot_pb", "snapshot_pe_pct_10y",
        "snapshot_fscore", "snapshot_roe", "snapshot_json",
    }
    bad = set(fields) - allowed
    if bad:
        raise ValueError(f"未知字段: {bad}")
    if not fields:
        return 0

    init_db()
    sets = ", ".join(f"{k} = ?" for k in fields)
    con = _connect()
    try:
        con.execute(f"UPDATE decisions SET {sets} WHERE id = ?",
                    list(fields.values()) + [decision_id])
        return con.execute(
            "SELECT COUNT(*) FROM decisions WHERE id = ?", [decision_id]
        ).fetchone()[0]
    finally:
        con.close()


def delete(decision_id: int) -> int:
    init_db()
    con = _connect()
    try:
        con.execute("DELETE FROM decisions WHERE id = ?", [decision_id])
        return 1
    finally:
        con.close()


def get(decision_id: int) -> Optional[dict[str, Any]]:
    init_db()
    con = _connect(read_only=True)
    try:
        row = con.execute(
            "SELECT * FROM decisions WHERE id = ?", [decision_id]
        ).fetchdf()
        if row.empty:
            return None
        return row.iloc[0].to_dict()
    finally:
        con.close()


def list_all(limit: int = 500):
    """返回 DataFrame,新→旧。"""
    init_db()
    con = _connect(read_only=True)
    try:
        return con.execute(
            "SELECT * FROM decisions ORDER BY date DESC, id DESC LIMIT ?", [limit]
        ).fetchdf()
    finally:
        con.close()


def list_by_ticker(ticker: str):
    init_db()
    con = _connect(read_only=True)
    try:
        return con.execute(
            "SELECT * FROM decisions WHERE ticker = ? ORDER BY date DESC, id DESC",
            [ticker],
        ).fetchdf()
    finally:
        con.close()


def count() -> int:
    init_db()
    con = _connect(read_only=True)
    try:
        return int(con.execute("SELECT COUNT(*) FROM decisions").fetchone()[0])
    finally:
        con.close()


if __name__ == "__main__":
    init_db()
    print(f"✅ {DB_PATH} schema ready (rows={count()})")
