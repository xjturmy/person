---
name: step-A · L1 全市场快照层
candidate: 候选 ⑨ Phase 1
priority: P0
estimate: ~6h
depends_on: 无(独立)
blocks: step-C(C 弱依赖此 step 的 market_spot 表)
---

# step-A · L1 全市场快照层(候选 ⑨ Phase 1)

> 通过 AkShare `stock_zh_a_spot_em` 一次性抓全 A 股 ~5400 行 × 23 列,沉淀到独立 `data/market.duckdb`,接入 weekly cron。

---

## 🎯 任务目标

**用户原话**:"每个行业存在多个公司,现在只有 1 个,通过拉取方法从中选效率太低"

**本 step 解决**:把全 A 股估值/盈利/市值快照沉淀成可查询库,后续行业筛选 / 全市场扫描 / 候选 ⑪ 行业聚焦都基于此。

---

## 📦 交付物清单

### 1. 数据库与表结构

- [ ] `data/market.duckdb` — 新建独立库(**不要污染 prices.duckdb / peers.duckdb**)
- [ ] `.tools/db/schema/market_spot.sql` — DDL,字段:
  ```sql
  CREATE TABLE market_spot (
      snapshot_date DATE,           -- 抓取日期
      ticker VARCHAR,                -- 6 位代码
      name VARCHAR,                  -- 中文名
      industry VARCHAR,              -- EM 行业(申万映射 step-C 处理)
      pe_dynamic DOUBLE,             -- PE 动态
      pb DOUBLE,
      total_market_cap DOUBLE,       -- 总市值(元)
      circulating_market_cap DOUBLE,
      turnover_rate DOUBLE,          -- 换手率
      pct_change DOUBLE,             -- 涨跌幅
      amplitude DOUBLE,              -- 振幅
      dividend_yield DOUBLE,         -- 股息率(可能缺,从其他源补)
      close DOUBLE,
      volume DOUBLE,
      amount DOUBLE,
      -- 原始 23 列其余列保留为 raw_* 前缀
      PRIMARY KEY (snapshot_date, ticker)
  );
  ```
- [ ] 索引:`(industry, snapshot_date)` + `(snapshot_date, total_market_cap DESC)`

### 2. 抓取脚本

- [ ] `.tools/db/fetch_market_spot.py`
  - 调 `akshare.stock_zh_a_spot_em()` → DataFrame
  - 字段重命名(中文 → 英文,见 schema)
  - 入 market_spot 表(snapshot_date = 今天)
  - 进度条 + retry(中国网络 ~7-8min,容易卡)
  - 失败重试 3 次,每次间隔指数退避

### 3. update.py 接入

- [ ] `.tools/db/update.py` 加 `step_market_spot()`,挂到 weekly cron
- [ ] 周日凌晨跑(避开工作日 spot 数据漂移)

### 4. 简易冒烟 Tab

- [ ] `.tools/dashboard/tabs/market_scan.py`(~80-100 行)
  - 顶部:行业 selectbox(从 market_spot 取 distinct industry)
  - 多维筛选:PE / PB / 股息率 / 市值 滑块
  - 表格:ticker / name / PE / PB / 市值 / 换手率 / 股息率(按 PE 排序)
  - **不做精美 UI,先打通数据流**(精美版留 step-C 行业聚焦做)
- [ ] `app.py` 加 `PAGE_MARKET_SCAN = "🌐 全市场扫描"` + sidebar 入口

### 5. PROGRESS.md 更新

- [ ] 在末尾追加:
  ```markdown
  ## v2.4 step-A · L1 全市场快照(2026-05-XX)
  - market.duckdb 新建,~5400 行 × N 列
  - fetch_market_spot.py 实测 ~Xmin
  - 「🌐 全市场扫描」Tab 可筛选行业 + 多维过滤
  - 接入 update.py weekly cron
  ```

---

## 🛑 文件边界(防撞车)

**只动以下路径,其他 step 不会动**:
- `data/market.duckdb`(新建)
- `.tools/db/fetch_market_spot.py`(新建)
- `.tools/db/schema/market_spot.sql`(新建)
- `.tools/db/update.py`(append 一段 step_market_spot)
- `.tools/dashboard/tabs/market_scan.py`(新建)
- `app.py`(加 PAGE_MARKET_SCAN + sidebar 一项)

---

## ✅ 完成判定

1. 跑 `python3 .tools/db/fetch_market_spot.py` → market.duckdb 中 market_spot 表 ~5400 行
2. `streamlit run app.py` 打开 Dashboard → 点「🌐 全市场扫描」→ 选「白酒」(或 EM 原行业名)→ 看到 30 家股票表格
3. `update.py weekly --dry-run` 输出包含 step_market_spot

---

## ⚠️ 已知坑

- **AkShare 中国网络分 58 batch 下载,~7-8min**。写完代码就放着跑,期间可以做别的(updatePy / Tab UI)。
- **EM 行业字段不是申万分类**。step-C 会做申万映射,本 step 直接存 EM 原行业字符串即可。
- **股息率字段可能缺失**。EM spot 表里不一定有,缺则置 NULL,后续从理杏仁 valuation 表回填。
- **不要用 prices.duckdb**。market_spot 是当日全市场截面,跟 prices 的日 K 时序数据是两个用途。
- **WAL 锁问题**(参考 D2 黄金 phase22 经验):写入完关闭连接,避免 streamlit 同时打开。

---

## 🔬 冒烟脚本(交付时跑)

```bash
cd /Users/gongyong/Desktop/Keyi/preson
source .venv/bin/activate

# 1. 抓数据
python3 .tools/db/fetch_market_spot.py

# 2. 验证行数
python3 -c "import duckdb; con = duckdb.connect('data/market.duckdb', read_only=True); print(con.execute('SELECT count(*), count(distinct industry) FROM market_spot').fetchone())"

# 3. 启 Dashboard 看 Tab(headless 验证)
streamlit run app.py --server.headless true &
sleep 5
curl -s http://localhost:8501/healthz
```

---

## 📚 参考资料

- AkShare 文档:https://akshare.akfamily.xyz/data/stock/stock.html#id56
- 记忆 [reference_akshare_sina_fallback.md](../../memory/reference_akshare_sina_fallback.md):eastmoney 易挂走新浪
- 记忆 [project_dimension1_data_layer.md](../../memory/project_dimension1_data_layer.md):DuckDB 8 张表架构,本 step 是第 9 张表所在的新库
