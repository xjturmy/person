# 投资智能体(Dashboard)

> 维度 3 交互层产物。Streamlit 4-tab 看图 + 嵌入式 Claude 终端,数据源 DuckDB(CSV 兜底)。

## 🚀 一行启动

```bash
cd /Users/gongyong/Desktop/Keyi/preson
.venv/bin/streamlit run .tools/dashboard/app.py
```

浏览器自动打开 `http://localhost:8501`。

> ⚡ **热重载已开**（`.streamlit/config.toml` 的 `runOnSave=true`）：改完渲染文件存盘，浏览器自动 rerun，无需重启。仅改 import / 全局缓存 / 顶层常量时才需 `./restart_dashboard.sh`。

## 🧪 子单元隔离台（开发用）

只渲染**一个**子单元，配热重载秒级看效果，跑在 8502、与主 app 并存：

```bash
bash .tools/dashboard/dev_harness.sh        # → http://localhost:8502
```

子单元清单见 [dev/units.py](dev/units.py)。开发回路：说「我在改 `peg_curve`」→ 隔离台选它看效果 → `pytest <test_path>` 验回归 → `verify_refactor.py` 确认没碰坏别页 → CHANGELOG 记一行。强耦合整 tab（芒格/格雷厄姆/决策中心）标 ⛔，走主 app + `verify_refactor.py`。

## 🤖 嵌入 Claude 终端

```bash
# 默认进 claude 会话
bash .tools/dashboard/launch_terminal.sh

# 后台 daemon 模式(关 Streamlit 不杀终端)
bash .tools/dashboard/launch_terminal.sh --daemon

# 普通 shell(不起 claude)
AUTO_CLAUDE=0 bash .tools/dashboard/launch_terminal.sh

# 停止后台 ttyd
bash .tools/dashboard/launch_terminal.sh --stop
```

启动后浏览器内 Tab 4「🤖 Claude 终端」直接显示。

## 🧱 架构

```
浏览器
  ├─ Streamlit (8501) ── 直连 DuckDB ── data/preson.duckdb
  │     └─ Tab 4 iframe ──┐
  └─                       └── ttyd (7681) ── claude
                                                ├── MCP: preson-research
                                                └── CLAUDE.md hook 加载 .temp/current_context.md
```

## 📁 文件清单

| 文件 | 作用 |
|---|---|
| [app.py](app.py) | Streamlit 主程序(4 tab) |
| [launch_terminal.sh](launch_terminal.sh) | ttyd 启动 + daemon 管理 |
| [requirements.txt](requirements.txt) | 锁定依赖版本 |

## 🔁 双向通道

| 方向 | 文件 | 触发 |
|---|---|---|
| Dashboard → Claude | `.temp/current_context.md` | 切换公司/模块/指标 自动写 |
| Claude → Dashboard | `.temp/dashboard_inbox.md` | Claude 端 `echo "..." > $f`,sidebar 自动展示 |

## 🧪 数据源回退

`load_metric()` 优先走 DuckDB(`data/preson.duckdb`),失败时回退 `02_companies/{N}/01_基本面数据/历史数据/*.csv`。

## ⚙️ 缓存策略

- DuckDB 连接:`@st.cache_resource`,文件 mtime 变更自动重连
- `load_metric` / `mcp_status` / `read_inbox`:`@st.cache_data(ttl=*)` + DuckDB mtime 作为入参,周末 cron 增量后无需手动重启

## 🩺 故障排查

| 现象 | 处理 |
|---|---|
| 侧栏显示「📁 CSV 兜底模式」 | 跑 `python3 .tools/db/ingest.py` 重建 DuckDB |
| Tab 4 终端空白 | 另开 shell 跑 `bash .tools/dashboard/launch_terminal.sh`;首次需 `brew install ttyd` |
| MCP 工具显 ⚠️ 脚本缺失 | 检查 `.tools/mcp/server.py` 是否还在 |
| 数据「过时」徽章长亮 | `python3 .tools/db/update.py` 跑增量,或装周日 cron `bash .tools/db/install_cron.sh` |
| streamlit + pyxtermjs 冲突 | 已避免 — 仅装 `requirements.txt` 即可 |

## 🔌 端口约定

| 服务 | 端口 | 备注 |
|---|---|---|
| Streamlit | 8501 | `--server.port` 可改 |
| ttyd | 7681 | `TTYD_PORT` 环境变量可改 |

## 📅 维护节奏

- **每周日 21:00**:`com.preson.update.weekly.plist` 自动跑 `update.py` → fetch → ingest → validate
- **手动**:`bash .tools/db/install_cron.sh` 安装 LaunchAgent

## 📖 优化文档

Dashboard UI/UX 优化方案已迁至 [docs/dashboard/](../../docs/dashboard/README.md)（M0–M6）。
