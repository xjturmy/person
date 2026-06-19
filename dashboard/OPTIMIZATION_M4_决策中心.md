# 模块 4 优化记录:💼 决策中心 · 持仓总览智能录入

> 文件:[tabs/decision_center.py](tabs/decision_center.py) · [.tools/portfolio/](../portfolio/) · [portfolio.yaml](../portfolio/portfolio.yaml)
>
> **创建**:2026-05-05
> **状态**:✅ 全部交付(#1+#2+#3+#4+#5 五项均已落地)
> **预计工作量**:12-16 小时(2 天)

---

## 🎯 优化目标

让"持仓总览"从**只读展示**升级为**智能录入工作台**:

1. **截图识别**:粘贴/上传券商 App / Wind / 同花顺持仓截图,VLM 识别公司/股数/成本/现价 → 表格预览
2. **批量文本识别**:支持复制券商导出的纯文本(逗号/Tab/空格分隔均可)→ 自动结构化解析
3. **逐行确认**:识别结果显示成"待添加候选清单",每行带 ☑ 勾选 + 字段可编辑 + 跳过原因
4. **写入 portfolio.yaml**:用户确认后,新增/合并到现有 holdings(已有 ticker 默认更新数量,可改为追加)

核心交互:**识别 → 校验 → 勾选 → 编辑 → 一键写入**。

---

## 🩺 当前痛点

| 现状 | 问题 |
|---|---|
| 持仓必须手编辑 [portfolio.yaml](../portfolio/portfolio.yaml) | 15 家公司起步阻力大,每家要填 ticker/shares/cost/date/weight 等 8 个字段 |
| `_meta.status: demo` 状态长期停在 demo | 用户没有便捷入口转 live,持仓总览大概率看到空 |
| 决策日志是手填表单,但持仓数据本身却没有录入入口 | 数据闭环断裂:用户在券商交易完,要回来手编 yaml |
| 月度复盘只读历史 PDF,缺一键打通"再平衡建议 → 修改持仓 → 写回 yaml" | 复盘是独白,不是反馈环 |

---

## 🆕 新增交互流程

### 流程 A:截图识别(主路径)

```
┌────────────────────────────────────────────────────────────────────┐
│ 💼 决策中心 → 段 1 持仓总览 → "📥 智能录入" expander                 │
├────────────────────────────────────────────────────────────────────┤
│ [📷 上传截图] [📋 粘贴文本] [✏️ 手动新增] 三个选项                   │
└────────────────────────────────────────────────────────────────────┘
                            ↓ (上传 1 张或多张持仓截图)
┌────────────────────────────────────────────────────────────────────┐
│ 🔍 VLM 识别中...(Claude Vision API)                                  │
│ 提示词:"识别这张持仓截图中的每只股票:                                 │
│         返回 JSON 数组,每条包含 ticker/name/shares/cost_basis/      │
│         last_price 字段。代码标准化为 6 位(A 股)/ 5 位(港股)。"  │
└────────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────────┐
│ 📋 识别结果(7 条候选,3 条命中现有 portfolio,4 条新增)              │
│  ┌─☑─公司────代码──股数──成本价──现价──状态──────备注─────────┐  │
│  │ ☑ 贵州茅台  600519  100   1500.0  1612  🟡 已持仓(更新数量) │ │
│  │ ☑ 招商银行  600036  500   34.5    36.8  🆕 新增              │ │
│  │ ☑ 美的集团  000333  200   65.0    72.1  🆕 新增              │ │
│  │ ☐ 比亚迪    002594  100   240.0   268   ⚠️ 不在 15 家清单    │ │
│  │ ☐ 平安银行  000001  1000  10.5    11.2  ❌ 不在 15 家清单    │ │
│  │ ☐ ?         ??????  ???   ???     ???   🔴 识别失败,请检查    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                    │
│  默认逻辑:                                                          │
│   • 在 companies.csv 15 家内 + 字段完整 → 默认勾选 ☑                │
│   • 不在 15 家清单 → 默认不勾 ☐(可勾选 + 自动加入 companies.csv)  │
│   • 识别失败 → 默认不勾 ☐ + 标红 + 提示手动修正                     │
│                                                                    │
│  [💾 写入 portfolio.yaml(已勾选 3 条)] [🔄 重新识别] [✏️ 编辑]   │
└────────────────────────────────────────────────────────────────────┘
                            ↓ (用户确认)
┌────────────────────────────────────────────────────────────────────┐
│ ✅ 已写入 3 条 — portfolio.yaml `_meta.status` 自动从 demo → live    │
│ 📌 备份原文件到 .tools/portfolio/portfolio.yaml.bak.20260505_1430   │
└────────────────────────────────────────────────────────────────────┘
```

### 流程 B:批量文本识别(辅助路径)

```
┌────────────────────────────────────────────────────────────────────┐
│ 📋 粘贴持仓文本(支持 6 种常见格式自动识别)                          │
│ ┌────────────────────────────────────────────────────────────────┐ │
│ │ 600519,100,1500                                                │ │
│ │ 600036,500,34.5                                                │ │
│ │ 000333  200  65.0     # Tab 分隔                              │ │
│ │ 美的集团 000333 200股 成本65.00         # 中文混合              │ │
│ │ 600519 贵州茅台 100 1500.00 1612.00 11.20% 浮盈+11200          │ │
│ │ ...                                                              │ │
│ └────────────────────────────────────────────────────────────────┘ │
│ [🔍 解析] (调用本地正则 + LLM 兜底)                                 │
└────────────────────────────────────────────────────────────────────┘
                            ↓
                   (同流程 A 的"识别结果"卡片)
```

### 流程 C:再平衡建议 → 一键执行

```
┌────────────────────────────────────────────────────────────────────┐
│ 🚨 当前提示(段 1 已有的 rebalance_alerts)                          │
│ - ⚠️ 贵州茅台权重 25%(超上限 20%)→ 减仓 5pp                       │
│ - ⚠️ 招商银行 PE 分位 92%(>85% 上限)→ 减仓评估                    │
│                                                                    │
│ [✏️ 一键调整 yaml(批量预览)] ← 新增按钮                          │
└────────────────────────────────────────────────────────────────────┘
                            ↓
┌────────────────────────────────────────────────────────────────────┐
│ 修改预览(diff 形式)                                                │
│  - target_weight: 0.25  →  + target_weight: 0.20  (贵州茅台)       │
│  + 自动追加决策日志:动作=减仓 / Δ-5%                                │
│ [✅ 确认应用] [❌ 取消]                                              │
└────────────────────────────────────────────────────────────────────┘
```

---

## ✅ 实施 Checklist(按 ROI 排序)

### 优化项 #1 — 批量文本解析(4h,先做最简版,无 API 依赖)

- [x] 新建 [.tools/portfolio/parse_holdings.py](../portfolio/parse_holdings.py)
- [x] 实现 `parse_text(raw: str) -> list[ParsedHolding]`
- [x] 支持 6 种常见格式:
  - `code,shares,cost`(CSV)
  - `code\tshares\tcost`(TSV)
  - `code shares cost`(空格)
  - `name code shares cost`(中英混合)
  - 含百分号/¥符号(自动剔除)
  - 一行一只股
- [x] 用正则匹配 ticker(6 位数字 / 港股 5 位)+ 关键字(股/cost/成本)定位字段
- [x] **失败兜底**:无法解析的行单独列出,标红显示,让用户手动修正
- [x] 单元测试:覆盖 6 种格式 + 3 种异常输入

### 优化项 #2 — 候选清单 UI + 写入 yaml(4h)

- [x] 在 [tabs/decision_center.py](tabs/decision_center.py) 段 1 顶部加 `📥 智能录入` expander
- [x] 三选项 tab:`📷 截图 | 📋 文本 | ✏️ 手动`
- [x] 解析后用 `st.data_editor` 渲染候选,带:
  - `加入` checkbox 列(`column_config.CheckboxColumn`)
  - 字段可编辑(shares / cost_basis / target_weight)
  - `状态` 列(🟡 已持仓更新 / 🆕 新增 / ⚠️ 不在 15 家 / 🔴 识别失败)
- [x] 写入逻辑:
  - 调用 `loader.save_portfolio(updated_yaml_dict, backup=True)`(loader.py 加新方法)
  - 备份原 yaml 到 `.bak.{timestamp}` 后写入
  - 已存在 ticker → 默认 update;不存在 → append 到 holdings 列表
  - `_meta.status: demo` → 自动改 `live`(若用户首次写入)
- [x] 写入后调 `st.rerun()` 让段 1 持仓总览自动刷新

### 优化项 #3 — 截图识别(VLM 接入,4h)

- [x] 新建 [.tools/portfolio/parse_screenshot.py](../portfolio/parse_screenshot.py)
- [x] 用 Anthropic SDK + Claude Vision(已有 Claude Code 登录态可复用)
- [x] 提示词模板(写入 `.tools/portfolio/prompts/holdings_extract.md`):
  ```
  识别这张持仓截图。返回严格 JSON 数组,字段:
  - ticker: 标准化 6 位 A 股 / 5 位港股代码
  - name: 公司名(中文)
  - shares: 持有股数(纯数字)
  - cost_basis: 成本价(每股,人民币)
  - last_price: 现价(每股,可选)
  无法识别的字段填 null。
  绝不编造,识别不到的整条留空。
  ```
- [x] 输出 schema 用 `tool_use` 强约束,避免 LLM 自由发挥
- [x] 错误兜底:识别失败显示原图 + 让用户手动改
- [x] **首次使用**提示用户:"截图会上传到 Anthropic API,确认后继续"(隐私)

### 优化项 #4 — 候选状态智能识别(2h,数据闭环)

- [x] 解析结果 ticker 与 [companies.csv](../../.config/companies.csv) 比对:
  - 在 → `🟡 已持仓 / 🆕 新增`
  - 不在 → `⚠️ 不在 15 家清单(可勾选自动加入)`
- [x] ticker 与 portfolio.yaml.holdings 比对:
  - 在 → `已持仓 → 更新数量/成本`
  - 不在 → `新增`
- [x] 字段完整性检查:`shares 必填 + cost_basis 必填 + ticker 6/5 位` → 失败标红

### 优化项 #5 — 再平衡建议一键执行(2h,选做)

- [x] 段 1 现有的 `rebalance_alerts` 加"修复建议"字段
- [x] 加按钮"✏️ 一键调整 yaml(批量预览)"
- [x] 用 `git diff` 风格预览修改 → 用户 ✅ 后写入 + 自动加决策日志条目
- [x] 风险:破坏性操作,**需 confirm 二次弹窗**

---

## 📋 配置改动清单

### 新增依赖

```
anthropic>=0.40.0      # 已有(Claude API)
pyyaml                  # 已有
```

### 新增文件

```
.tools/portfolio/parse_holdings.py        # 文本解析
.tools/portfolio/parse_screenshot.py      # VLM 截图解析
.tools/portfolio/prompts/holdings_extract.md  # VLM 提示词
.tools/portfolio/loader.py(扩展)         # 加 save_portfolio() 方法
```

### `tabs/decision_center.py` 改动

- `_render_holdings_overview()` 顶部插入 `_render_smart_intake()`
- 新增 `_render_smart_intake()` 处理 3 路输入 + 候选清单 UI
- 新增 `_apply_to_yaml()` 写入逻辑

---

## 🚀 推荐执行顺序

| # | 任务 | 工作量 | 依赖 |
|---|---|---|---|
| 1 | #1 批量文本解析(先做最低门槛入口) | 4h | 无依赖 |
| 2 | #2 候选清单 UI + yaml 写入 | 4h | #1 数据结构 |
| 3 | #4 智能识别状态(已持仓/新增/不在清单) | 2h | #2 已有候选 dataframe |
| 4 | #3 截图识别 VLM 接入 | 4h | API key + 复用 #2 UI |
| 5 | #5 再平衡建议一键执行(选做) | 2h | yaml 写入封装就绪 |

**总计 16 小时**,可拆 2 天完成。**先做文本解析(#1+#2)即可解决 80% 录入痛点,截图(#3)是锦上添花。**

---

## ⚠️ 风险与注意

| 风险 | 处理 |
|---|---|
| **VLM 识别错误**:股数小数点位 / 港股 vs A 股 ticker 混淆 | 用户必须**逐行确认**才写入,不允许"识别即写" |
| **破坏 portfolio.yaml**:写入失败导致丢配置 | 每次写入前自动 `.bak.{timestamp}` 备份 + 用户可一键回滚 |
| **截图含敏感信息**(总资产/账户号) | UI 上明确提示"截图会上传 API",可选 OCR 本地预处理裁剪 |
| **批量录入后 sneak in 错数据** | 写入后顶部 toast `✅ 已写入 N 条 + 备份位置`,提示用户立即在持仓总览校验 |
| **companies.csv 不在 15 家** | 不强制扩,默认不勾选;勾选后追加到 csv 末尾,提示用户跑 `update_pipeline.py` 抓数据 |
| **decisions.duckdb 联动** | 写入后自动追加决策日志(action=新增/调仓 + rationale="智能录入" + 时间戳) |

---

## 💡 用户体验亮点

1. **零阻力首次使用**:截一张券商 App 持仓页 → 拖进 Dashboard → 3 秒看到候选清单
2. **逐行可控**:LLM 识别可能错,所有结果默认"待确认",用户必须勾选才写入
3. **状态智能**:🟡/🆕/⚠️/🔴 4 档颜色一眼分清"哪些是更新 / 哪些是新增 / 哪些得拒绝"
4. **可回滚**:每次写入备份,出错可秒回
5. **数据闭环**:智能录入 → portfolio.yaml → 持仓总览 → 再平衡建议 → 决策日志,全在一页内闭合

---

## 📝 决策记录

| 日期 | 决策 | 备注 |
|------|------|------|
| 2026-05-05 | 优先做文本解析(#1+#2),截图作为 phase 2 | 文本解析无 API 依赖,ROI 最高 |
| 2026-05-05 | VLM 用 Anthropic Claude Vision,不引第三方 OCR | 复用现有 API 链路,统一维护 |
| 2026-05-05 | 写入前必须 `.bak.{timestamp}` 备份 | 破坏性操作的最低安全网 |
| 2026-05-05 | 默认勾选规则:在 15 家 + 字段完整才默认勾 | 避免误写不属于本投研框架的股票 |
| 2026-05-05 | "识别失败"行不允许写入(只能编辑后写) | 减少脏数据进 yaml |
| 2026-05-05 | #1+#2+#4 已交付(文本路径 + UI + 状态识别),#3 截图 / #5 再平衡占位待做 | 文本路径已能解决 80% 录入痛点,可先验收使用 |

---

## ✅ 交付记录(2026-05-05)

### 已落地

- [x] **#1 文本解析**:[parse_holdings.py](../portfolio/parse_holdings.py) — 支持 6 种格式 + 港股 5 位 + ¥ 货币符 + 噪声词过滤,15 项单测全过([test_parse_holdings.py](../portfolio/test_parse_holdings.py))
- [x] **#4 状态识别**:`classify()` 返回 ok_existing 🟡 / ok_new 🆕 / not_in_universe ⚠️ / parse_failed 🔴 / incomplete 🔴 五档,默认勾选规则正确
- [x] **loader 写入封装**:`save_portfolio()` + `upsert_holdings()` 在 [loader.py](../portfolio/loader.py),自动 `.bak.{ts}` 备份,demo→live 自动翻转,12 项单测全过([test_loader_save.py](../portfolio/test_loader_save.py))
- [x] **#2 UI**:`_render_smart_intake()` 三 tab(粘贴文本 / 截图占位 / 手动新增),候选清单用 `st.data_editor` 带 checkbox + 字段可编辑,headless streamlit 启动无异常

### 占位待做

- [x] **#3 截图 VLM**:[parse_screenshot.py](../portfolio/parse_screenshot.py) + [prompts/holdings_extract.md](../portfolio/prompts/holdings_extract.md);Streamlit `st.file_uploader` + Claude Vision (model=`claude-sonnet-4-6`),响应 JSON 解析容错(fence / 前后说明文字),无 ANTHROPIC_API_KEY 友好降级提示;12 项单测通过([test_parse_screenshot.py](../portfolio/test_parse_screenshot.py))
- [x] **#5 再平衡一键**:[rebalance_planner.py](../portfolio/rebalance_planner.py) — `plan()` 输出结构化 `RebalanceProposal`(含 ticker/old/new/delta/rationale/review_only),`apply_proposals()` 自动 `upsert_holdings` + `decisions.insert`;UI 含 diff 预览 + 二次确认 checkbox;14 项单测通过([test_rebalance_planner.py](../portfolio/test_rebalance_planner.py))

---

## 🔗 相关文件

- 当前实现:[tabs/decision_center.py](tabs/decision_center.py) · [.tools/portfolio/holdings_view.py](../portfolio/holdings_view.py) · [.tools/portfolio/loader.py](../portfolio/loader.py)
- 配置:[portfolio.yaml.example](../portfolio/portfolio.yaml.example) · [companies.csv](../../.config/companies.csv)
- 决策日志:[.tools/decisions/](../decisions/)
- 整体重设计:[REDESIGN_TODO.md](REDESIGN_TODO.md)
- 同系列:[OPTIMIZATION_M1_市场周期.md](OPTIMIZATION_M1_市场周期.md) · [OPTIMIZATION_M2_公司筛选.md](OPTIMIZATION_M2_公司筛选.md) · [OPTIMIZATION_M3_单公司详情.md](OPTIMIZATION_M3_单公司详情.md)
