---
name: step-D · 黄金短期过热信号引擎
candidate: 候选 ⑫
priority: P1
estimate: ~5-6h
depends_on: 无(基于 v2.3 D2 已有 gold.duckdb,完全独立)
blocks: 无
---

# step-D · 黄金短期过热信号引擎(候选 ⑫)

> 扩展 D2 黄金模块,加 6 信号过热引擎(换手率 / 成交量 / RSI / MA60 偏离 / 资金流入 / 期货基差)+ 大趋势联动建议,**完全照 paradigm_engine.py + gold_paradigm.yaml 模式**。

---

## 🎯 任务目标

**用户原话**:"对于黄金,我现在只知道大趋势,能不能基于某些条件做出短期的建议,比如同花顺中 etf 的换手率和成交量,除了博大趋势,还要知道短期是否存在过热的情况"

**本 step 解决**:D2 已有"长期主导身份"(月/年节奏),缺"周/日级买入时机"。**追高被套是黄金投资最常见损失模式** — 用 6 信号过热引擎防追高。

---

## 📦 交付物清单

### 1. 数据扩展

- [ ] `.tools/db/fetch_gold_etf.py` 扩列(已有 4 ETF 价格,加 2 列):
  - `turnover_rate`(换手率)
  - `volume`(成交量)
  - 写入现有 `gold_etf_price` 表(或独立 `gold_etf_volume` 表)
- [ ] `.tools/db/fetch_gold_etf_share.py`(新建)
  - 调 AkShare `fund_etf_fund_info_em(symbol="518880")` 抓 ETF 份额时序
  - 4 个 ETF:518880 / 518800 / 159934 / 518680(华安/工银/易方达/SPDR ADR 不在,改沪市)
  - 入新表 `gold_etf_share`:
    ```sql
    CREATE TABLE gold_etf_share (
        date DATE,
        etf_code VARCHAR,
        share DOUBLE,           -- 当日份额
        share_change_5d DOUBLE, -- 5 日变化%
        PRIMARY KEY (date, etf_code)
    );
    ```

### 2. 过热引擎 yaml

- [ ] `.tools/rules/gold_overheat.yaml`(完全照 [.tools/rules/gold_paradigm.yaml] 结构)
  ```yaml
  # 6 信号 × 3 档红绿灯
  signals:
    - id: etf_turnover
      name: ETF 换手率激增
      source: gold_etf_price.turnover_rate
      method: latest_avg          # 最近 5 日均值
      thresholds:
        red: ">5"      # > 5%
        yellow: "2-5"
        green: "<2"
      weight: 1.0

    - id: volume_surge
      name: 成交量爆量
      source: gold_etf_price.volume
      method: ratio_5d_60d        # 5 日均量 / 60 日均量
      thresholds:
        red: ">3.0"
        yellow: "2-3"
        green: "<2"
      weight: 1.0

    - id: rsi_14
      name: RSI 过买
      source: gold_metrics.spot_price
      method: rsi_14
      thresholds:
        red: ">75"
        yellow: "65-75"
        green: "<65"
      weight: 1.0

    - id: ma60_deviation
      name: 价格偏离 MA60
      source: gold_metrics.spot_price
      method: deviation_from_ma60
      thresholds:
        red: ">+10%"
        yellow: "+5%~+10%"
        green: "<+5%"
      weight: 1.0

    - id: etf_share_inflow
      name: ETF 资金流入激增
      source: gold_etf_share.share_change_5d
      method: max_across_etfs     # 4 个 ETF 取 max
      thresholds:
        red: ">+5%"
        yellow: "+2%~+5%"
        green: "<+2%"
      weight: 1.0

    - id: futures_basis            # 可选,有数据则用
      name: 期货基差异常
      source: gold_futures.basis
      method: latest
      thresholds:
        red: ">+2%"
        yellow: "±1%"
        green: "<±0.5%"
      weight: 0.5                  # 可选信号权重低

  # 综合判定
  verdict:
    - condition: "red_count >= 3"
      label: 🔴 暂停建仓
      action: 过热警示,等回调
    - condition: "red_count == 1 or red_count == 2 or yellow_count >= 3"
      label: 🟡 持有观望
      action: 局部偏热,不加仓
    - condition: "green_count >= 4"
      label: 🟢 可加仓
      action: 短期未过热

  # 大趋势联动(关键!)
  trend_combo:
    - long_paradigm: "≥2/3 看多"
      short_signal: 🟢
      label: 加仓窗口
    - long_paradigm: "≥2/3 看多"
      short_signal: 🟡
      label: 持有
    - long_paradigm: "≥2/3 看多"
      short_signal: 🔴
      label: ⚠️ 暂停建仓,等过热释放
    - long_paradigm: "≤1/3 看多"
      short_signal: 🔴
      label: 减仓信号
    - long_paradigm: "≤1/3 看多"
      short_signal: 🟢
      label: 反弹机会(高风险)
  ```

### 3. 引擎实现

- [ ] `.tools/dashboard/overheat_engine.py`(完全照 [.tools/dashboard/paradigm_engine.py] 模式,~150-200 行)
  - `class OverheatEngine`:
    - `__init__(self, yaml_path, db_path="data/gold.duckdb")`
    - `evaluate(as_of_date) -> dict`:逐信号算值 → 比对阈值 → 标 🔴/🟡/🟢
    - `vote(as_of_date) -> dict`:综合判定 → 返回 {label, action, signals: [...], counts}
    - `combo_with_paradigm(as_of_date) -> dict`:与 paradigm_engine 联动 → 返回最终建议
    - `record_snapshot(as_of_date)`:写入 `overheat_snapshot` 表(date / verdict / red_count / yellow_count / green_count / signals_json)

### 4. update.py 接入

- [ ] `.tools/db/update.py` weekly 加第 N+1 步:
  ```python
  def step_gold_overheat():
      # 1. 抓 etf share
      run("python3 .tools/db/fetch_gold_etf_share.py")
      # 2. 跑引擎 + record snapshot
      from tools.dashboard.overheat_engine import OverheatEngine
      eng = OverheatEngine(".tools/rules/gold_overheat.yaml")
      eng.record_snapshot(as_of=today)
  ```

### 5. Dashboard 集成

- [ ] `.tools/dashboard/tabs/gold_analysis.py`:
  - **顶部 banner**:已有「★ 主导身份」卡 + 加「⏱ 短期热度」卡(并列,黄金渐变区分色)
    - 显示当前判定(🟢/🟡/🔴)+ 综合理由(如"换手率偏高 + RSI 65")
    - 联动建议(如"⚠️ 暂停建仓,等过热释放")
  - **第 6 sub-tab「⑥ 短期过热扫描」**(在已有 5 sub-tab 后追加):
    - 6 信号 × 3 档矩阵表(信号名 / 当前值 / 档位 / 历史百分位 / 阈值)
    - 综合判定卡(verdict + action)
    - 大趋势联动决策矩阵(2×3 或 3×3 表,行=大趋势,列=短期信号,格=建议)
    - **历史回看图**:近 1 年逐周的 🔴/🟡/🟢 时序(plotly 热力条 / 阶梯图)
      - 标注 2024-04 / 2024-08 / 2025-03 等历史回调点,看 🔴 警示是否对应
- [ ] 离线测试支持:`from tools.dashboard.overheat_engine import OverheatEngine` 可直接调用

### 6. PROGRESS.md 更新

- [ ] 追加:
  ```markdown
  ## v2.4 step-D · 黄金短期过热引擎(2026-05-XX)
  - gold.duckdb 扩 etf_share 表 + price 表加 turnover/volume 列
  - gold_overheat.yaml 6 信号 × 3 档(完全照 gold_paradigm 模式)
  - overheat_engine.py 引擎(~XXX 行,evaluate/vote/combo/snapshot)
  - 顶部 banner「⏱ 短期热度」卡 + 第 6 sub-tab「短期过热扫描」
  - 历史回看图覆盖近 1 年 🔴/🟡/🟢 时序
  - 接入 update.py weekly cron
  ```

---

## 🛑 文件边界(防撞车)

- `.tools/db/fetch_gold_etf.py`(扩 2 列)
- `.tools/db/fetch_gold_etf_share.py`(新建)
- `.tools/rules/gold_overheat.yaml`(新建)
- `.tools/dashboard/overheat_engine.py`(新建)
- `.tools/dashboard/tabs/gold_analysis.py`(加顶部 banner 卡 + 第 6 sub-tab)
- `.tools/db/update.py`(append 一段 step_gold_overheat)
- `data/gold.duckdb`(加 gold_etf_share + overheat_snapshot 表)

**不动**:step-A/B/C 涉及的所有文件,完全不冲突

---

## ✅ 完成判定

1. 跑数据抓取:
   ```bash
   python3 .tools/db/fetch_gold_etf.py            # 扩列后重抓
   python3 .tools/db/fetch_gold_etf_share.py      # 新表
   ```
   验证 gold.duckdb:
   ```python
   import duckdb
   con = duckdb.connect("data/gold.duckdb", read_only=True)
   print(con.execute("SELECT count(*) FROM gold_etf_share").fetchone())
   print(con.execute("SELECT * FROM gold_etf_price ORDER BY date DESC LIMIT 1").fetchall())
   # 验证 turnover_rate 和 volume 列存在且非 NULL
   ```

2. 引擎离线测试:
   ```python
   from tools.dashboard.overheat_engine import OverheatEngine
   eng = OverheatEngine(".tools/rules/gold_overheat.yaml")
   v = eng.vote(as_of_date="2026-05-08")
   assert v["label"] in ["🟢 可加仓", "🟡 持有观望", "🔴 暂停建仓"]
   assert len(v["signals"]) == 6
   combo = eng.combo_with_paradigm(as_of_date="2026-05-08")
   print(combo)
   ```

3. Dashboard 验证:
   ```bash
   streamlit run app.py --server.headless true &
   ```
   - 「🥇 黄金分析法」顶部看到「⏱ 短期热度」卡(并列「★ 主导身份」)
   - 第 6 sub-tab「短期过热扫描」可点开,6 信号矩阵清晰
   - 历史回看图显示近 1 年时序

4. AppTest 0 异常(参考 D2 Phase 2.3 测试模式)

---

## ⚠️ 已知坑

- **完全照 paradigm_engine 模式**:不要创新架构,evaluate/vote/record_snapshot 三方法签名跟 paradigm_engine 完全对齐(见记忆 [project_v23_d2_phase24_paradigm_engine.md])
- **AkShare ETF 份额接口偶尔超时**:写入失败时保留上期数据,UI 标"数据新鲜度:N 天前"
- **RSI/MA 计算**:必须与现有 gold_metrics 同源(SGE 国内),避免跨源失真
- **DuckDB window 保留字坑**(记忆 D2 Phase 2.2):window function 别名加引号或换名
- **WAL 锁**(记忆 D2 Phase 2.2):写完关连接,与 streamlit 读分离
- **6 信号同涨同跌**:6 个分属"价格 / 量能 / 资金"三类,不必担心独立性 — yaml 设计已分散
- **futures_basis 是可选信号**:沪金主力数据可能缺,缺则降到 5 信号投票,verdict 阈值同步降一档

---

## 🔬 冒烟脚本(交付时跑)

```bash
cd /Users/gongyong/Desktop/Keyi/preson
source .venv/bin/activate

# 1. 数据
python3 .tools/db/fetch_gold_etf.py
python3 .tools/db/fetch_gold_etf_share.py

# 2. 验证表结构
python3 -c "
import duckdb
con = duckdb.connect('data/gold.duckdb', read_only=True)
print('gold_etf_price 列:', [r[0] for r in con.execute('DESCRIBE gold_etf_price').fetchall()])
print('gold_etf_share 行数:', con.execute('SELECT count(*) FROM gold_etf_share').fetchone())
"

# 3. 引擎
python3 -c "
import sys; sys.path.insert(0, '.')
from tools.dashboard.overheat_engine import OverheatEngine
eng = OverheatEngine('.tools/rules/gold_overheat.yaml')
import datetime
v = eng.vote(as_of_date=datetime.date.today())
print('判定:', v['label'])
print('信号:', [(s['id'], s['level']) for s in v['signals']])
combo = eng.combo_with_paradigm(as_of_date=datetime.date.today())
print('联动:', combo['label'], '|', combo['action'])
"

# 4. record snapshot
python3 -c "
import sys; sys.path.insert(0, '.')
from tools.dashboard.overheat_engine import OverheatEngine
eng = OverheatEngine('.tools/rules/gold_overheat.yaml')
import datetime
eng.record_snapshot(as_of_date=datetime.date.today())
print('snapshot recorded')
"

# 5. Streamlit headless
streamlit run app.py --server.headless true &
sleep 5
curl -s http://localhost:8501/healthz && echo "OK"
```

---

## 📚 参考资料

- 记忆 [project_v23_d2_phase24_paradigm_engine.md](../../memory/project_v23_d2_phase24_paradigm_engine.md):**完全照搬此模式**
- 记忆 [project_v23_d2_phase23_gold_tab.md](../../memory/project_v23_d2_phase23_gold_tab.md):Tab 集成 + AppTest 测试
- 记忆 [project_v23_d2_phase22_gold_data.md](../../memory/project_v23_d2_phase22_gold_data.md):4 个数据坑(沪银 /1000 / SPDR 手填 / window 保留字 / WAL 锁)
- 已有文件:`.tools/dashboard/paradigm_engine.py` 442 行 + `.tools/rules/gold_paradigm.yaml` 214 行 — **逐行参考**
- AkShare ETF:`fund_etf_fund_info_em` / `fund_etf_spot_em`
