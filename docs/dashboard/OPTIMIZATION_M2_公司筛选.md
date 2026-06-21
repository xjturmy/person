# 模块 2 优化记录:🔍 公司筛选 Tab

> 文件:[tabs/screener.py](tabs/screener.py) + [screener.py](screener.py) + [presets.yaml](presets.yaml)
>
> **创建**:2026-05-04
> **状态**:📋 待开工
> **预计工作量**:8-10 小时(1-1.5 天)

---

## 🎯 优化目标

把"指标过滤 + 散点图 + 候选清单"升级为**大师方法论评分驱动**的筛选驾驶舱:

1. 每套预设(格雷厄姆 / 巴菲特 / 林奇 / ...)有**完整方法论说明卡**(默认折叠 expander)
2. 候选清单**按分数从高到低排序**
3. 高分公司行(≥ excellent 阈值)**绿色背景填充**
4. 每行**新增"加入观察池"checkbox 列**(替代当前底部 multiselect)

---

## 🩺 当前痛点

| 现状 | 问题 |
|---|---|
| 3 个预设(buffett/graham/growth)只有一行 description | 用户看不到每个方法的"7 项硬指标 / 评分阈值 / 历史背景" |
| 当前用 8 个原始指标硬过滤(布尔 pass/fail) | **没用 .tools/rules/ 的大师评分体系**(graham.yaml 已有 10 分制) |
| 候选清单按 DataFrame 默认顺序(ticker?) | 没排序 → 用户分不清"谁更优" |
| 候选清单纯白底 | 高分/低分视觉权重一样,无层级 |
| 加入观察池 = 底部 multiselect + 全选默认 | 想精挑只勾 1-2 家不顺手,得反向取消勾选 |
| `growth` 预设和 lynch.yaml 没关联 | 大师方法论分散,前端只用了 3 套硬规则 |

---

## 🆕 新版面设计

```
┌────────────────────────────────────────────────────────────────────┐
│ 🔍 L2 公司筛选 — 哪些值得深看?                                       │
├────────────────────────────────────────────────────────────────────┤
│ [💎 巴菲特] [🛡️ 格雷厄姆] [🚀 林奇成长] [🎯 格林布拉特] [⚙️ 自定义]  │
├────────────────────────────────────────────────────────────────────┤
│ 📖 当前方法:🛡️ 格雷厄姆深度价值                                     │
│ ┌──────────────────────────────────────────────────────────────┐   │
│ │ 一句话定位:5 毛钱买 1 块钱的资产 — 安全边际为王                │   │
│ │                                                                │   │
│ │ ▼ 方法论详情(展开)                                             │   │
│ │   • 来源:《聪明的投资者》第 14 章(防御型投资者 7 项)         │   │
│ │   • 评分制:10 分制(7 项硬指标 + Graham Number)              │   │
│ │   • 阈值:≥8 优秀 🟢 / ≥6 合格 🟡 / <4 不及格 🔴             │   │
│ │   • 7 项硬指标:                                                │   │
│ │     ① 公司规模 ≥ 500 亿(1分)                                 │   │
│ │     ② 流动比率 ≥ 2 + 长期负债 ≤ 净流动资产(1分)             │   │
│ │     ③ 10 年盈利稳定性(2分)                                   │   │
│ │     ④ 持续派息 ≥ 10 年(1分)                                  │   │
│ │     ⑤ 10 年盈利增长 ≥ 33%(1分)                               │   │
│ │     ⑥ PE-TTM ≤ 15(2分)                                      │   │
│ │     ⑦ PB ≤ 1.5(可放宽 PE × PB ≤ 22.5)(2分)                 │   │
│ │   • Graham Number:√(22.5 × EPS × BVPS)= 合理价格上限         │   │
│ │   • 适用:大盘蓝筹、银行保险、稳定龙头                          │   │
│ │   • 不适用:成长股、亏损早期公司、高估值科技                    │   │
│ │   • 知识库:[01_价值投资法/04_估值分析.md](...)                │   │
│ └──────────────────────────────────────────────────────────────┘   │
├────────────────────────────────────────────────────────────────────┤
│ 命中统计:总 15 家 · 通过 5 家 · 通过率 33% · 满分 10/10           │
├────────────────────────────────────────────────────────────────────┤
│ 📍 散点矩阵(保留 ✓ — 改 X=分数 / Y=ROE / 大小=权重)              │
├────────────────────────────────────────────────────────────────────┤
│ 📋 候选清单(★按分数从高到低 · ★ ≥8 绿色背景)                     │
│ ┌──☑─公司────代码────分数──评级──PE──ROE──F-Score──加入观察池──┐ │
│ │ ✅ 招商银行  600036  9/10  🟢优秀  6.5  16%  7/9   [☑加入]    │🟢│
│ │ ✅ 伊利股份  600887  8/10  🟢优秀  18.2 24%  8/9   [☑加入]    │🟢│
│ │    美的集团  000333  7/10  🟡合格  14.8 22%  7/9   [☐加入]    │   │
│ │    五粮液    000858  5/10  🟡合格  21.0 28%  6/9   [☐加入]    │   │
│ │    贵州茅台  600519  3/10  🔴不及格 24.0 30%  9/9  [☐加入]    │   │
│ │    宁德时代  300750  2/10  🔴不适用 35.0 12% 5/9   [☐加入]    │   │
│ └──────────────────────────────────────────────────────────────┘   │
│  📥 一键加入勾选项(2)→ .temp/watchlist.md                         │
└────────────────────────────────────────────────────────────────────┘
```

---

## ✅ 实施 Checklist(按 ROI 排序)

### 优化项 #1 — 候选清单按分数排序 + 高分绿背景 + checkbox 列(4h,核心交互)

- [ ] 将当前 `st.dataframe` 升级为 `st.data_editor` 或预渲染 `styler`
- [ ] 新增 `score` 列(从大师评分引擎拿,见 #3),按 `score DESC` 排序
- [ ] 新增 `rating` 列:`🟢 优秀 / 🟡 合格 / 🔴 不及格`(按 yaml `threshold` 字段)
- [ ] 高分行(`score >= excellent_threshold`)整行 `background-color: #d4edda`(浅绿)
- [ ] 新增 `加入观察池` 列(`st.column_config.CheckboxColumn`),默认全 False
- [ ] 替换底部 multiselect → "📥 一键加入勾选项" 按钮,读 data_editor 的 checkbox 列状态
- [ ] 删除当前 `default=filtered["name"].tolist()`(默认全选不合理)

```python
# 关键代码片段
def _style_row(row):
    if row['score'] >= excellent_th:
        return ['background-color: #d4edda'] * len(row)
    elif row['score'] >= good_th:
        return ['background-color: #fff3cd'] * len(row)
    return [''] * len(row)

styled = filtered.sort_values('score', ascending=False).style.apply(_style_row, axis=1)
edited = st.data_editor(
    styled,
    column_config={
        '加入观察池': st.column_config.CheckboxColumn(default=False),
        ...
    },
    disabled=[c for c in cols if c != '加入观察池'],
    hide_index=True,
)
```

**用户价值**:**3 秒锁定 top 候选** + 视觉权重清晰 + 单行勾选直观。

### 优化项 #2 — 每个预设方法论说明卡(3h)

- [ ] 在 `presets.yaml` 每个 preset 增加字段:
  - `tagline`(一句话定位)
  - `book_origin`(来源典籍)
  - `score_max`(最高分,默认 10)
  - `thresholds`(`excellent / good / warning`)
  - `rules_summary`(7-9 条核心规则的简洁列表)
  - `applicable / not_applicable`(适用/不适用场景)
  - `knowledge_link`(对应知识库 md 路径)
- [ ] 选定预设后,顶部 `st.container(border=True)` 显示 tagline
- [ ] `st.expander("▼ 方法论详情", expanded=False)` 展开看完整 rules_summary
- [ ] **优先复用 `.tools/rules/*.yaml`** — graham.yaml 已有完整结构,只需 `_load_master_rules(name)` 读它,不需要在 presets.yaml 重复维护

**4 套方法论卡片对应**(可全部从 .tools/rules/ 读):

| 预设 | 来源 yaml | 一句话定位 |
|---|---|---|
| 🛡️ 格雷厄姆深度 | [graham.yaml](../rules/graham.yaml) | 5 毛钱买 1 块钱的资产 — 安全边际为王 |
| 💎 巴菲特护城河 | [buffett.yaml](../rules/buffett.yaml) | 用合理价格买伟大企业,长期持有 |
| 🚀 林奇成长 | [lynch.yaml](../rules/lynch.yaml) | PEG ≤ 1 的快速增长公司 |
| 🎯 格林布拉特神奇公式 | [greenblatt.yaml](../rules/greenblatt.yaml) | EBIT 收益率 + ROC 双高 |
| ⚙️ 自定义 | — | 8 个原始指标自由组合 |

### 优化项 #3 — 接入大师评分引擎(4h,数据底座)

- [ ] 新增 `screener.score_with_master(df, master_id, year)` 函数
- [ ] 调用 [.tools/score/engine.py](../score/engine.py) 的 `run_score(rules_path, data, year)`(已有,公司主页用过)
- [ ] 批量遍历 15 家公司 × 选定大师 = 15 次评分,缓存 `@st.cache_data(ttl=3600)`
- [ ] 输出 `score / max / rating / detail_pass_count`,合并到 filtered DataFrame
- [ ] 自定义模式:维持当前布尔过滤,`score = NaN` → 不参与排序着色
- [ ] **离线验证**:跑一遍 graham 评分,确认 [graham.yaml expected_a_share_fit](../rules/graham.yaml#L110) 预期排名 — 招商银行 8-10 / 伊利 7-9 / 茅台 2-4

### 优化项 #4 — checkbox 加入观察池(已合并到 #1)

(列入 #1 一并实现)

### 优化项 #5 — 散点图轴改"分数"(1h,锦上添花)

- [ ] X 轴从 `pe_pct_10y` 改 `score`(0-10),Y 维持 ROE
- [ ] 颜色编码改成 `rating`(绿/黄/红 3 档),不再用 F-Score 渐变(避免与新 score 列重复)
- [ ] 加 vline `score=excellent_th` 红线,用户一眼看"哪些点过线了"

---

## 📋 数据/配置改动清单

### `presets.yaml` 扩展

```yaml
presets:
  - id: graham
    name: 格雷厄姆深度
    icon: "🛡️"
    description: 低 PE + 低 PB + 高股息 — 安全边际优先的深度价值
    tagline: 5 毛钱买 1 块钱的资产 — 安全边际为王         # ★新增
    rules_yaml: graham                                      # ★新增 → 读 .tools/rules/graham.yaml
    book_origin: "《聪明的投资者》第 14 章"                  # ★新增
    knowledge_link: "01_knowledge/03_投资策略与选股/01_价值投资法/04_估值分析.md"  # ★新增
    # 原 filters 段保留(快速过滤,不通过 = 不评分)
    filters: ...
```

### `screener.py` 新增

- `load_master_rules(master_id)` — 读 .tools/rules/{master_id}.yaml
- `score_with_master(df, master_id, year)` — 批量评分,返回 score/max/rating
- `format_rating(score, thresholds)` — 转 🟢/🟡/🔴 emoji

### `tabs/screener.py` 改动

- `render()` 顶部加方法论说明卡 expander
- 候选清单段重写:`data_editor + styled + checkbox 列`
- 删除当前底部 multiselect + button,改"📥 一键加入勾选项"

---

## 🚀 推荐执行顺序

| # | 任务 | 工作量 | 依赖 |
|---|---|---|---|
| 1 | #3 接入大师评分引擎(数据底座) | 4h | engine.py / rules yaml — 已就绪 |
| 2 | #1 候选清单排序 + 绿背景 + checkbox 列 | 4h | 依赖 #1 的 score 字段 |
| 3 | #2 方法论说明卡 | 3h | 仅 yaml 改 + UI 渲染 |
| 4 | #5 散点图轴改分数 | 1h | 依赖 #1 |
| 5 | (并行)`presets.yaml` 加 `lynch / greenblatt` 两套 | 1h | 复用 .tools/rules/ |

**总计 12-13 小时**,可拆 2 天完成。

---

## ⚠️ 风险与注意

1. **评分性能**:15 家 × 1 大师评分 ≈ 1-2s(已知 piotroski 单次 ~100ms)— 必须 `@st.cache_data` 否则切预设卡顿
2. **缺失数据兜底**:graham.yaml 第 6 项要 EPS 10 年,部分公司不足 10 年 → engine.py 已处理,UI 上 `score=NaN` 显示 "—"
3. **`st.data_editor` 与 `style` 兼容性**:Styler 在 data_editor 中**只读** — 如果要 checkbox 列,需用普通 DataFrame + 手动用 emoji 表示分数等级,或拆成"展示表 + 选择控件"两块
4. **行业差异**:graham 不适用宁德/比亚迪 → UI 上需明确标注 "🔴 不适用"(不是"差")避免误导
5. **银行保险变体**:.tools/rules/ 已有 `piotroski_bank.yaml` `piotroski_insurance.yaml` — 招行/新华应自动用变体,score 函数需识别行业

---

## 📝 决策记录

| 日期 | 决策 | 备注 |
|------|------|------|
| 2026-05-04 | 候选清单加 checkbox 列代替底部 multiselect | 单行勾选比反向取消勾选直观 |
| 2026-05-04 | 高分行用 `#d4edda` 浅绿背景 | 与 SWS 视觉语言绿色一致 |
| 2026-05-04 | 评分体系直接复用 .tools/rules/ yaml | 不在 presets.yaml 重复维护 |
| 2026-05-04 | 不适用行业标 "🔴 不适用" 而非 "🔴 不及格" | graham 给宁德 2 分不代表宁德差,只是不在格雷厄姆框架内 |

---

## 🔗 相关文件

- 当前实现:[tabs/screener.py](tabs/screener.py) · [screener.py](screener.py) · [presets.yaml](presets.yaml)
- 评分引擎:[.tools/score/engine.py](../score/engine.py) · [.tools/score/multi_master.py](../score/multi_master.py)
- 大师 yaml:[.tools/rules/](../rules/)(graham / buffett / lynch / greenblatt / damodaran / altman / piotroski 含 _bank/_insurance 变体)
- 知识库:[01_knowledge/03_投资策略与选股/](../../01_knowledge/03_投资策略与选股/)
- 整体重设计:[REDESIGN_TODO.md](REDESIGN_TODO.md) · [OPTIMIZATION_M1_市场周期.md](OPTIMIZATION_M1_市场周期.md)
