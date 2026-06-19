---
name: step-B · 全局搜索栏
candidate: 候选 ⑩
priority: P0
estimate: ~2-3h
depends_on: 无(独立)
blocks: 无
---

# step-B · 全局搜索栏(候选 ⑩)

> sidebar 顶部加搜索栏,支持代码 / 中文名 / 拼音首字母 / 行业关键词,优先级降序匹配,命中跳转公司详情。

---

## 🎯 任务目标

**用户原话**:"我想增加搜索的功能,便于快速查找公司"

**本 step 解决**:selectbox 翻找 15 家 OK,但 step-A 落地后扩到 ~5400 家,搜索成必需。先做 L3(自选 15 家)闭环,L2 fallback 留 hook。

---

## 📦 交付物清单

### 1. 依赖

- [ ] `requirements.txt` 加:
  ```
  pypinyin>=0.50.0
  rapidfuzz>=3.5.0
  ```
  > 用 `rapidfuzz` 不用 `fuzzywuzzy`(更快 + 不需要 python-Levenshtein 编译)

### 2. 搜索组件

- [ ] `.tools/dashboard/components/search_bar.py`(新建)
  - `class CompanySearcher`:
    - `__init__(self, companies_df)`:接受 DataFrame(ticker, name, name_pinyin_initial, industry)
    - `search(query: str, limit=10) -> list[dict]`:返回命中列表
  - 优先级匹配(score 降序):
    1. 完全匹配 ticker(`600519` → 茅台)→ score 100
    2. 完全匹配中文名(`贵州茅台`)→ score 95
    3. 中文名前缀匹配(`茅台` 命中 `贵州茅台`)→ score 90
    4. 拼音首字母完全匹配(`gzmt` → 贵州茅台)→ score 85
    5. 模糊包含(rapidfuzz partial_ratio > 60)→ score 60-80
    6. 行业关键词(`白酒` → 整个白酒行业列表)→ score 50
  - **缓存**:`@functools.lru_cache` 装饰预处理后的 DataFrame

- [ ] `.tools/dashboard/components/search_bar.py` 内提供 Streamlit 入口:
  - `def render_search_bar(searcher, key="global_search")`:
    - `query = st.text_input("🔍 搜索公司", key=key)`
    - 命中后 `st.session_state["selected_company"] = result["ticker"]`
    - 显示 Top 5 候选(`st.expander` 收起)

### 3. app.py 接入

- [ ] `app.py` sidebar **顶部**(在 selectbox 之上):
  ```python
  from tools.dashboard.components.search_bar import CompanySearcher, render_search_bar

  searcher = build_searcher()  # 读 .config/companies.csv
  render_search_bar(searcher)
  ```
- [ ] 命中后:`st.session_state["selected_company"]` → 联动现有 selectbox(用 index 切换)

### 4. 数据源

- [ ] **L3 自选(必做)**:读 `.config/companies.csv` 15 家
- [ ] **L2 fallback hook(预留)**:
  ```python
  def search_l2_fallback(query, limit=10):
      """step-A 完成后接 market_spot;当前返回空 list。"""
      try:
          import duckdb
          con = duckdb.connect("data/market.duckdb", read_only=True)
          # ...
      except Exception:
          return []
  ```
  当 L3 命中 < 5 时调用,失败静默(因为 step-A 可能还没落地)

### 5. PROGRESS.md 更新

- [ ] 末尾追加:
  ```markdown
  ## v2.4 step-B · 全局搜索栏(2026-05-XX)
  - rapidfuzz + pypinyin 接入
  - search_bar.py 组件,优先级降序 6 档匹配
  - sidebar 顶部接入,命中联动 selectbox
  - L2 fallback hook 预留(step-A 完成后激活)
  - 冒烟:茅台 / 600519 / gzmt / 白酒 全部命中
  ```

---

## 🛑 文件边界(防撞车)

- `.tools/dashboard/components/search_bar.py`(新建)
- `app.py`(sidebar 顶部插一段;**不动其他 step 加的 PAGE 入口**)
- `requirements.txt`(append 2 行)

---

## ✅ 完成判定

1. `pip install -r requirements.txt` 无报错
2. `streamlit run app.py` → sidebar 顶部看到搜索框
3. 输入下列查询都能命中前 3:
   - `茅台` → 贵州茅台
   - `600519` → 贵州茅台
   - `gzmt` → 贵州茅台
   - `白酒` → 茅台 + 五粮液(任意顺序)
   - `xhbx` → 新华保险
4. 命中后点击 → selectbox 切换到对应公司
5. 离线测试(无 streamlit):
   ```python
   from tools.dashboard.components.search_bar import CompanySearcher
   import pandas as pd
   df = pd.read_csv(".config/companies.csv")
   searcher = CompanySearcher(df)
   assert searcher.search("茅台")[0]["ticker"] == "600519"
   ```

---

## ⚠️ 已知坑

- `pypinyin` 抽首字母用:`pypinyin.lazy_pinyin(name, style=pypinyin.Style.FIRST_LETTER)` → `["g", "z", "m", "t"]` → join `"gzmt"`
- 中文/英文混合 ticker(港股 `02097` 蜜雪集团)需要单独识别 → 5-6 位数字 = ticker
- 行业关键词命中如果数量太多(白酒可能 40 家)→ 限制返回 top 7,提示"还有 33 条,去全市场扫描"
- session_state 跨 rerun 持久,确保命中后不被 selectbox 默认值覆盖

---

## 🔬 冒烟脚本(交付时跑)

```bash
cd /Users/gongyong/Desktop/Keyi/preson
source .venv/bin/activate
pip install -r requirements.txt

# 离线测试
python3 -c "
import sys; sys.path.insert(0, '.')
from tools.dashboard.components.search_bar import CompanySearcher
import pandas as pd
df = pd.read_csv('.config/companies.csv')
s = CompanySearcher(df)
for q in ['茅台', '600519', 'gzmt', '白酒', 'xhbx']:
    r = s.search(q, limit=3)
    print(f'{q!r} → {[h[\"name\"] for h in r]}')
"

# Streamlit headless 验证
streamlit run app.py --server.headless true &
sleep 5
curl -s http://localhost:8501/healthz && echo "OK"
```

---

## 📚 参考资料

- 记忆 [reference_streamlit_techniques.md](../../memory/reference_streamlit_techniques.md):session_state / 离线测试 / mtime 缓存
- pypinyin:https://pypinyin.readthedocs.io/zh_CN/master/
- rapidfuzz:https://github.com/rapidfuzz/RapidFuzz
