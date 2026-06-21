"""Tab: 🤖 嵌入式 Claude Code 终端(ttyd iframe + 双向通道说明)。

由 .tools/dashboard/app.py 调用 render(),从 app 模块拿运行时变量
(selected / ttyd_status / ttyd_start_daemon / ttyd_stop / TTYD_LAUNCHER / ROOT / subprocess)。

M5 优化(2026-05-05):
- 启停 button 包 st.spinner,消除瞬时无反馈
- 状态条加 uptime + 端口监听检测(僵死检测)
- 🔄 重启 / 🩺 健康检查 / 📜 日志 三个新能力
- iframe 加载前先探端口,未监听显警告而非灰屏
- D7/D8/D9:依赖预检 panel + 端口冲突警告 + 状态条显示 claude binary 来源
- D5 (2026-05-05 第三轮):状态条改用 M1 温度计同款 4 列卡片(状态/PID/uptime/端口),
  视觉统一 + 信息密度大幅提升
"""
from __future__ import annotations

import socket
import time
from pathlib import Path

import streamlit as st


def _port_listening(port: int, timeout: float = 0.4) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def _fmt_uptime(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _pid_uptime(pid_file: Path) -> int:
    if not pid_file.exists():
        return 0
    return max(0, int(time.time() - pid_file.stat().st_mtime))


def _run_launcher(subprocess_mod, launcher: Path, root: Path, *args: str,
                  timeout: int = 10) -> tuple[int, str]:
    try:
        r = subprocess_mod.run(
            ["bash", str(launcher), *args],
            capture_output=True, text=True, timeout=timeout, cwd=root,
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return -1, str(e)


def _claude_source(path: str) -> str:
    """根据 claude binary 路径推断来源,告诉用户走的哪个登录态。"""
    if not path:
        return "未安装"
    if "/.vscode/extensions/anthropic.claude-code-" in path:
        return "VS Code 扩展自带 binary(与 Keychain 同步)"
    if "/homebrew/" in path or path.startswith("/usr/local/"):
        return "Homebrew · 注意 Keychain 凭据可能不兼容"
    return "系统 PATH"


def render(app_globals: dict) -> None:
    """app.py 在 dispatch 时把 globals() 传过来,把 selected / ttyd_* / 路径常量注入。"""
    g = globals()
    for _k, _v in app_globals.items():
        if _k != "__builtins__":
            g[_k] = _v

    st.subheader("🤖 嵌入式 Claude Code 终端")

    ttyd_port = st.session_state.get("ttyd_port_widget", 7681)
    running, pid = ttyd_status()  # type: ignore[name-defined]
    listening = _port_listening(ttyd_port) if running else False
    uptime = _fmt_uptime(_pid_uptime(TTYD_PID)) if running else "—"  # type: ignore[name-defined]

    # ─── D7/D9 依赖预检(每次 render 都跑,代价 ~30ms 两次 subprocess)─
    ttyd_code, ttyd_path = _run_launcher(subprocess, TTYD_LAUNCHER, ROOT, "--which-ttyd", timeout=3)  # type: ignore[name-defined]
    claude_code, claude_path = _run_launcher(subprocess, TTYD_LAUNCHER, ROOT, "--which-claude", timeout=3)  # type: ignore[name-defined]
    deps_ok = (ttyd_code == 0)

    if not deps_ok:
        st.error(
            "❌ **ttyd 未安装** — 终端无法启动。安装后刷新本页:\n\n"
            "```bash\n/opt/homebrew/bin/brew install ttyd\n```"
        )
    if claude_code != 0:
        st.warning(
            "⚠️ **claude CLI 未找到** — 启动后会降级到普通 shell(不会自动进 claude)。\n"
            "可装 VS Code Claude 扩展(`anthropic.claude-code`)或 `brew install claude`。"
        )

    # ─── 状态条:M1 温度计同款 4 列卡片(D5)─────────────────────
    try:
        from ui.thermometer import card_html as _card  # type: ignore
    except Exception:
        _card = None  # 降级见下方 fallback

    if running and listening:
        status_emoji, status_label, status_color = "🟢", "运行中", "#1b8a3a"
        status_hint = "LISTEN"
    elif running and not listening:
        status_emoji, status_label, status_color = "🟡", "僵死", "#f0ad4e"
        status_hint = "进程在·端口不通"
    elif not deps_ok:
        status_emoji, status_label, status_color = "⚪", "缺 ttyd", "#999"
        status_hint = "见上方安装提示"
    else:
        status_emoji, status_label, status_color = "🔴", "未启动", "#d9534f"
        status_hint = "点 ▶️ 启动"

    if _card is not None:
        cols = st.columns(4)
        with cols[0]:
            st.markdown(_card(
                label="ttyd 状态",
                value=f"{status_emoji} {status_label}",
                hint=status_hint,
                tooltip="🟢 运行中且端口监听 / 🟡 PID 在但端口不通(僵死) / 🔴 未启动 / ⚪ ttyd 未安装",
                value_color=status_color,
            ), unsafe_allow_html=True)
        with cols[1]:
            st.markdown(_card(
                label="PID",
                value=str(pid) if running else "—",
                hint=("运行中" if running else "无进程"),
                tooltip="ttyd daemon 进程号",
            ), unsafe_allow_html=True)
        with cols[2]:
            st.markdown(_card(
                label="Uptime",
                value=uptime,
                hint=("HH:MM:SS" if running else "未运行"),
                tooltip="基于 PID 文件 mtime 估算",
            ), unsafe_allow_html=True)
        with cols[3]:
            port_disp = f":{ttyd_port}"
            port_hint = "LISTEN" if listening else ("未监听" if running else "—")
            port_color = "#1b8a3a" if listening else ("#f0ad4e" if running else "#999")
            st.markdown(_card(
                label="端口",
                value=port_disp,
                hint=port_hint,
                tooltip=f"http://127.0.0.1:{ttyd_port}",
                value_color=port_color,
            ), unsafe_allow_html=True)
    else:
        # header_thermometer 不可用时降级到原 st.success/warning
        if running and listening:
            st.success(f"🟢 PID {pid} · uptime {uptime} · :{ttyd_port} LISTEN")
        elif running and not listening:
            st.warning(f"🟡 PID {pid} · :{ttyd_port} 未监听 — 进程可能僵死")
        else:
            st.warning("🔴 ttyd 未运行 · 点 ▶️ 启动 daemon")

    # D9: claude binary 来源(只在依赖齐时显示,避免和上面 warning 重复)
    if claude_code == 0:
        st.caption(f"📦 claude binary:`{claude_path}`  · {_claude_source(claude_path)}")

    # ─── 操作按钮 ─────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("▶️ 启动 daemon",
                     disabled=running or not deps_ok,
                     use_container_width=True, key="m5_start",
                     help=("ttyd 未装" if not deps_ok else None)):
            # D8: 启动前端口冲突预检
            port_code, port_msg = _run_launcher(
                subprocess, TTYD_LAUNCHER, ROOT, "--check-port", timeout=3,  # type: ignore[name-defined]
            )
            if port_code == 3:
                st.error(
                    f"❌ 端口 :{ttyd_port} 被别的进程占用 — `{port_msg}`\n\n"
                    f"换端口启动:`TTYD_PORT=7682 bash .tools/dashboard/launch_terminal.sh --daemon`,"
                    f"再把上方端口数字改成 7682。"
                )
            else:
                with st.spinner("启动 ttyd…"):
                    ok, out = ttyd_start_daemon()  # type: ignore[name-defined]
                (st.success if ok else st.error)(out or ("已启动" if ok else "启动失败"))
                st.rerun()
    with c2:
        if st.button("⏹ 停止", disabled=not running, use_container_width=True, key="m5_stop"):
            with st.spinner("停止 ttyd…"):
                ok, out = ttyd_stop()  # type: ignore[name-defined]
            (st.success if ok else st.error)(out or ("已停止" if ok else "停止失败"))
            st.rerun()
    with c3:
        if st.button("🔄 重启", use_container_width=True, key="m5_restart",
                     disabled=not deps_ok, help=("ttyd 未装" if not deps_ok else None)):
            with st.spinner("重启 ttyd…"):
                if running:
                    ttyd_stop()  # type: ignore[name-defined]
                    time.sleep(0.4)
                ok, out = ttyd_start_daemon()  # type: ignore[name-defined]
            (st.success if ok else st.error)(out or ("已重启" if ok else "重启失败"))
            st.rerun()
    with c4:
        if st.button("🩺 健康检查", use_container_width=True, key="m5_health"):
            code, out = _run_launcher(subprocess, TTYD_LAUNCHER, ROOT, "--health")  # type: ignore[name-defined]
            if code == 0:
                st.success(out)
            elif code == 2:
                st.warning(out)
            else:
                st.error(out)

    # ─── 端口 + iframe ────────────────────────────────────────────
    new_port = st.number_input(
        "ttyd 端口", min_value=1024, max_value=65535, value=ttyd_port, step=1,
        key="ttyd_port_widget",
        help="改端口需先 ⏹ 停止再 ▶️ 启动(并通过 TTYD_PORT 环境变量传入 launcher)",
    )
    ttyd_url = f"http://127.0.0.1:{new_port}"
    st.link_button("🔗 在新窗口打开", ttyd_url)

    if running and listening:
        st.components.v1.iframe(ttyd_url, height=560, scrolling=True)
    elif running and not listening:
        st.warning(
            f"⚠️ ttyd 进程在但 :{new_port} 未监听 — 可能端口被改过或进程僵死。\n"
            f"先点 🔄 重启,如仍失败查看下方日志。"
        )
    else:
        st.info("💡 点 ▶️ 启动 daemon 后 iframe 会自动加载")

    st.markdown("---")

    # ─── 日志(折叠)──────────────────────────────────────────────
    with st.expander("📜 ttyd 日志(最近 30 行)"):
        if st.button("🔄 刷新日志", key="m5_logs_refresh"):
            pass  # rerun 自动触发
        code, out = _run_launcher(subprocess, TTYD_LAUNCHER, ROOT, "--logs", "30")  # type: ignore[name-defined]
        if out:
            st.code(out, language="log")
        else:
            st.caption("(暂无日志)")

    # ─── 双向通道 ──────────────────────────────────────────────────
    with st.expander("🔁 双向通道协议"):
        st.markdown(
            f"- **Dashboard → Claude**:`.temp/current_context.md`(当前 → **{selected}**,"  # type: ignore[name-defined]
            f"Claude 启动自动加载)\n"
            f"- **Claude → Dashboard**:写入 `.temp/dashboard_inbox.md` → "
            f"Dashboard 侧栏「📨 Claude 来信」展示"
        )
        st.code(
            'echo "**茅台 PE 已到 5 年低位 10.7%**,可考虑分批建仓。" > .temp/dashboard_inbox.md',
            language="bash",
        )
