# 🎓 大师分析法 · 8 模块总纲

> **状态**:📋 规划记录 — [M6 林奇](OPTIMIZATION_M6_彼得林奇分析法.md)✅ 已交付独立五步 Tab。
> M7-M13 中,**格雷厄姆 / 巴菲特(Buffett v2)/ Piotroski(F-Score)/ 芒格 / 八师投票** 已在
> v2.4-v2.9 陆续以各自形态落地(见 `tabs/graham_analysis.py` · `munger_analysis.py` ·
> `score/` 评分引擎 + 公司研究页七师投票);本表的"5 步同构骨架 + 通用基类"为当年统一规划设想,
> **实际落地未严格走单一基类**(各大师独立实现)。其余大师按需展开。
>
> **创建**:2026-05-05

---

## 🎯 整体思路

每位大师独立 Tab,**5 步同构 + 口径各异**:
- 同构:每个 Tab 都是 5 个 sub-tab(① 入场判断 / ② 核心指标 / ③ 估值口径 / ④ 风险审视 / ⑤ 决策落地)+ 顶部 banner + 底部综合结论
- 异质:每位大师在每一步用各自的阈值、公式、红线

**好处**:用户切大师 = 切方法论,不需要重新学 UI;支持多大师横向对比(M13)。

---

## 🌳 8 大师映射表(总览)

| 模块 | 大师 | ① 入场判断 | ② 核心指标 | ③ 估值口径 | ④ 风险审视 | ⑤ 决策落地 |
|:-:|---|---|---|---|---|---|
| **M6** ✏️ | 🌱 **林奇** | 六类公司分类 + 故事脚本 | CAGR 持续性 + 销量 vs 价格驱动 | PEG ≤ 1.0 | 资产负债率 > 40%(快速增长铁律)| 类型驱动仓位 |
| M7 | 🛡️ 格雷厄姆 | 公司规模 ≥ 500 亿 + 行业稳定 | 7 项硬指标(盈利稳定/派息/增长) | Graham Number = √(22.5×EPS×BVPS) | PE > 15 / PB > 1.5 任一不满足 | 10 分制,8+ 重仓 |
| M8 | 💎 巴菲特 | 看得懂 + ROE > 15% 持续 5y | 护城河 4 类 + 自由现金流 + 资本支出 | 内在价值 = 未来现金流折现 | 资本支出/利润 > 50%(重资产)| 重仓 / 长持 / 不卖 |
| M9 | 🎯 格林布拉特 | 非金融非公用 | EBIT/EV(收益率)+ ROC(资本回报率) | 神奇公式排序前 30% | 周期股慎用 | 自动选股 + 1 年再平衡 |
| M10 | 📐 Damodaran | 商业成熟度 + 数据可获得 | 收入增速 / EBIT 利润率 / 再投资率 | DCF 三阶段 + WACC | 假设敏感性测试(±20%)| MOS > 30% 入,< 0 出 |
| M11 | 🔬 Piotroski | F-Score 9 项 | 盈利 4 项 / 负债流动性 3 项 / 经营效率 2 项 | 不算估值,只算财务质量 | F < 4 直接拒绝 | 8-9 重仓 / 5-7 中仓 / 0-4 拒 |
| M12 | ⚠️ Altman | 制造业 / 服务业(双口径)| Z = 1.2A + 1.4B + 3.3C + 0.6D + 1.0E | Z 值阈值 | Z < 1.81 破产风险高 | 仅作风险预警,不主导买入 |
| M13 | 🤝 八师投票 | 综合 8 大师评分 | 通过率 + 平均分 + 一致性 | 八师共识 = 加权平均 | 分歧度过高 → 标"看法分裂"| ≥6 票 重仓 / 4-5 中 / ≤3 拒 |

> ✏️ = 已动笔(完整文档),其余仅本表占位

---

## 🆕 通用 Tab 骨架(8 大师共用)

```
┌──────────────────────────────────────────────────────────────────────┐
│ {icon} {大师名} · {方法论一句话}                                       │
├──────────────────────────────────────────────────────────────────────┤
│ [公司 ▼ 比亚迪 002594]  [年份 ▼ 2024]  [🔄 重新评估]   ⏱ 上次:5/3   │
│ ★ {大师视角下的当前定位}                                               │
└──────────────────────────────────────────────────────────────────────┘
              [① 入场判断] [② 核心指标] [③ 估值口径] [④ 风险审视] [⑤ 决策]
                                ↓
                每个 sub-tab:📖 框架说明 → 📊 数据展示 → ✅/❌ 结论
                                ↓
               🎯 五步综合结论 banner + [💾 写入决策日志] [📤 导出 md]
```

---

## 📁 sidebar 折叠组(M0 联动)

```
🌐 市场视角:
  📊 市场周期
  🔍 公司筛选

🏢 公司视角:
  🏢 单公司详情

🎓 大师分析法:                    ← 8 大师独立 Tab,折叠组默认展开
  🌱 林奇(M6) ✏️
  🛡️  格雷厄姆(M7)
  💎 巴菲特(M8)
  🎯 格林布拉特(M9)
  📐 Damodaran(M10)
  🔬 Piotroski(M11)
  ⚠️  Altman(M12)
  🤝 八师投票(M13)

💼 决策视角:
  💼 决策中心
```

> 注:上为当年规划的 sidebar 折叠组设想。实际 v2.9 导航为 5 页扁平 radio
> (🌡️ 市场 & 行业 · 🔍 选股 · 🏢 公司研究 · 💼 决策中心 · 🥇 黄金),
> 大师分析法并入「公司研究 / 选股」子 Tab,Claude 终端项已下线。

---

## 🧰 通用基类(动手时再实现)

新建 [.tools/dashboard/master_analysis_base.py](master_analysis_base.py)(规划):

```python
class MasterAnalysisTab:
    """8 大师共用骨架 — 子类只需提供 5 步的 step_xxx() 方法。"""
    master_id: str          # graham / buffett / lynch / ...
    master_cn: str          # "格雷厄姆"
    icon: str
    philosophy_one_line: str

    def render_top_banner(self, ticker, year): ...
    def render_step_tabs(self): ...
    def render_summary_banner(self): ...
    def export_decision_md(self, ticker): ...

    # 子类必须 override
    def step_1_entry(self, ticker, year): raise NotImplementedError
    def step_2_metrics(self, ticker, year): raise NotImplementedError
    def step_3_valuation(self, ticker, year): raise NotImplementedError
    def step_4_risk(self, ticker, year): raise NotImplementedError
    def step_5_decision(self, ticker, year): raise NotImplementedError
```

每个大师 Tab `class GrahamTab(MasterAnalysisTab)` 只需 ~150 行(覆盖 5 个 step_xxx()),不重复造骨架。

---

## 🚀 推荐展开顺序(用时再决定)

| 顺序 | 模块 | 工作量 | 依据 |
|:-:|---|:-:|---|
| 1 | **M6 林奇** ✏️(已落) | 10h | 用户优先 + lynch_classifier 已有 |
| 2 | M7 格雷厄姆 | 2.5h | graham.yaml 完整 + 新华保险已有人工五步样本 |
| 3 | M11 Piotroski | 1.5h | engine.py 已实现 9 项,UI 套壳即可 |
| 4 | M13 八师投票 | 2h | 集大成,前若干个完工就能做 |
| 5 | M9 格林布拉特 | 2h | 公式简单,数据齐 |
| 6 | M8 巴菲特 | 2.5h | 数据齐,但定性维度多需提示用户 |
| 7 | M12 Altman | 1.5h | 公式 5 项简单 |
| 8 | M10 Damodaran | 2h | DCF 数据接入复杂,放最后 |

---

## ⚠️ 关键约定(动手前先达成共识)

1. **M3 单公司详情**不再嵌"七大师投票" — 改为 M13 独立 Tab,M3 只显示一行"已通过 N/8 师 → 详见 M13"链接
2. **大师 yaml** 全部按 [_schema.md](.tools/rules/_schema.md) 对齐 — 通用基类才能批量驱动
3. **决策日志统一格式**:`02_companies/{N}_{name}/05_投资决策/{master}_五步分析_{date}.md`,与[新华保险格雷厄姆模板](../../02_companies/01_新华保险/05_投资决策/02_格雷厄姆投资法_新华保险五步分析.md)对齐
4. **Damodaran DCF 数据缺口**:WACC / 永续增长率需用户输入,不强算
5. **金融业适配**:格雷厄姆/Piotroski 的银行/保险变体已在 [.tools/rules/](.tools/rules/) 就绪,基类需识别行业自动选 yaml

---

## 📝 决策记录

| 日期 | 决策 | 备注 |
|------|------|------|
| 2026-05-05 | 8 大师 5 步同构骨架定稿 | 用户切大师 = 切方法论,UI 不变 |
| 2026-05-05 | 当前仅 M6 林奇展开,M7-M13 仅本表记录 | 用户明确"先按彼得林奇写,其它先记录" |
| 2026-05-05 | sidebar 改 4 折叠组导航 | 13 项 radio 不可一字排开 |
| 2026-05-05 | M3 七大师投票升级为 M13 独立 Tab | 集中管理,M3 只留链接 |
| 2026-05-05 | 通用基类延后到 M7 动手时再写 | 当前 M6 单独实现,M7 抽基类时回头复用 |

---

## 🔗 相关文件

- 已落地:[OPTIMIZATION_M6_彼得林奇分析法.md](OPTIMIZATION_M6_彼得林奇分析法.md)
- 大师 yaml:[.tools/rules/](.tools/rules/) · 8 套规则全就绪
- 模板对照:[02_companies/01_新华保险/05_投资决策/02_格雷厄姆投资法_新华保险五步分析.md](../../02_companies/01_新华保险/05_投资决策/02_格雷厄姆投资法_新华保险五步分析.md)
- 整体重设计:[REDESIGN_TODO.md](REDESIGN_TODO.md)
