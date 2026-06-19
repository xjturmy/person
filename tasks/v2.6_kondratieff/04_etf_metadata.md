---
name: 04_etf_metadata · ETF 元数据扩展
priority: Wave 1(0 依赖,但需 AkShare 网络)
estimate: ~5-7h
---

# 任务包 04 · ETF 元数据扩展(费率 + 规模)

> 写 `.tools/db/fetch_etf_meta_extra.py` 抓 35 ETF 的 management_fee / custodian_fee / fund_size,扩 etf.duckdb.etf_meta 表;接入 update.py monthly cron。

---

## 📦 交付物

### 1. `.tools/db/fetch_etf_meta_extra.py`(~150 行)

```python
"""扩展 etf.duckdb.etf_meta 表 — 抓 ETF 元数据(费率 / 规模).

数据源:AkShare `fund_etf_fund_em()`(全市场 ETF 一张表,按 35 ETF code filter)
失败兜底:字段保 None;手填 csv 备份(暂不实现,留 v2.7)。

频率:monthly cron(费率 + 规模少变)。
"""
from __future__ import annotations
from pathlib import Path
import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ETF_DB = PROJECT_ROOT / "data" / "etf.duckdb"


def ensure_schema(con) -> None:
    """idempotent ALTER ADD COLUMN."""
    cols = {r[0] for r in con.execute("DESCRIBE etf_meta").fetchall()}
    if "management_fee" not in cols:
        con.execute("ALTER TABLE etf_meta ADD COLUMN management_fee DOUBLE")
    if "custodian_fee" not in cols:
        con.execute("ALTER TABLE etf_meta ADD COLUMN custodian_fee DOUBLE")
    if "fund_size" not in cols:
        con.execute("ALTER TABLE etf_meta ADD COLUMN fund_size DOUBLE")
    if "tracking_index" not in cols:
        con.execute("ALTER TABLE etf_meta ADD COLUMN tracking_index VARCHAR")
    if "meta_updated" not in cols:
        con.execute("ALTER TABLE etf_meta ADD COLUMN meta_updated DATE")


def fetch_extra() -> pd.DataFrame:
    """抓 AkShare 全市场 ETF,filter 我们 35 ETF.
    返回 DataFrame: etf_code, management_fee, custodian_fee, fund_size, tracking_index
    """
    import akshare as ak
    df = ak.fund_etf_fund_em()  # 全市场 ETF;字段如 "管理费率" "托管费率" "资产规模" "跟踪指数代码"
    # 字段重命名 + 类型转换 ...
    return df_filtered


def update_metadata() -> int:
    """主入口:抓数据 → ALTER schema → UPDATE etf_meta. 返回更新行数."""
    con = duckdb.connect(str(ETF_DB))
    ensure_schema(con)
    df = fetch_extra()
    if df.empty:
        return 0
    # UPDATE 而非 INSERT(etf_meta 已有 35 行 etf_code)
    n = 0
    for _, row in df.iterrows():
        con.execute("""
            UPDATE etf_meta SET
              management_fee = ?, custodian_fee = ?,
              fund_size = ?, tracking_index = ?,
              meta_updated = CURRENT_DATE
            WHERE etf_code = ?
        """, [row["management_fee"], row["custodian_fee"],
              row["fund_size"], row["tracking_index"], row["etf_code"]])
        n += 1
    con.close()
    return n


if __name__ == "__main__":
    n = update_metadata()
    print(f"updated {n} rows")
```

#### 实现要点

- **字段映射**:AkShare 返回中文列名,需要 hardcoded mapping(参考 v2.5 fetch_market_spot.py 风格)
- **fund_size 单位**:AkShare 一般是"亿元"(直接存)或"元"(/1e8 转)— 探针确认
- **management_fee**:百分比形式(0.5% 还是 0.005),探针确认后统一存为小数(0.005)
- **tracking_index**:有的 ETF 没有 tracking_index 字段,字段保 None
- **网络失败重试**:3 次指数退避(参考 fetch_market_spot.py)

---

### 2. v2.5 etf_recommender.py 扩字段

修改 `ETFCandidate` dataclass 加:
```python
@dataclass
class ETFCandidate:
    # ... 已有字段
    fee_total: float | None = None
    fund_size: float | None = None
```

`recommend()` 内 SELECT etf_meta 时新增列:
```python
SELECT etf_code, etf_name, etf_type,
       management_fee, custodian_fee, fund_size, tracking_index
FROM etf_meta WHERE etf_code IN (...)
```

`fee_total = (management_fee or 0) + (custodian_fee or 0)`

---

### 3. update.py 接入

加 `step_etf_meta_extra()`:
```python
def step_etf_meta_extra():
    """月度 cron:更新 ETF 费率 + 规模."""
    from .fetch_etf_meta_extra import update_metadata
    n = update_metadata()
    print(f"[etf_meta_extra] updated {n} rows")
```

挂到 monthly cron(每月第 1 日触发);`--skip-etf-meta-extra` 兜底。

---

### 4. 测试 `.tools/db/test_fetch_etf_meta_extra.py`(6-10 项)

```python
def test_ensure_schema_idempotent(tmp_path):
    """重复跑 ALTER 不抛错"""
    ...

def test_fetch_extra_returns_dataframe(monkeypatch):
    """mock akshare.fund_etf_fund_em 返回固定 df"""
    ...

def test_update_metadata_writes_rows():
    """端到端:跑一次 → etf_meta 至少 1 行有 management_fee"""
    ...

def test_module_imports():
    from tools.db import fetch_etf_meta_extra
    assert hasattr(fetch_etf_meta_extra, "update_metadata")
```

至少 6 项通过(端到端测试可标 `@pytest.mark.network` 跳过 CI)。

---

## 🛑 文件边界

只能写:
- `.tools/db/fetch_etf_meta_extra.py`(新建)
- `.tools/db/test_fetch_etf_meta_extra.py`(新建)
- `.tools/db/update.py`(append step_etf_meta_extra 调度)
- `data/etf.duckdb`(ALTER ADD COLUMN + UPDATE,**不改 DDL/数据**)
- `.tools/dashboard/etf_recommender.py`(append fee_total / fund_size 字段)
- `.tools/dashboard/tabs/industry_focus.py`(C 区表格加 2 列)

---

## ✅ 完成判定

```bash
cd /Users/gongyong/Desktop/Keyi/preson && source .venv/bin/activate

# 1. 单跑抓数(网络)
python3 .tools/db/fetch_etf_meta_extra.py

# 2. 验证 etf_meta 扩字段
python3 -c "
import duckdb
con = duckdb.connect('data/etf.duckdb', read_only=True)
print('cols:', [r[0] for r in con.execute('DESCRIBE etf_meta').fetchall()])
df = con.execute('SELECT etf_code, etf_name, management_fee, fund_size FROM etf_meta WHERE management_fee IS NOT NULL LIMIT 5').fetchdf()
print(df)
"

# 3. v2.5 industry_focus C 区也跟着补 2 列
streamlit run .tools/dashboard/app.py --server.headless true --server.port 8501 &
# 切到 🏭 行业分析 → 看 C 区表格

# 4. update.py monthly --dry-run
python3 .tools/db/update.py monthly --dry-run | grep etf_meta_extra
```

---

## 📚 参考

- [README.md 接口契约 C/D](README.md)
- 网络抓数模板:[fetch_market_spot.py](../../.tools/db/fetch_market_spot.py)(retry / 进度条)
- AkShare 文档:`fund_etf_fund_em` 字段含义未必稳定,先探针后写 mapping
- 记忆 [reference_akshare_sina_fallback.md](../../.claude/projects/-Users-gongyong-Desktop-Keyi-preson/memory/reference_akshare_sina_fallback.md)

---

## ⚠️ 已知坑

- AkShare `fund_etf_fund_em` 偶尔不返回某些 ETF(尤其新上市)→ 字段保 None,UI 标"未入库"
- fund_size 单位不一致,先探针确认("亿元" vs "元");统一存"亿元"
- 跟踪指数 code 留 hook 不用(v2.7 跟踪误差用)
- ALTER ADD COLUMN 在 DuckDB 默认 NULL,无需 default
- monthly cron 失败不阻塞 weekly(`--skip-etf-meta-extra` 兜底)
- 不抢 jin10(中国 IP geo-block + ssl 卡的坑参考记忆)
