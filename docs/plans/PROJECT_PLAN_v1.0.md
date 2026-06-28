---
版本: 1.0
状态: 立项
创建: 2026-06-28
作者: renmingyang@proton.me
---

# preson 1.0 立项：系统版本统一 + 资料整理

> 把整个 preson 系统正式宣布为统一的 **1.0 基线版本**，作为后续开发的干净起点。
> Dashboard v2.x 内部计数到此归零，折叠为「1.0 之前的开发迭代史」。

---

## 1. Context（为什么做）

当前「版本」在系统里是**分裂**的：

- 代码与文档自称 **Dashboard v2.9**（42 处 `.py` / `.md` 引用），这是从 v2.1 一路累加的「Dashboard 内部迭代计数器」。
- 但 git 已有 **`v1.0` tag**，`.config/portfolio.yaml` 里也写 `version: 1.0`。
- `docs/plans/` 还堆着 v2.3~v2.7 共 11 份历史计划、`docs/tasks/` 堆着 v2.4 / v2.5 已交付任务包 —— 读者无法一眼判断「系统现在到底是什么版本、什么状态」。

**预期结果**：仓库里任何人（含 AI 会话）打开都能立刻看到「preson v1.0」这一个权威版本号；历史 v2.x 迭代收编进 `CHANGELOG.md` 与归档目录；活跃文档区只剩当前该看的东西。

---

## 2. 范围边界

| | 内容 |
|---|---|
| ✅ 做 | 版本号统一 + 资料整理（归档历史文档、校准当前版本锚点、建立单一版本真源） |
| ✅ 新增 | 1.0 开发验证脚手架 L1+L2（热重载 + 子单元隔离台 + 子单元 manifest），见 §4.F |
| ❌ 不做 | 功能债：不重建 `peers.duckdb`、不删 legacy 代码、不标准化 `02_companies/` 目录 |
| ❌ 不做 | 本地包袱：`.backup/`(1.3G)、`.vscode/01_knowledge/`(440M)、`.temp/` 均已 gitignore，保留不动 |
| ⏳ 延后 | 验证脚手架 L3（截图快照对比 / 单元断言基线） |

---

## 3. 核心理念

把散落的版本表述分两类，分别处理：

| 类别 | 含义 | 处理方式 |
|------|------|----------|
| **「当前版本」锚点**（live） | 声明系统现在是什么版本 | 改为 **preson v1.0**，并指向单一真源 |
| **历史版本提及**（history） | 记录某次迭代的设计/计划/commit | **保留不改**，作为通往 1.0 的开发史 |

> 关键动作 = 建立**一个**版本真源 + 把所有 live 锚点指向它 + 历史 v2.x 折叠归档。

---

## 4. 工作项

### A. 建立单一版本真源

1. 新建根目录 `VERSION`，内容一行 `1.0` —— 全系统唯一权威版本号。
2. 新建根目录 `CHANGELOG.md`：
   - 头条 `## [1.0] - 2026-06-28`，列当前已交付能力（数据层 7 库 + 100 家 / 五导航 Dashboard / 5 套大师评分 / 行业分析 / 同行对标 / MCP 工具）。
   - `## Pre-1.0 开发迭代史`：把 Dashboard v2.1→v2.9 浓缩成时间线（一句话/版本），不逐条搬运。
3. 新建本文件 `docs/plans/PROJECT_PLAN_v1.0.md`（即本立项文档），并在 `docs/plans/README.md` 活跃区索引。
4. （可选）Dashboard sidebar 底部读取 `VERSION` 显示 `preson v1.0`。

### B. 校准 live 版本锚点 → 1.0

把以下「声明当前版本」处从 `Dashboard v2.9` 改为 `preson v1.0`（合适处加「详见 CHANGELOG.md」）：

- `README.md`：抬头「当前版本」、「已完成」表中 v2.9 行。
- `CLAUDE.md`：抬头、演进说明段。
- `docs/architecture/README.md` 与 `00-overview.md`：若有「当前版本 v2.9」表述改为 1.0。

**不改**：`12-dashboard-v2.9-design-scheme.md` 文件名与正文、代码内 `migrate_v29_schema.py` / `tests/screener_v29/` 等 v29 命名（属历史 artifact，重命名牵动 import）。仅在设计文档顶部加一行「此设计即 1.0 当前形态」。

### C. 归档历史 plans / tasks（移动不删除）

1. 新建 `docs/plans/_archive/`，移入：`PROJECT_PLAN.md`、`PROJECT_PLAN_v2.md`、`PROJECT_PLAN_v2.3.md`、`PROJECT_PLAN_v2.4_候选.md`、`PROJECT_PLAN_v2.5_TODO.md`、`PROJECT_PLAN_v2.6.md`、`PROJECT_PLAN_v2.7_持仓档案.md`、`PROJECT_PLAN_peer.md`、`PROGRESS_v2.md`、`PROJECT_OVERVIEW.md`。
   - 活跃区保留：`PROGRESS.md`、`README.md`、`共享计划.md`、`PROJECT_PLAN_v1.0.md`。
2. 新建 `docs/tasks/_archive/`，移入 `v2.4_p0/`、`v2.5_industry/`。
   - 活跃区保留：`v2.6_kondratieff/`、`data_audit_2026-05-14/`、`docs/tools/`。
3. （可选）`docs/dashboard/_archive/` 移入 `OPTIMIZATION_M0~M5` + `REDESIGN_TODO`，顶层留 README + M6。

### D. 更新索引与指引

- `docs/plans/README.md`：活跃区只列 PROGRESS.md / 共享计划.md / PROJECT_PLAN_v1.0.md；其余见 `_archive/`。
- `docs/README.md`：plans/tasks 行补「历史版本已归入各自 `_archive/`」。
- `README.md` 与 `CLAUDE.md` 更新记录区：各加一条 `2026-06-28：系统版本统一为 1.0，历史迭代见 CHANGELOG.md`。
- `README.md` 文档索引表加一行指向 `CHANGELOG.md`。

### E. git tag 对齐（需授权执行）

`v1.0` tag 已存在但可能指向旧 commit。资料整理提交后重新打 tag：

```bash
git add -A && git commit -m "chore: 系统版本统一为 1.0 + 历史文档归档"
git tag -f v1.0   # 或 git tag v1.0.0
```

### F. 1.0 开发验证脚手架（L1+L2，新增交付）

为「后续一个子单元一个子单元地改」配套快速回路。三个卡点：①没开热重载（全杀全启 15–30s）；②无法只渲染一个子单元；③「修改单元」没有稳定把手、无可对比基线。全部为**新增文件**，不改现有渲染逻辑。

**L1 — 热重载（~5 分钟）**

新建 `.streamlit/config.toml`：

```toml
[server]
runOnSave = true
headless = true
port = 8501
```

存盘即自动 rerun，循环从 ~20s 降到 ~5s。`README.md` / `.tools/dashboard/README.md` 补一句说明。

**L2 — 子单元隔离台 + manifest**（复用现有纯渲染函数与离线测试）

1. 新建 `.tools/dashboard/dev/units.py`（manifest）：每个子单元登记 `{key, label, render, sample_inputs, test_path}`。首批 6–8 个易隔离单元：
   - `peg_curve` → `lynch_analysis/step4_peg.py::render_peg_step`，样本 `000333`
   - `industry_percentile` → `tabs/industry/preselect.py::render_percentile_card`，样本 `白酒`
   - `munger_card`、graham/lynch/buffett 评分卡、黄金子模块之一
   - 强耦合整 tab（`graham_analysis` / `decision_center`）登记但标 `full_app_only=True`。
2. 新建 `.tools/dashboard/dev_harness.py`（独立 Streamlit，端口 8502）：sidebar selectbox 选 key，主区只渲染选中单元，顶部显示 key 与 test_path。
3. 新建 `.tools/dashboard/dev_harness.sh`：`streamlit run dev_harness.py --server.port 8502`。

> manifest 是三件套底座：「我在改 `peg_curve`」→ 隔离台看（配 L1 秒级）→ `pytest <test_path>` 验回归。

---

## 5. 明确不做（防范围蔓延）

- 不重建 `peers.duckdb`、不修任何功能债。
- 不删 legacy 代码、不重命名代码内 v29、不改缓存常量 `_VOTE_CACHE_VERSION`。
- 不删/不移 `.backup/`、`.vscode/01_knowledge/`、`.temp/`。
- 不标准化 `02_companies/` 目录深度。
- 不改 `docs/` 下文档的设计/决策正文，只改「当前版本」声明 + 物理归档移动。

---

## 6. 验证

1. **版本真源唯一性**：`cat VERSION` 得 `1.0`；`grep -rn "当前版本\|Dashboard v2.9" README.md CLAUDE.md docs/architecture/*.md` 只剩历史设计文档链接/标题。
2. **断链检查**：归档后 `docs/*.md` / `docs/plans/README.md` 里指向的路径均存在。
3. **CHANGELOG 可读性**：头条 1.0，pre-1.0 时间线覆盖 v2.x。
4. **活跃区清爽**：`docs/plans/` 仅剩 PROGRESS / README / 共享计划 / PROJECT_PLAN_v1.0 / `_archive/`；`docs/tasks/` 仅剩 v2.6_kondratieff / data_audit / `_archive/`。
5. **热重载（L1）**：编辑渲染文件存盘，浏览器自动 rerun。
6. **隔离台（L2）**：`bash dev_harness.sh` 起在 8502，能逐个渲染 manifest 单元无异常。

---

## 7. 附录：1.0 之后的迭代建议

本次三个系统性问题——**版本曾失控**、**文档曾漂移**、**债务静默累积**——共同根因是「缺触发器」。后续护栏本质就是给每类东西配一个触发器。

### 近期：建议设「1.1 健康度」里程碑，收掉本次推迟的功能债

1. 🔴 **重建 `peers.duckdb`**：跑 `.tools/db/fetch_peers.py`（9 处引用却文件缺失，功能降级/报错）。
2. **删 legacy 代码**：`tabs/screener_legacy.py`、`score/piotroski_v0.py`。
3. **`02_companies/` 目录标准化**：100 家深度不一，统一模板或补占位。

### 贯穿性纪律

1. **解耦债务边改边还**：每动一个强耦合 tab，顺手把一个 sub-step 抽成纯渲染函数并登记 manifest —— 对「迭代变快」复利最高。
2. **单一活文档**：1.0 后只认 `CHANGELOG.md` + `PROGRESS.md`，其余带日期冻结；改导航/版本/库结构就更新这一个。
3. **每个子单元都有测试**：manifest 同时是覆盖清单，补齐 `test_path` 为空的单元。
4. **质量门自动化**：`verify_refactor.py` 挂成 pre-push hook 或 `make verify`。
5. **数据层开机自检**：启动时断言 8 库齐全 + 行数合理，异常 sidebar 亮红（覆盖「clone 后忘还原 blob」坑）。

### 单次迭代仪式

> manifest 选单元 → 隔离台(8502)+热重载边改边看 → 跑该单元离线测试 → `verify_refactor.py` 确认没碰坏别页 → CHANGELOG.md 记一行。

大功能才走 plan/spec 流程；单子单元改动用上面这套轻仪式，几分钟一轮。
