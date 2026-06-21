# 关键约定

后续修改应遵守以下约定，避免破坏跨模块契约。

## 读写分离

| 组件 | DuckDB | YAML/MD |
|------|--------|---------|
| Dashboard 查询 | read-only | 持仓/观察池可写 |
| MCP Server | read-only | — |
| db/ingest | 独占写 preson | — |
| decisions/db | 读写 decisions | — |
| 抓数脚本 | 独占写各库 | 写 02_companies 原始目录 |

## Ticker 规范化

- 单一可信源：`tickers.normalize_ticker`（或项目内等价函数）
- A 股 6 位、港股 5 位
- ingest / MCP / portfolio 均使用规范化后的 ticker

## 缓存策略

```python
@st.cache_data(ttl=60~900)
def fn(db_mtime: float, ...):
    ...
```

- cache key 必须含 `_db_mtime()` 或文件 mtime
- 用户点「刷新数据」→ `st.cache_data.clear()`
- YAML 配置变更依赖文件 mtime 或手动 rerun

## 港股处理

估值 / 技术 / 两融模块对港股统一：
- 返回空数据或显示「未接入」caption
- **不抛异常**，不阻断页面渲染

## 路径常量

各模块通过 `ROOT = Path(__file__).resolve().parents[N]` 定位项目根。  
`N` 取决于文件深度，**不要硬编码绝对路径**。

## 模块导入

Dashboard 启动时把以下目录加入 `sys.path`：
- `.tools/dashboard/`
- `.tools/mcp/`
- `.tools/score/`
- `.tools/`（portfolio、decisions 等）

新模块应遵循相同模式，避免循环导入。

## 配置迁移模式

参考 v2.8 portfolio 迁移：
1. 新路径 `.config/portfolio.yaml` 为唯一源
2. 提供 `migrate_to_config.py` 一次性迁移
3. 旧文件 rename 为 `.deprecated`，保留 `.bak` 时间戳备份
4. loader 内注释标明版本断点

## 跨 Tab 跳转

- 禁止直接改 `st.session_state["nav"]` 后期待生效（radio 已渲染）
- 统一用 `navigation.goto()` + rerun
- 新增页面时同步更新 `navigation.py` 与 `app.py` 的 `PAGE_*`

## 测试要求

- 引擎逻辑：纯函数单测，不依赖 Streamlit
- 导航：`test_navigation.py` 覆盖 goto/consume
- App 冒烟：`test_app.py` AppTest headless

## 敏感信息

- `.config/credentials.md` 不入 git、不在日志/错误栈展示
- Token 通过 `lixinger_resolve_token.py` 解析

## 文档同步

以下变更必须更新 `docs/architecture/` 对应文档：

| 变更类型 | 更新文档 |
|----------|----------|
| 新 DuckDB / 新表 | `02-data-layer.md` |
| 新抓数脚本 | `03-fetch-layer.md` |
| 新 Tab / 路由变更 | `05-dashboard.md` |
| 新配置 YAML | `06-config-and-state.md` |
| 新引擎子包 | `07-engines-reference.md` |
| 架构级决策 | `adr/NNNN-*.md` |
