# M5 优化:🤖 Claude 终端 Tab + 浮窗

> **状态**:⚰️ 已下线 — 本模块 D1-D9 当年全部交付,但 v2.7 起 Claude 终端 Tab + 右下浮窗整体移除
> (ttyd 嵌入转方案 B「VS Code 旁挂」,功能等价;浮窗低频)。
> 当前导航无独立终端项,`tabs/claude.py` 仅留 ttyd 生命周期 helper 作历史残留。
> 本文档保留为已下线模块的设计/交付记录,不再维护。
>
> 优化窗口:2026-05-05 起
> 涉及文件(历史):`tabs/claude.py` · `floating_widget.py` · `launch_terminal.sh` · `app.py`(ttyd_* helper)

---

## 痛点回放

| #  | 痛点                           | 当前表现                                                | 用户感受                          |
| -- | ------------------------------ | ------------------------------------------------------- | --------------------------------- |
| P1 | 启停无反馈                     | 按 ▶️ 后 0.5s 内 `st.rerun()`,无加载动效               | 不知道是否真的在启动              |
| P2 | 状态浅                         | 只显示 PID,看不到运行了多久、占了多少端口、日志最后几行 | 出问题不知道去哪查                |
| P3 | 端口冲突无提示                 | ttyd 默认 7681,被占就静默失败                          | 启不起来要去看 ttyd.log 才知道    |
| P4 | 浮窗只能问 Claude,不能开终端  | 浮窗 3 按钮:💬 / 📝 / 📅                              | 想开终端还要切 Tab                |
| P5 | 健康检查缺失                   | PID 存在 ≠ ttyd 真在监听端口(进程僵死场景)            | "绿灯但打不开"的迷惑             |
| P6 | 日志查看要跳出 Streamlit       | 必须 `tail -f .temp/ttyd.log`                           | 没必要走出仪表板                  |
| P7 | iframe 加载失败无降级          | 端口空但 ttyd 没装 → iframe 灰屏                       | 不知道点哪修                      |

---

## 设计

### Tab 内布局(自上而下)

```
┌─ 🤖 嵌入式 Claude Code 终端 ──────────────────────────┐
│ [状态条]  🟢 PID 12345 · uptime 03:21 · :7681 LISTEN  │
│ [按钮区]  ▶️ 启动 daemon  ⏹ 停止  🔄 重启  🩺 健康检查  │
│ [端口]    端口 [7681] · 🔗 在新窗口打开                │
│ [iframe]  http://127.0.0.1:7681  height=560           │
│ ─────────────────────────────────────────────────     │
│ ▼ 📜 ttyd 日志(最近 30 行) [折叠]                     │
│ ▼ 🔁 双向通道协议 [折叠,沿用旧文案]                    │
└────────────────────────────────────────────────────────┘
```

### 浮窗(sidebar 末端)增加第 4 列

| col_a 💬 | col_b 📝 | col_c 📅 | **col_d 🤖** *(新)* |
|---|---|---|---|
| 问 Claude | 跳决策中心 | 看月报 | **一键启停 ttyd**(toggle) |

按 🤖:
- 当前未运行 → 调 `ttyd_start_daemon()`,toast「ttyd 已启动 · 切到 🤖 Tab 看终端」
- 当前运行中 → 调 `ttyd_stop()`,toast「ttyd 已停止」

(浮窗本身不嵌 iframe — sidebar 太窄,只做开关。看终端仍需切 Tab。)

### launcher 子命令补全

```bash
launch_terminal.sh --health   # curl 127.0.0.1:$PORT;返回 0=可达 / 2=进程在但端口不通 / 1=完全没起
launch_terminal.sh --logs     # 打印 .temp/ttyd.log 末尾 30 行(默认)
launch_terminal.sh --logs 100 # 自定义行数
```

### 端口冲突自动避让(可选, P3 减负)

启动前 `lsof -i :$PORT`,被占则:
- 默认仍报错并提示 `TTYD_PORT=7682 bash launch_terminal.sh --daemon`
- (不自动跳端口 — iframe URL 在 Streamlit 端是常量,跳了反而错位)

---

## 实施 checklist(零冲突项,本轮做)

- [x] **D1** 写本计划文档 → `OPTIMIZATION_M5_Claude终端.md`
- [x] **D2** `launch_terminal.sh` 加 `--health` `--logs [N]` 子命令
- [x] **D3** `tabs/claude.py` 增强:
  - 启停按 button 后用 `st.spinner` 包住 subprocess(消除瞬时无反馈)
  - 状态条显示 PID + uptime(基于 PID_FILE mtime)+ 端口监听检测
  - 健康检查按钮(🩺):调 `--health`,展示 stdout
  - 重启按钮(🔄):stop → start
  - 折叠面板"📜 ttyd 日志(最近 30 行)" 调 `--logs 30`
  - iframe 加载前先 `_port_listening()`,未监听则改显 `st.warning` + 教程
- [x] **D4** `floating_widget.py` 加 col_d 🤖 toggle(只影响 sidebar 第 4 列,M4 的 col_a/b/c 完全不动)

## 实施 checklist(第二轮 · 2026-05-05 后续,M0-M4 全交付后)

- [x] **D6** 浮窗 🤖 toggle 启动 ttyd 后写一条系统消息到 `dashboard_inbox.md`
  (`## [ts] 🟢 system · ttyd 已启动`,带当前 context 文件首行作为锚定)
- [x] **D7** 依赖预检面板:`launch_terminal.sh` 加 `--which-ttyd` / `--which-claude`,
  tab 顶部缺 ttyd 红色 error + 安装命令,缺 claude 黄色 warning + 降级说明;
  ttyd 缺时禁用 ▶️/🔄 按钮(避免静默失败)
- [x] **D8** 启动前端口冲突预检:`--check-port` 返回 0/2/3 三态;
  被别人占(3)直接 error + 提示 `TTYD_PORT=7682` 改端口;被自家 daemon 占(2)走原有 is_running 路径
- [x] **D9** 状态条 caption 显示 claude binary 路径 + 来源标签
  (VS Code 扩展 / Homebrew / 系统 PATH)— 让用户知道走的哪个登录态

## 实施 checklist(下一轮)

- [ ] **D5** ttyd 状态卡片接 dash-01 市场温度的视觉风格(等 M1 视觉风格定型后统一)

---

## 决策记录

| 日期 | 决策 | 原因 |
|---|---|---|
| 2026-05-05 | 不做端口自动跳 | iframe URL 在 Streamlit 是常量,跳了反而错位;改为报错 + 提示用户改 `TTYD_PORT` 环境变量 |
| 2026-05-05 | 浮窗只做开关不嵌 iframe | sidebar 宽度 ~250px,iframe 体验灾难;开关够用 |
| 2026-05-05 | 健康检查独立按钮而非自动轮询 | Streamlit rerun 频繁,自动轮询会卡 UI;手动按更可控 |

---

## 风险

| 风险 | 缓解 |
|---|---|
| `--health` 调 curl 在没装 curl 的机器报错 | 改用 python 内置 socket.connect 检测端口(零依赖) |
| `lsof` 在精简 Linux 缺失 | 仅 macOS 主用,降级到 `python -c "import socket;..."` |
| 浮窗 toggle 与 Tab 内按钮状态不同步 | 都读同一个 PID_FILE,Streamlit rerun 自动一致 |
