"""dash-04 横切组件 — 右下角浮窗。

固定在视口右下,4 选项:
  1️⃣ 问 Claude     — 在 .temp/dashboard_inbox.md 追加问题(由会话方读取)
  2️⃣ 补录决策     — 跳到决策中心 Tab(via session_state)
  3️⃣ 看月报       — 列出 .temp/monthly_review_*.md 最近 3 份
  4️⃣ ttyd 开关    — M5 新增:一键启停 ttyd daemon(看终端仍需切 🤖 Tab)

软依赖 dash-01:若全局 session_state["market_temperature"] 存在,显示市场温度

调用约定:在 app.py 的所有 tab 渲染完成后(脚本最末)调一次 render() 即可。
"""
from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
INBOX = ROOT / ".temp" / "dashboard_inbox.md"
REVIEW_DIR = ROOT / ".temp"
TTYD_PID = ROOT / ".temp" / "ttyd.pid"
TTYD_LAUNCHER = ROOT / ".tools" / "dashboard" / "launch_terminal.sh"


def _ttyd_running() -> bool:
    if not TTYD_PID.exists():
        return False
    try:
        import os
        os.kill(int(TTYD_PID.read_text().strip()), 0)
        return True
    except Exception:
        return False


def _ttyd_call(arg: str) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["bash", str(TTYD_LAUNCHER), arg],
            capture_output=True, text=True, timeout=10, cwd=ROOT,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


_FLOAT_CSS = """
<style>
.preson-fab {
    position: fixed;
    right: 24px;
    bottom: 24px;
    z-index: 9999;
    background: linear-gradient(135deg, #6366F1, #8B5CF6);
    border-radius: 14px;
    padding: 10px 14px;
    color: white;
    font-size: 13px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.18);
    display: flex; gap: 10px; align-items: center;
}
.preson-fab b { font-size: 14px; }
.preson-fab .preson-fab-pill {
    background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 8px;
}
</style>
"""


def _market_temp() -> str:
    """软依赖 dash-01:若 session_state 有 market_temperature 显示,否则降级。"""
    t = st.session_state.get("market_temperature")
    if t is None:
        return "🌡️ 温度计待启动"
    if isinstance(t, (int, float)):
        if t < 30:
            return f"🥶 市场冷 ({t:.0f})"
        if t > 70:
            return f"🥵 市场热 ({t:.0f})"
        return f"😐 市场中性 ({t:.0f})"
    return f"🌡️ {t}"


def render() -> None:
    """在所有 tab 之后调用一次。"""
    st.markdown(_FLOAT_CSS, unsafe_allow_html=True)

    # 顶部小贴纸(浮窗本体)— 视觉提示用户右下有快捷入口
    st.markdown(
        f'<div class="preson-fab">'
        f'  <b>🚀 quick</b>'
        f'  <span class="preson-fab-pill">{_market_temp()}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # 真正的交互入口放 sidebar 末尾(Streamlit 不支持真浮窗交互,只有视觉浮层)
    with st.sidebar:
        st.divider()
        st.markdown("#### 🚀 快捷入口")
        col_a, col_b, col_c, col_d = st.columns(4)

        with col_a:
            if st.button("💬", help="问 Claude(写入 dashboard_inbox)", key="fab_ask",
                         width="stretch"):
                st.session_state["fab_ask_open"] = not st.session_state.get("fab_ask_open", False)

        with col_b:
            if st.button("📝", help="跳转决策中心 Tab(请手动点顶部 Tab)", key="fab_decide",
                         width="stretch"):
                st.session_state["fab_decide_hint"] = True

        with col_c:
            if st.button("📅", help="最近 3 份月报", key="fab_report",
                         width="stretch"):
                st.session_state["fab_report_open"] = not st.session_state.get("fab_report_open", False)

        with col_d:
            ttyd_on = _ttyd_running()
            ttyd_label = "⏹" if ttyd_on else "🤖"
            ttyd_help = (
                "停止 ttyd daemon" if ttyd_on
                else "启动 ttyd daemon(切到 🤖 Tab 看终端)"
            )
            if st.button(ttyd_label, help=ttyd_help, key="fab_ttyd",
                         width="stretch"):
                with st.spinner("ttyd…"):
                    ok, out = _ttyd_call("--stop" if ttyd_on else "--daemon")
                if ok:
                    # D6: ttyd 启动后写一条系统消息到 inbox,告诉 Claude 端用户已就位
                    if not ttyd_on:
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                        ctx_hint = ""
                        ctx_file = ROOT / ".temp" / "current_context.md"
                        if ctx_file.exists():
                            try:
                                ctx_hint = f"(上下文 → `{ctx_file.read_text(encoding='utf-8').strip().splitlines()[0][:80]}`)"
                            except Exception:
                                pass
                        try:
                            INBOX.parent.mkdir(parents=True, exist_ok=True)
                            with INBOX.open("a", encoding="utf-8") as f:
                                f.write(
                                    f"\n## [{ts}] 🟢 system · ttyd 已启动\n\n"
                                    f"用户从 dashboard 浮窗启动了 Claude 终端,可在 🤖 Tab 看到。{ctx_hint}\n"
                                )
                        except Exception:
                            pass  # inbox 写失败不阻塞 UI
                    st.toast(("🛑 ttyd 已停止" if ttyd_on
                              else "🚀 ttyd 已启动 · 切到 🤖 Tab"))
                else:
                    st.toast(f"❌ {out[:60]}", icon="⚠️")
                st.rerun()

        # 子面板:问 Claude
        if st.session_state.get("fab_ask_open"):
            with st.container(border=True):
                msg = st.text_area("💬 写一条给 Claude 的问题",
                                   key="fab_ask_msg", height=80,
                                   placeholder="例:茅台现在贵不贵?要不要减仓?")
                if st.button("📤 发送", key="fab_ask_send", type="primary"):
                    if msg.strip():
                        INBOX.parent.mkdir(parents=True, exist_ok=True)
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
                        with INBOX.open("a", encoding="utf-8") as f:
                            f.write(f"\n## [{ts}] dashboard 浮窗问\n\n{msg.strip()}\n")
                        st.success(f"✅ 已写入 .temp/dashboard_inbox.md(Claude 会话端可读)")
                        st.session_state["fab_ask_msg"] = ""

        # 子面板:跳决策中心提示
        if st.session_state.get("fab_decide_hint"):
            st.info("👉 请点顶部 **💼 决策中心** Tab 进入完整录入区")
            st.session_state["fab_decide_hint"] = False  # 一次性

        # 子面板:近月报
        if st.session_state.get("fab_report_open"):
            files = sorted(REVIEW_DIR.glob("monthly_review_*.md"), reverse=True)[:3]
            if not files:
                st.caption("(暂无月报 — 跑 monthly_review.py 生成)")
            else:
                for p in files:
                    st.caption(f"📄 [{p.name}](file://{p.resolve()})")
