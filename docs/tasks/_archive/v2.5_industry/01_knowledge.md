---
name: 01_knowledge · 行业主索引 + 知识库 + ETF 主题映射
covers: D1 + D2 + D3
priority: Wave 1(0 依赖)
estimate: ~6h
agent: agent-knowledge
---

# 任务包 01 · 行业知识层

> 写 `.config/industry_master.yaml`(8 重点行业完整)+ `.tools/rules/industry_etf_mapping.yaml` + `03_macro/02_行业对标数据/` 8 篇 md。**全部产物是 yaml/markdown,无代码**。

---

## 📦 交付物清单

### D1 · `.config/industry_master.yaml`(必须最先完成,其他 agent 等这个)

8 重点行业(对齐 [.config/companies.csv](../../.config/companies.csv) 的 `industry_l2`):

1. **白酒**(SW L2)— 茅台/五粮液 在自选;type=stalwart
2. **化学制药**(SW L2)— 恒瑞医药 在自选;type=fast_grower(创新药近似)
3. **股份制银行**(SW L2)— 招商银行 在自选;type=bank
4. **保险**(SW L2)— 新华保险 在自选;type=insurance
5. **电池**(SW L2)— 宁德时代 在自选;type=fast_grower
6. **通信设备**(SW L2)— 中际旭创 在自选;type=fast_grower(代芯片)
7. **白色家电**(SW L2)— 美的集团 在自选;type=stalwart
8. **饮料乳品**(SW L2)— 伊利股份 在自选;type=stalwart

每条字段(必填):

```yaml
- code: BAIJIU
  name: 白酒                       # SW L2,精确匹配 companies.csv
  sw_l1: 食品饮料
  type: stalwart                  # 林奇六类
  summary: "..."                  # 30-60 字概览
  cycle_attrs:
    type: 防御                     # 成长 / 价值 / 防御 / 周期
    kondratieff_position: "..."   # 例:萧条期防御核心
    key_indicators: ["...", "..."]  # 3-5 条
  etf_codes: ["...", "..."]       # 2-4 只,**必须从 etf.duckdb 实有 35 ETF 中挑**
  knowledge_md: "03_macro/02_行业对标数据/01_白酒.md"
  leaders: ["600519", "..."]      # 龙头 ticker 2-4 只
```

**额外**:除 8 重点外,补 5-10 个 SW L2 占位条目(如:化学制品 / 轨交设备 / 消费电子 / 家电零部件 / 乘用车),`type` 填好,其他字段最简版(留 TODO 注释),为未来扩展自选时可立即接入。

#### 如何确认 etf_codes 实有

跑这个查 35 ETF 列表:
```bash
cd /Users/gongyong/Desktop/Keyi/preson && source .venv/bin/activate
python3 -c "
import duckdb
con = duckdb.connect('data/etf.duckdb', read_only=True)
for r in con.execute('SELECT etf_code, etf_name, etf_type FROM etf_meta ORDER BY etf_type, etf_code').fetchall():
    print(r)
"
```

只能填 etf.duckdb 里有的 code。若某行业没有合适的 ETF,留空 list `etf_codes: []` 加注释 `# 35 ETF 池暂无对应`。

---

### D2 · 8 篇行业知识 md

写入 `03_macro/02_行业对标数据/` 目录,文件名格式 `{编号}_{行业名}.md`:

- `01_白酒.md`
- `02_股份制银行.md`
- `03_保险.md`
- `04_化学制药.md`
- `05_电池.md`
- `06_通信设备.md`
- `07_白色家电.md`
- `08_饮料乳品.md`

**每篇结构**(200-400 字):

```markdown
# 白酒

## 行业概览

(1-2 段,100 字内 — 行业本质 / 商业模式 / 中国特色)

## 周期特性

- **周期类型**:防御
- **康波位置**:萧条期防御核心
- **典型周期长度**:5-7 年(渠道库存周期)
- **现在哪个阶段**:(留空让 E2 引擎填,或写"参见 Dashboard 实时判定")

## 龙头格局

- **CR3**:茅五洋 ~50% 市占
- **TOP 5**:贵州茅台 / 五粮液 / 山西汾酒 / 泸州老窖 / 洋河股份
- **格局演变**:高端化趋势,品牌集中度持续上升

## 关键观察指标

- 飞天茅台批价(终端价 = 行业景气温度计)
- 渠道库存周转(库存/月销 < 2 月健康)
- 消费税政策(2017 后未调,但悬剑)
- 春节/中秋销售(白酒两大旺季)

## 投资逻辑

(1-2 段 — 哪些时点适合买,哪些时点回避;参考鲁政委 / 林奇方法论)

## 推荐 ETF

| Code | 名称 | 主题 | 备注 |
|---|---|---|---|
| 512690 | 酒ETF | 主题 | 白酒 + 啤酒大消费综合 |
| ... | ... | ... | ... |

## 参考资料

- (链接到 [01_knowledge/03_投资策略与选股/](../../01_knowledge/03_投资策略与选股/) 内相关方法论)
```

**8 篇都按此结构写,字段保持一致**,F4 D 区会读这些 md 渲染。

#### 模板参考

[03_macro/02_行业对标数据/模板/](../../03_macro/02_行业对标数据/模板/) 已有结构,可参照但不用照搬 — 用本任务包定义的结构更紧凑。

---

### D3 · `.tools/rules/industry_etf_mapping.yaml`

从 [03_macro/01_ETF分析工具/康波周期ETF配置汇总.md](../../03_macro/01_ETF分析工具/康波周期ETF配置汇总.md) 解析(已有 12 个 ETF 主题完整文档),抽成结构化 yaml:

```yaml
current_phase: 萧条期中后段
target_allocation:
  defensive: [65, 75]
  offensive: [25, 35]

mapping:
  - industry: 白酒
    layer: defensive
    target_pct: [15, 20]
    recommended_etfs:
      - code: "512690"
        name: 酒ETF
        theme: 主题
        rationale: 白酒大消费综合曝光
    framework_logic: 稳定现金流 + 抗通胀
  # ... 其他 7 重点行业 + 黄金 + 国债 + 红利低波 等防御层 + 半导体 + AI + 新能源 等进攻层
```

**至少覆盖 10-12 行业/主题**,与 [康波周期ETF配置汇总.md](../../03_macro/01_ETF分析工具/康波周期ETF配置汇总.md) 列出的主题一一对应。

---

## 🛑 文件边界

只动以下路径:
- `.config/industry_master.yaml`(新建)
- `.tools/rules/industry_etf_mapping.yaml`(新建)
- `03_macro/02_行业对标数据/01_白酒.md` ~ `08_饮料乳品.md`(8 个新建)

**不动**:任何 .py 代码 / app.py / 其他 yaml / 其他目录

---

## ✅ 完成判定

```bash
cd /Users/gongyong/Desktop/Keyi/preson

# 1. yaml 格式有效
python3 -c "import yaml; d = yaml.safe_load(open('.config/industry_master.yaml')); print(f'industries={len(d[\"industries\"])}'); assert len(d['industries']) >= 8"
python3 -c "import yaml; d = yaml.safe_load(open('.tools/rules/industry_etf_mapping.yaml')); print(f'mapping={len(d[\"mapping\"])}'); assert len(d['mapping']) >= 8"

# 2. 8 篇知识 md 存在 + 字数足
for f in 03_macro/02_行业对标数据/0[1-8]_*.md; do
  wc -l "$f" | awk '{if ($1 < 15) {print "TOO SHORT: " $2; exit 1}}'
done

# 3. ETF code 在 etf.duckdb 实有
python3 -c "
import yaml, duckdb
con = duckdb.connect('data/etf.duckdb', read_only=True)
real = {r[0] for r in con.execute('SELECT etf_code FROM etf_meta').fetchall()}
m = yaml.safe_load(open('.config/industry_master.yaml'))
for ind in m['industries']:
    for c in ind.get('etf_codes', []):
        assert c in real, f'{ind[\"name\"]} 引用不存在 ETF {c}'
print('ETF 引用全部命中实有 35 ETF')
"

# 4. industry name 必须在 companies.csv.industry_l2 出现过(至少 8 重点)
python3 -c "
import yaml, csv
csv_inds = set()
with open('.config/companies.csv') as f:
    for row in csv.DictReader(f):
        csv_inds.add(row['industry_l2'])
m = yaml.safe_load(open('.config/industry_master.yaml'))
key = ['白酒','化学制药','股份制银行','保险','电池','通信设备','白色家电','饮料乳品']
yaml_names = {i['name'] for i in m['industries']}
for k in key:
    assert k in yaml_names, f'缺重点行业 {k}'
print('8 重点行业都在 yaml 中')
"
```

---

## 📚 参考

- [README.md 接口契约 A/B](README.md)
- [.config/companies.csv](../../.config/companies.csv)(industry_l2 列)
- 现有模板 [03_macro/02_行业对标数据/模板/](../../03_macro/02_行业对标数据/模板/)
- ETF 文档 [03_macro/01_ETF分析工具/](../../03_macro/01_ETF分析工具/)
- 大师方法论 [01_knowledge/03_投资策略与选股/](../../01_knowledge/03_投资策略与选股/)

---

## ⚠️ 已知坑

- 行业 name 用 SW L2 不带罗马数字 Ⅱ(companies.csv 是简体 + 中文 + 不带 Ⅱ)
- ETF code 必须从 etf.duckdb 35 只里挑,**不要凭知识写**(可能不存在)
- 知识 md 不能引用 .csv 数据(那是动态变化的,Tab 渲染时实时算)
- yaml 不要用复杂 anchor/merge,保持扁平好读
