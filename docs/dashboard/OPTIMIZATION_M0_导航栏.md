# 模块 0 优化记录:🧭 左侧导航栏 + Sidebar

> 文件:[app.py:168-233](app.py#L168) — sidebar 块
>
> **创建**:2026-05-05
> **状态**:📋 待开工
> **预计工作量**:1.5-2 小时(纯 UI 调整)

---

## 🎯 优化目标

把当前"导航 / 选股 / 设置"3 段分离的 sidebar,合并为**导航 + 选股&设置**两段紧凑布局,字体可读性更好,层级更清。

---

## 🩺 当前痛点

| 现状 | 行号 | 问题 |
|---|---|---|
| 5 个页面 radio 字体偏小 | [app.py:178](app.py#L178) | 主导航看不清,且默认行高紧凑 |
| 5 个页面 radio 行间距过紧 | 同上 | "市场周期/公司筛选" 紧贴在一起,视觉一片 |
| `### 🧭 导航` 与 `### 🎯 选股` 之间用 `st.divider()` 分隔 | [app.py:179-181](app.py#L179) | 两段距离太大,sidebar 显得空荡 |
| `st.caption("上下文 → .temp/current_context.md")` 紧跟选股 selectbox | [app.py:187](app.py#L187) | 用户根本不关心这是写到哪个文件,纯噪音 |
| `### 🎯 选股` 与 `⚙️ 设置 expander` 又被 divider 分开 | [app.py:188](app.py#L188) | 两个紧密相关的功能被强行拆成两段 |
| ⚙️ 设置 expander 塞 4 类内容(数据源 / MCP / 缺口 / 收件箱兜底) | [app.py:201-233](app.py#L201) | 信息密度过高,展开后一堆段落,没有"快速看一眼"的入口 |
| 收件箱在 sidebar 顶上独立段落 | [app.py:191-199](app.py#L191) | 占太多视觉空间,实际多数时候是空 |

---

## 🆕 新版面设计(2 段紧凑布局)

```
╔══════════════════════════════╗
║  🧭 导航                       ║   ← 标题加大加粗
║                                ║
║  📊 市场周期                  ║   ← 字体 16px,行距 ↑
║                                ║
║  🔍 公司筛选                  ║
║                                ║
║  🏢 单公司详情                ║
║                                ║
║  💼 决策中心                  ║
║                                ║
║  🤖 Claude 终端               ║
║                                ║
║  ─────────────                ║   ← 细分割线(非 divider)
║                                ║
║  🎯 当前公司                  ║   ← 选股 + 设置 合并段
║  [贵州茅台 ▼]                 ║
║                                ║
║  ⚙️ 设置(精简版)              ║   ← expander 默认收起
║   ✅ DuckDB · 543k 行 · 今天   ║   ← 仅 1 行状态(数据源)
║   📨 收件箱(N) ▶              ║   ← 折叠子项
║   🔌 MCP / 🩺 缺口  ▶          ║   ← 折叠子项
╚══════════════════════════════╝
```

---

## ✅ 实施 Checklist

### 优化项 #1 — 字体放大 + 行间距加大(20min)

- [ ] 在 sidebar 顶部注入 CSS:

```python
st.sidebar.markdown("""
<style>
  /* 导航 radio 字号 + 行距 */
  section[data-testid="stSidebar"] [data-testid="stRadio"] label p {
    font-size: 16px !important;
    line-height: 2.2 !important;     /* 行间距加大 */
    font-weight: 500;
  }
  /* sidebar 标题 */
  section[data-testid="stSidebar"] h3 {
    font-size: 18px !important;
    margin-top: 8px !important;
    margin-bottom: 8px !important;
  }
  /* selectbox 字号 */
  section[data-testid="stSidebar"] [data-baseweb="select"] {
    font-size: 15px !important;
  }
</style>
""", unsafe_allow_html=True)
```

### 优化项 #2 — 删除"导航"与"选股"之间多余 divider(5min)

- [ ] [app.py:179](app.py#L179) 的 `st.divider()` 改 `st.markdown("---")`(更细)或直接删除,改成 12-16px margin
- [ ] 5 个页面 radio 选项保留,但 `st.markdown("### 🧭 导航")` 标题可保留(用户希望加大)

### 优化项 #3 — 隐藏"上下文"提示(1min)

- [ ] 删除 [app.py:187](app.py#L187):`st.caption("上下文 → .temp/current_context.md")`
- [ ] 上下文写入逻辑保留(后台默默写),用户不需要知道

### 优化项 #4 — 选股 + 设置合并为一段(15min)

- [ ] 删除 [app.py:188](app.py#L188) 的 `st.divider()`
- [ ] `### 🎯 选股` 改为 `### 🎯 当前公司`(更准确)
- [ ] selectbox 紧跟其后,然后立即 `with st.expander("⚙️ 设置", expanded=False):` 收起
- [ ] 整体合成一个视觉块,无 divider

### 优化项 #5 — ⚙️ 设置内容精简(30min)

**保留(浓缩成 1-3 行)**:
- ✅ 数据源状态:`💾 DuckDB · 543k 行 · 今天 09:30 更新` 一行(原 4 行精简)
- 📨 收件箱:有信时显示徽章数 `📨 收件箱 (1)`,点击展开;空时不显示

**折叠到二级 expander**(默认收起):
- 🔌 MCP 工具列表(用户日常不看)
- 🩺 数据缺口(已并入持仓总览的 audit_alerts,sidebar 只保留计数)

**新增"快捷入口"挪入设置**:
- 「🔄 刷新数据」按钮 — 触发 `st.cache_data.clear()` + rerun
- 「📂 打开项目目录」按钮 — `subprocess.run(["open", ROOT])`(macOS)

```python
with st.expander("⚙️ 设置", expanded=False):
    # 1. 数据源状态(1 行)
    ds = datasource_status(DB_MTIME)
    if ds["source"] == "duckdb":
        st.caption(f"💾 DuckDB · {ds['rows']:,} 行 · {ds['updated']}")
    else:
        st.caption(f"📁 CSV 兜底 — {ds.get('reason', '')}")

    # 2. 收件箱(有信才显示)
    inbox = read_inbox()
    if inbox:
        with st.expander(f"📨 收件箱 (1)", expanded=True):
            st.markdown(inbox)
            if st.button("✅ 已读", key="clear_inbox", use_container_width=True):
                clear_inbox()
                read_inbox.clear()
                st.rerun()

    # 3. MCP / 缺口 折叠
    with st.expander("🔌 MCP / 🩺 缺口", expanded=False):
        # MCP servers
        ...
        # validate 缺口
        ...

    # 4. 快捷入口
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔄 刷新数据", use_container_width=True, key="refresh_cache"):
            st.cache_data.clear()
            st.rerun()
    with col_b:
        if st.button("📂 打开目录", use_container_width=True, key="open_root"):
            import subprocess
            subprocess.run(["open", str(ROOT)])
```

### 优化项 #6 — 收件箱从顶部移除(5min)

- [ ] 删除 [app.py:191-199](app.py#L191) sidebar 顶部的独立收件箱段落
- [ ] 已合并到 #5 的 ⚙️ 设置 内,有信才显示徽章

### 优化项 #7 — 顶部主标题精简(5min)

- [ ] 当前 [app.py:152-154](app.py#L152) 主区有 `st.title("📊 投资智能体") + st.caption("MVP · ...")`,占 2 行
- [ ] caption 信息("DuckDB 直连(mtime 缓存)+ MCP 状态 + 双向通道")属技术细节 → 删掉
- [ ] 标题保留即可

---

## 📋 改动清单

仅改 [app.py](app.py),不动其他文件:

```diff
@@ st.title 之后 @@
- st.caption("MVP · DuckDB 直连(mtime 缓存)+ MCP 状态 + 双向通道")

@@ sidebar @@
+ # 字体 + 行距 CSS(优化项 #1)
+ st.sidebar.markdown("""<style>...</style>""", unsafe_allow_html=True)

  st.markdown("### 🧭 导航")
  page = st.radio(...)
- st.divider()                          # 优化项 #2:删

  st.markdown("### 🎯 当前公司")        # 优化项 #4:改名
  selected = st.selectbox(...)
- st.caption("上下文 → ...")            # 优化项 #3:删
- st.divider()                          # 优化项 #4:删

- # 优化项 #6:删独立收件箱段(已并入设置)
- inbox = read_inbox()
- if inbox: ...

  with st.expander("⚙️ 设置", expanded=False):
+     # 1. 数据源 1 行 (优化项 #5)
+     # 2. 收件箱(有信才显示)
+     # 3. MCP / 缺口 二级 expander
+     # 4. 快捷入口:🔄 刷新 / 📂 打开目录
```

---

## 🚀 推荐执行顺序

按列出顺序 1→7 即可,纯改 app.py 单个文件,无回归风险。**可一次性 30 分钟做完 + headless 验证**。

---

## ⚠️ 风险与注意

| 风险 | 处理 |
|---|---|
| Streamlit 升级后 `data-testid` 选择器变化导致 CSS 失效 | CSS 加 `!important` 兜底 + 注释标记 streamlit 版本 |
| `st.cache_data.clear()` 会清空所有 cache,不只是当前页 | 用户预期就是"全刷新",不是缺陷 |
| `subprocess.run(["open", ...])` 仅 macOS 支持 | 当前用户是 macOS,不需跨平台 |
| 收件箱"有信才显示"逻辑改后,Claude 推送测试需重跑 | 改完后用 `echo > .temp/dashboard_inbox.md` 测试 |

---

## 📝 决策记录

| 日期 | 决策 | 备注 |
|------|------|------|
| 2026-05-05 | 选股 + 设置合并一段,无 divider | 用户反馈"分得太开" |
| 2026-05-05 | 上下文文件路径 caption 删除 | 用户不需要知道写到哪 |
| 2026-05-05 | 收件箱并入设置,有信才显示 | sidebar 视觉减负 |
| 2026-05-05 | "导航"标题保留 + 字体加大 | 用户明确希望"字体大一点" |
| 2026-05-05 | "刷新数据 / 打开目录"作为快捷入口放进设置 | 不另起一段 |

---

## 🔗 相关文件

- 当前实现:[app.py:168-233](app.py#L168) sidebar 块 + [app.py:152-154](app.py#L152) title 块
- 同系列:[OPTIMIZATION_M1_市场周期.md](OPTIMIZATION_M1_市场周期.md) · [OPTIMIZATION_M2_公司筛选.md](OPTIMIZATION_M2_公司筛选.md) · [OPTIMIZATION_M3_单公司详情.md](OPTIMIZATION_M3_单公司详情.md) · [OPTIMIZATION_M4_决策中心.md](OPTIMIZATION_M4_决策中心.md)
- 整体重设计:[REDESIGN_TODO.md](REDESIGN_TODO.md)
