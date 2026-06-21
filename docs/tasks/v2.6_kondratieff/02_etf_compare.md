---
name: 02_etf_compare · 同行业 N 选 1 引擎
priority: Wave 1(0 强依赖,弱依赖 v2.5 etf_recommender)
estimate: ~2h
---

# 任务包 02 · 同行业 N 选 1 选优引擎

> 写 `.tools/dashboard/etf_compare.py` — 给定行业内 N 只 ETF,按加权规则输出 Top 1 推荐 + 排序列表。

---

## 📦 交付物

### 主模块 `.tools/dashboard/etf_compare.py`(~150 行)

```python
from .kondratieff_loader import IndustryEntry, ETFEntry

DEFAULT_WEIGHTS = {"liquidity": 0.4, "return_1y": 0.3, "fund_size": 0.3}
# 阶段 2 之前 fund_size 普遍缺失,降级权重:
FALLBACK_WEIGHTS = {"liquidity": 0.5, "return_1y": 0.5}


def pick_top_etf(industry_entry: IndustryEntry,
                 weights: dict | None = None) -> ETFEntry | None:
    """单行业 Top 1。"""
    ranked = rank_etfs(industry_entry, weights)
    return ranked[0][0] if ranked else None


def rank_etfs(industry_entry: IndustryEntry,
              weights: dict | None = None) -> list[tuple[ETFEntry, float]]:
    """返回排序后 [(ETFEntry, composite_score), ...]"""
    ...


def _normalize_score(value: float | None, all_values: list[float]) -> float:
    """单值在 list 中的百分位排名(0-100);None 返回 50(中位)"""
    ...
```

#### 加权规则

每只 ETF 算综合分:
```
composite = w_liq * liquidity_pct + w_ret * return_pct + w_size * size_pct
```

- `liquidity_pct` — 已有 `liquidity_score`(在全 35 ETF 池中的 60d turnover 分位 0-100)
- `return_pct` — `return_1y` 在该行业 N 只 ETF 中的相对位置(0-100)
- `size_pct` — `fund_size` 在该行业 N 只 ETF 中的相对位置(阶段 2 后才有真实数据)

权重自动降级:
- `fund_size` 全行业全为 None → 走 `FALLBACK_WEIGHTS`
- `return_1y` 全为 None → 仅看 liquidity
- 全为 None → 返回 yaml 顺序(第一只为 Top 1)

#### 主流派加权(可选,留 hook)

mapping yaml 里 `theme ∈ {主题, 龙头, 红利}`,后续可加偏好:
```python
def pick_top_etf(..., prefer_theme: str | None = None):
    # 若 prefer_theme 命中,该 ETF composite +10 加成
```

阶段 1 默认不启用,留参数 hook。

---

### 测试 `.tools/dashboard/test_etf_compare.py`(8-12 项)

```python
def test_pick_top_etf_returns_etf_entry():
    cfg = load_config()
    e = cfg.defensive[0]  # 黄金
    top = pick_top_etf(e)
    assert top is not None
    assert top.code in [x.code for x in e.etfs]

def test_rank_etfs_descending():
    cfg = load_config()
    e = cfg.defensive[0]
    ranked = rank_etfs(e)
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)

def test_baijiu_top_etf_in_yaml():
    """白酒 Top 1 必须是 yaml 里 3 只之一"""
    cfg = load_config()
    baijiu = next(x for x in cfg.defensive if x.industry == "白酒")
    top = pick_top_etf(baijiu)
    yaml_codes = {e.code for e in baijiu.etfs}
    assert top.code in yaml_codes

def test_empty_industry_returns_none():
    e = IndustryEntry("空", "defensive", (0, 5), "", [])
    assert pick_top_etf(e) is None

def test_fallback_weights_when_no_fund_size():
    """阶段 1 无 fund_size 时不应崩"""
    cfg = load_config()
    for ind in cfg.all_industries:
        # 不 raise 即可
        pick_top_etf(ind)

def test_8_focus_industries_top_etf():
    """8 重点行业各能选出 Top 1"""
    cfg = load_config()
    key = ["白酒", "股份制银行", "保险", "化学制药",
           "电池", "通信设备", "白色家电", "饮料乳品"]
    found = [ind for ind in cfg.all_industries if ind.industry in key]
    for ind in found:
        top = pick_top_etf(ind)
        assert top is not None, f"{ind.industry} 无 Top 1"
```

---

## 🛑 文件边界

只能写:
- `.tools/dashboard/etf_compare.py`(新建)
- `.tools/dashboard/test_etf_compare.py`(新建)

**不动**:任何其他文件

---

## ✅ 完成判定

```bash
cd /Users/gongyong/Desktop/Keyi/preson && source .venv/bin/activate

python3 -c "
import sys; sys.path.insert(0, '.tools/dashboard')
from kondratieff_loader import load_config
from etf_compare import pick_top_etf, rank_etfs

cfg = load_config()
print('Top 1 per industry:')
for ind in cfg.all_industries:
    top = pick_top_etf(ind)
    print(f'  {ind.industry:10s} ({ind.layer:10s}) → {top.code if top else \"—\"}/{top.name if top else \"\"}')
"

pytest .tools/dashboard/test_etf_compare.py -v
```

---

## 📚 参考

- [README.md 接口契约 B](README.md)
- 依赖:01_data_loader.md 的 IndustryEntry / ETFEntry / load_config

---

## ⚠️ 已知坑

- 不要硬抛错;数据缺失走 fallback
- 同分时按 yaml 顺序,即 mapping 排在前面的 ETF 优先(用户认为更重要的)
- composite 分数仅供排序,UI 不一定展示(避免过度量化)
