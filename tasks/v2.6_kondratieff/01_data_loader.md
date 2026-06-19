---
name: 01_data_loader · 康波配置数据聚合层
priority: Wave 1(0 依赖)
estimate: ~2h
---

# 任务包 01 · 康波配置数据聚合层

> 写 `.tools/dashboard/kondratieff_loader.py` — 把 `industry_etf_mapping.yaml` + `industry_master.yaml` + `etf.duckdb` 组装成 `KondratieffConfig`(三层结构 / N 行业 / 每行业 M ETF)。

---

## 📦 交付物

### 主模块 `.tools/dashboard/kondratieff_loader.py`(~150-200 行)

按 [README.md 接口契约 A](README.md) 实现:
- `IndustryEntry` dataclass
- `ETFEntry` dataclass
- `KondratieffConfig` dataclass + `all_industries` property
- `load_config() -> KondratieffConfig` 主入口

#### 实现要点

1. 读 `.tools/rules/industry_etf_mapping.yaml`:
   - `current_phase` → KondratieffConfig.current_phase
   - `target_allocation` → KondratieffConfig.target_allocation
   - `mapping[]` 按 layer 分组到 defensive/offensive/auxiliary 三个 list

2. 每个 mapping 条目:
   - `industry / layer / target_pct / framework_logic` → IndustryEntry
   - `recommended_etfs[]` → list[ETFEntry]
     - `code / name / theme / rationale` 直接抄

3. 调 etf.duckdb 填充每只 ETF 的市场数据(复用 v2.5 etf_recommender 的查询逻辑):
   - `last_close`(最新收盘)
   - `return_1y`(1y 涨跌)
   - `avg_turnover_60d`(60 日均换手)
   - `liquidity_score`(在全 35 ETF 池中的 60d turnover 分位)
   - 阶段 2 后:`fund_size / fee_total`(从 etf_meta 扩字段读;阶段 1 时这两列还没有,留 None)

4. **复用而非重写**:可直接 `from etf_recommender import recommend` 拿 ETF 数据
   - 但 etf_recommender 是按行业 query,需要二次组装为 KondratieffConfig 三层
   - 或者写新的批量 SQL,一次查全 35 ETF 数据

5. 缓存策略:模块内不缓存(留给 UI 层 `@st.cache_data(ttl=1800)`)

#### 可选辅助函数

- `get_phase_signals() -> dict` — 从 `data/macro.duckdb` 读最新实际利率 / CPI / M2 / USDCNY,返回 `{name, value, percentile, as_of}`(顶部 banner 用)
  - macro.duckdb 字段需先 DESCRIBE 确认

---

### 测试 `.tools/dashboard/test_kondratieff_loader.py`(8-12 项)

```python
def test_load_config_returns_kondratieff_config():
    cfg = load_config()
    assert isinstance(cfg, KondratieffConfig)
    assert cfg.current_phase == "萧条期中后段"

def test_layers_split_correctly():
    cfg = load_config()
    assert len(cfg.defensive) >= 8   # yaml 里防御 8
    assert len(cfg.offensive) >= 9
    assert len(cfg.auxiliary) >= 2

def test_all_industries_count():
    cfg = load_config()
    assert len(cfg.all_industries) == 19

def test_target_allocation_layers():
    cfg = load_config()
    for k in ["defensive", "offensive", "auxiliary"]:
        assert k in cfg.target_allocation
        assert len(cfg.target_allocation[k]) == 2  # [min, max]

def test_industry_entry_fields():
    cfg = load_config()
    e = cfg.defensive[0]
    assert e.industry and e.layer and e.target_pct and e.etfs

def test_etf_entry_fields():
    cfg = load_config()
    etfs = cfg.defensive[0].etfs
    assert len(etfs) >= 1
    assert etfs[0].code and etfs[0].theme

def test_etf_entry_data_filled_from_db():
    """已入库 ETF 应有 last_close / return_1y"""
    cfg = load_config()
    etfs_in_db = [e for e in cfg.defensive[0].etfs if e.last_close is not None]
    assert len(etfs_in_db) >= 1

def test_get_phase_signals_returns_dict():
    s = get_phase_signals()
    assert isinstance(s, dict)
    # 至少含实际利率
    assert any("利率" in k or "rate" in k.lower() for k in s.keys())
```

至少 8 项 pytest 通过。

---

## 🛑 文件边界

只能写:
- `.tools/dashboard/kondratieff_loader.py`(新建)
- `.tools/dashboard/test_kondratieff_loader.py`(新建)

**不动**:其他文件 / yaml / 数据库

---

## ✅ 完成判定

```bash
cd /Users/gongyong/Desktop/Keyi/preson && source .venv/bin/activate

python3 -c "
import sys; sys.path.insert(0, '.tools/dashboard')
from kondratieff_loader import load_config
cfg = load_config()
print(f'phase: {cfg.current_phase}')
print(f'defensive {len(cfg.defensive)} / offensive {len(cfg.offensive)} / auxiliary {len(cfg.auxiliary)}')
print(f'total industries: {len(cfg.all_industries)}')
e = cfg.defensive[0]
print(f'first defensive: {e.industry} / target {e.target_pct} / {len(e.etfs)} ETFs')
print(f'first ETF: {e.etfs[0].code}/{e.etfs[0].name}/1y={e.etfs[0].return_1y}')
"

pytest .tools/dashboard/test_kondratieff_loader.py -v
```

---

## 📚 参考

- [README.md 接口契约 A](README.md)
- v2.5 [.tools/dashboard/etf_recommender.py](../../.tools/dashboard/etf_recommender.py)(参考 SQL 风格 + liquidity_score 算法)
- [.tools/rules/industry_etf_mapping.yaml](../../.tools/rules/industry_etf_mapping.yaml)(19 行业完整)
- [data/etf.duckdb](../../data/) + [data/macro.duckdb](../../data/)

---

## ⚠️ 已知坑

- macro.duckdb 字段名未知,先 `DESCRIBE` 探针;若 fail 则 `get_phase_signals` 返回 `{}`
- ETF code 在 yaml 但不在 etf.duckdb → ETFEntry 数据字段保 None,`rationale` 加 "数据未入库"标注
- 阶段 1 时 `fund_size / fee_total` 还没字段,SQL `SELECT` 时用 `try/except` 容错;阶段 2 跑完后自动启用
- 排序逻辑放 02 任务包(本任务包只组装数据,不排序)
