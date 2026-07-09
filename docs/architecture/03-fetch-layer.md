# 抓数层

> 最后更新：2026-07-03。本页记录抓数入口、编排顺序和近期数据源踩坑经验；字段级缺口见 [docs/tools/待抓取字段清单.md](../tools/待抓取字段清单.md)。

## 数据源与入口

| 数据源 | 入口脚本 | 频率 |
|--------|----------|------|
| 理杏仁（估值/财务） | `lixinger-archiver/run_full_pipeline.py` | 周末 + 按需 |
| 理杏仁（估值宽表） | `lixinger-archiver/batch_update_recent_wide.py` | 快速日更 |
| 理杏仁（财务模块） | `lixinger-archiver/batch_update_fs_modules.py` | 季度 |
| AkShare（日 K + 行业 PE） | `db/fetch_akshare.py` | 每日 |
| 黄金多源 | `db/fetch_gold_prices.py` 等 6 个 | 每日 |
| 同行对标 | `db/fetch_peers.py` | 周末 |
| L1 全 A 市场 | `db/fetch_market_spot.py` | 每日（~13min，可 skip） |
| 宏观 | `db/fetch_macro.py` | 按需 |
| ETF | `lixinger-archiver/fetch_lixinger_etf.py` / `db/fetch_etf.py` / `fetch_gold_etf*.py` | 按需 |
| 周转率派生 | `db/fetch_turnover.py` | 季度 |

## 日常抓取顺序

常规刷新优先用一键管道：

```bash
source .venv/bin/activate
python3 .tools/data_consolidator/update_pipeline.py
```

专项修复或外部源不稳定时，按下面顺序拆开跑，便于定位失败点：

```bash
# 1. 理杏仁财务模块原始抓取，写入 02_companies/*/01_基本面数据/02-05_*
python3 .tools/lixinger-archiver/batch_update_fs_modules.py \
  --companies-csv .config/companies.csv \
  --base-dir 02_companies \
  --years 10

# 2. 整合原始目录到 历史数据/*.csv + 摘要.md
python3 .tools/data_consolidator/consolidate.py

# 3. 重建主库
python3 .tools/db/ingest.py

# 4. 刷新专项库和预计算
python3 .tools/db/fetch_market_spot.py --quiet
python3 .tools/db/fetch_peers.py --use-cached-peers --skip-fundamentals
python3 .tools/db/fetch_gold_etf_share.py
python3 .tools/dashboard/gold/paradigm.py --write
python3 .tools/dashboard/gold/overheat.py --write
python3 .tools/analytics/precompute.py
```

定点补抓可用 `--only-folder`，避免全量重复生成文件：

```bash
python3 .tools/lixinger-archiver/batch_update_fs_modules.py \
  --companies-csv .config/companies.csv \
  --base-dir 02_companies \
  --years 10 \
  --only-folder 07_美的集团
```

## 周末编排入口

```bash
python .tools/db/update.py
```

管道顺序（`db/update.py`）：

1. `fetch_akshare` — 日 K 增量
2. `ingest.py` — 全量重建 preson.duckdb
3. `validate.py` — 数据质量检查
4. `fetch_peers` — 同行池刷新（失败仅 warning）
5. 黄金模块（prices / real_rate / ETF / ratios）— 可 `--skip-gold`
6. `fetch_market_spot` — 可 `--skip-market-spot`
7. gold paradigm / overheat 快照

退出码：`0`=OK，`1`=validate critical，`2`=akshare/ingest 失败

## 理杏仁管道

```
.config/companies.csv + credentials.md (token)
        ↓
run_full_pipeline.py
        ↓
02_companies/{公司}/01_基本面数据/01_估值分析/ … 05_安全性分析/
        ↓
(可选) data_consolidator/consolidate.py → 历史数据/*.csv + 摘要.md
        ↓
db/ingest.py → preson.duckdb
```

## Token 获取

- 从 `.config/credentials.md` 自动解析（`lixinger_resolve_token.py`）
- 不出 git、不在日志打印

## 与整合层的关系

理杏仁脚本写入 **原始分目录**（`01_估值分析/` 等）；  
`consolidate.py` 合并为 **历史数据/*.csv**；  
`ingest.py` 再导入 DuckDB。

一键编排：`.tools/data_consolidator/update_pipeline.py`

## 理杏仁 ETF 管线

普通 ETF 优先走理杏仁 ETF 抓取器,写入 `data/etf.duckdb` 的 `etf_prices` / `etf_meta`;Dashboard 与原 ETF 行情源共用同一张表。

当前已核对的理杏仁官方接口:

- 基金 K 线: `https://open.lixinger.com/api/cn/fund/candlestick`
- 参数: `token`, `stockCode`, `startDate`, `endDate`
- 返回: `date/open/close/high/low/volume/amount/change`

```bash
# 单只 ETF,例如红利低波
.venv/bin/python .tools/lixinger-archiver/fetch_lixinger_etf.py --only 512590 --years 5

# 只看请求形态,不联网、不写库
.venv/bin/python .tools/lixinger-archiver/fetch_lixinger_etf.py --only 512590 --dry-run
```

若理杏仁 ETF 端点或字段口径变化,可用 `--endpoint` / `--code-field` 显式覆盖;若理杏仁不可用,再用 `.tools/db/fetch_etf.py` 的 AkShare/Eastmoney/Sina 行情管线兜底。

## 近期经验：2026-07-03 缺失数据修复

### 1. 公司代码必须规范化

`.config/companies.csv` 里 A 股历史上可能写成 `333`、`858`、`2475` 这类短代码。理杏仁 API 需要 A 股 6 位代码、港股 5 位代码；短代码会导致脚本显示“成功”，但返回空数据。

当前 `batch_update_fs_modules.py` 已在读取清单时统一补零：

- A 股：`333` → `000333`
- 港股：`2097` → `02097`

后续新增公司时仍建议在清单里直接写规范代码，避免其它脚本遗漏补零逻辑。

### 2. Lynch / Graham 的 BS 明细字段

理杏仁非金融财务端点可用字段：

| 字段 | 中文名 | 当前用途 |
|------|--------|----------|
| `q.bs.mc.t` | 货币资金 | Lynch L2 净现金 / Graham G3 NCAV 简化计算 |
| `q.bs.ar.t` | 应收账款 | 周转与财务质量辅助判断 |
| `q.bs.ca.t` / `q.bs.cl.t` | 流动资产 / 流动负债 | NCAV、流动性 |
| `q.bs.ta.t` / `q.bs.tl.t` / `q.bs.toe.t` | 资产 / 负债 / 权益 | 安全性与防御性 |

不可用或仍需替代源的字段不要放进同一次理杏仁请求，否则会触发 `ValidationError` 并导致整批失败。短期借款、一年内到期非流动负债仍需 Tushare/AkShare 资产负债表替代源。

### 3. AkShare 行情源要有兜底

- 港股单股 K 线用 `stock_hk_hist`，比全市场港股快照稳定。
- A 股日 K 如果缓存已经到今天，默认跳过“当天探测”；盘后确实要强刷时再加 `--allow-today-probe`。
- 行业 PE 在节假日可能返回无数据，保留旧缓存即可，不应阻断主库重建。

### 4. 市场快照和行业映射分开看

`fetch_market_spot.py` 的 EM 全 A 快照可能断连；脚本会切新浪行情兜底。新浪只有行情字段，不带 EM 行业映射，因此行业字段需从本地兜底：

- `.config/companies_industry.csv`
- `.config/companies.csv` 的 `industry_l2`

验收时不要只看全市场行业命中率；自选池命中率更关键。

### 5. 同行库刷新要保留旧基本面

EM 行业成分股接口不稳定时，用：

```bash
python3 .tools/db/fetch_peers.py --use-cached-peers --skip-fundamentals
```

这个模式应保留 `.config/peers.csv` 里的 `peer_roe`、`peer_gross_margin`、`peer_peg` 等字段，不能用空值覆盖旧快照。

### 6. 黄金 ETF 份额当前是代理源

AkShare 暂无稳定的 ETF 历史份额字段。当前 `fetch_gold_etf_share.py` 的默认顺序是：

1. 读 `.config/gold_etf_share_manual.csv`（若存在）
2. 显式传 `--try-akshare` 时才尝试 AkShare
3. 否则用 `gold_etf_prices.volume` 派生 `share_change_5d`

因此 `gold_etf_share.share` 可能是成交量代理，不等于真实基金份额；看板短期过热信号只使用 `share_change_5d`。

## 验收口径

数据刷新后至少跑以下检查：

```bash
.venv/bin/python - <<'PY'
import duckdb

con = duckdb.connect('data/preson.duckdb', read_only=True)
print('prices', con.execute("SELECT COUNT(DISTINCT ticker), COUNT(*), MAX(date) FROM prices").fetchone())
for metric in ['货币资金', '应收账款']:
    missing = con.execute("""
      SELECT COUNT(*) FROM companies c
      WHERE c.category='non_financial'
        AND NOT EXISTS (
          SELECT 1 FROM safety s
          WHERE s.ticker=c.ticker AND s.metric=? AND s.value IS NOT NULL
        )
    """, [metric]).fetchone()[0]
    print(metric, 'missing_non_financial=', missing)
con.close()

con = duckdb.connect('data/analytics.duckdb', read_only=True)
print('analytics', con.execute("SELECT (SELECT COUNT(*) FROM screener_wide), (SELECT COUNT(*) FROM company_bundle)").fetchone())
con.close()
PY
```

2026-07-03 本轮修复后的基准：

| 检查项 | 期望 |
|---|---:|
| `prices` 覆盖 | 100 ticker，最新 2026-07-03 |
| 非金融 `货币资金` 缺失 | 0 |
| 非金融 `应收账款` 缺失 | 0 |
| `analytics.screener_wide` | 100 行 |
| `analytics.company_bundle` | 100 行 |
