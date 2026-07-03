"""dash-04 L0 决策中心 — 4 个子 Tab。

子 Tab 1:持仓总览 — 待办收件箱 + 持仓表 + 动作面板 + 分布/再平衡
子 Tab 2:持仓跟踪 — 单股决策卡片视图(holding_tracker)
子 Tab 3:决策日志 — 快速录入 + 历史列表
子 Tab 4:月报历史 — .temp 快照 + 知识库复盘

入口:render(companies, selected, db_mtime, decisions_db, decisions_snapshot, _folder_to_ticker)
"""
from __future__ import annotations

import sys
from datetime import date as _date_cls
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".tools" / "portfolio"))

from holdings_view import HoldingsSnapshot, build_snapshot  # noqa: E402
from loader import load_yaml_dict, upsert_holdings  # noqa: E402
from parse_holdings import build_candidates, parse_text  # noqa: E402
from rebalance_planner import RebalanceProposal, apply_proposals, plan as plan_rebalance  # noqa: E402
from parse_screenshot import parse_image  # noqa: E402

# v2.8+ 持仓全景重构:新增 3 个独立模块
sys.path.insert(0, str(ROOT / ".tools" / "dashboard" / "tabs"))
from decision import action_inbox as _inbox  # noqa: E402
from decision import holdings_table as _table  # noqa: E402
from decision import holding_actions as _actions  # noqa: E402

COMPANIES_CSV = ROOT / ".config" / "companies.csv"
PRESON_DB = ROOT / "data" / "preson.duckdb"
DECISIONS_DB = ROOT / "data" / "decisions.duckdb"
PORTFOLIO_YAML = ROOT / ".tools" / "portfolio" / "portfolio.yaml"


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


@st.cache_data(ttl=300, show_spinner=False)
def _cached_snapshot(preson_mtime: float, decisions_mtime: float,
                     portfolio_mtime: float) -> HoldingsSnapshot:
    """决策中心持仓快照,按 (preson/decisions.duckdb + portfolio.yaml) mtime 失效。

    build_snapshot 无内建缓存,实测每次进决策中心固定 ~630ms。
    """
    return build_snapshot()


def cached_snapshot() -> HoldingsSnapshot:
    return _cached_snapshot(_mtime(PRESON_DB), _mtime(DECISIONS_DB), _mtime(PORTFOLIO_YAML))


REVIEW_DIR_TEMP = ROOT / ".temp"
REVIEW_DIR_KNOWLEDGE = ROOT / "01_knowledge" / "05_实战案例与持仓" / "持仓统计与复盘"


# ─── 智能录入辅助 ─────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def _load_universe() -> tuple[set[str], dict[str, str]]:
    """读 companies.csv → (15 家 ticker 集合, ticker→公司名 map)。"""
    if not COMPANIES_CSV.exists():
        return set(), {}
    df = pd.read_csv(COMPANIES_CSV, dtype={"stock": str})
    tickers = {str(t).strip() for t in df["stock"] if pd.notna(t)}
    name_map = {str(r["stock"]).strip(): str(r["name"]) for _, r in df.iterrows()
                if pd.notna(r.get("stock"))}
    return tickers, name_map


def _held_tickers() -> set[str]:
    """读 portfolio.yaml,返回已 holdings 的 ticker 集合。"""
    doc = load_yaml_dict()
    return {str(h.get("ticker", "")).strip() for h in (doc.get("holdings") or []) if h.get("ticker")}


def _render_smart_intake() -> None:
    """📥 智能录入 expander — 三选项:截图 / 文本 / 手动。

    截图 (#3) 暂占位,核心做文本路径(#1+#2+#4)。
    """
    with st.expander("📥 智能录入持仓(粘贴券商导出文本一键解析)", expanded=False):
        st.caption(
            "💡 把券商 App / Wind / 同花顺导出的持仓粘贴到下方,系统自动识别 "
            "ticker / 股数 / 成本价,逐行勾选确认后写入 portfolio.yaml(自动 .bak 备份)。"
        )

        tab_text, tab_img, tab_manual = st.tabs(["📋 粘贴文本", "📷 截图(VLM)", "✏️ 手动新增"])

        with tab_text:
            _render_text_intake()

        with tab_img:
            _render_screenshot_intake()

        with tab_manual:
            _render_manual_add()

        # 候选清单(文本 / 截图共用)— 在所有 tab 之外渲染
        if st.session_state.get("dc_intake_rows"):
            st.divider()
            _render_candidate_list()


def _render_text_intake() -> None:
    """📋 文本路径主流程:粘贴 → 解析 → 候选清单(候选 UI 由 _render_candidate_list 统一)."""
    sample = (
        "# 示例(支持 CSV/TSV/空格/中英混合):\n"
        "# 600519,100,1500\n"
        "# 美的集团 000333 200 65.0\n"
        "# 02097 100 5.5\n"
    )
    raw = st.text_area(
        "粘贴持仓行(每行一只,#开头视为注释)",
        height=160,
        placeholder=sample,
        key="dc_intake_raw",
    )

    if st.button("🔍 解析", key="dc_intake_parse"):
        if not raw.strip():
            st.warning("请先粘贴文本")
        else:
            parsed = parse_text(raw)
            universe, name_map = _load_universe()
            held = _held_tickers()
            rows = build_candidates(parsed, universe, held, name_map)
            st.session_state["dc_intake_rows"] = [r.to_dict() for r in rows]
            st.rerun()


def _render_candidate_list() -> None:
    """候选清单 — 文本 / 截图路径共用."""
    rows: list[dict] = st.session_state.get("dc_intake_rows") or []
    if not rows:
        return

    st.markdown(f"**📋 候选清单({len(rows)} 条)** — 勾选要写入的行,可直接编辑字段")

    df = pd.DataFrame(rows)
    edited = st.data_editor(
        df,
        column_config={
            "加入": st.column_config.CheckboxColumn("加入", help="勾选后写入 portfolio.yaml", default=False),
            "代码": st.column_config.TextColumn(
                "代码",
                help="6 位 A 股 / 5 位港股;识别失败的可手动补",
                max_chars=6,
            ),
            "公司": st.column_config.TextColumn("公司"),
            "股数": st.column_config.NumberColumn("股数", format="%d"),
            "成本价": st.column_config.NumberColumn("成本价", format="%.2f"),
            "现价": st.column_config.NumberColumn("现价", format="%.2f"),
            "状态": st.column_config.TextColumn("状态", disabled=True),
            "备注": st.column_config.TextColumn("备注", disabled=True),
            "原文": st.column_config.TextColumn("原文", disabled=True),
        },
        hide_index=True,
        width="stretch",
        key="dc_intake_editor",
    )

    selected = edited[edited["加入"] == True]  # noqa: E712
    n_sel = len(selected)

    col_a, col_b, col_c = st.columns([2, 1, 1])
    with col_a:
        st.caption(f"已勾选 {n_sel} 条 / 共 {len(edited)} 条")
    with col_b:
        if st.button("🔄 清空候选", key="dc_intake_reparse"):
            st.session_state.pop("dc_intake_rows", None)
            st.rerun()
    with col_c:
        write_btn = st.button(
            f"💾 写入 ({n_sel})",
            type="primary",
            disabled=(n_sel == 0),
            key="dc_intake_write",
        )

    if write_btn:
        _apply_to_yaml(selected.to_dict(orient="records"))


def _render_screenshot_intake() -> None:
    """📷 截图路径 — 上传图片 → Claude Vision 识别 → 复用候选清单 UI."""
    import os

    st.caption(
        "💡 上传券商 App / Wind / 同花顺持仓截图(PNG / JPEG / WebP / GIF)。"
        "Claude Vision 识别 ticker / 股数 / 成本 → 自动跳转候选清单。"
    )
    st.warning(
        "⚠️ 隐私提示:截图会上传到 Anthropic API。如含账户号 / 总资产等敏感信息,"
        "请先用图片编辑工具裁剪只留持仓表格部分。"
    )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error(
            "❌ 未检测到 `ANTHROPIC_API_KEY` 环境变量。\n\n"
            "**配置方法**(三选一):\n"
            "- 终端 `export ANTHROPIC_API_KEY=sk-ant-xxx` 后重启 streamlit\n"
            "- 写入 `~/.zshrc` 长期生效\n"
            "- 通过 `.env` 文件 + `python-dotenv` 加载\n\n"
            "**或者**:用「📋 粘贴文本」路径(免 API)。"
        )
        return

    # 首次使用隐私 confirm(session_state 持久,本会话只问一次)
    if not st.session_state.get("dc_vlm_privacy_ack"):
        with st.container(border=True):
            st.markdown("**🔐 首次使用须知**")
            st.markdown(
                "- 截图会通过 HTTPS 上传到 **Anthropic Claude Vision API** 用于识别\n"
                "- API 端默认不存储用户图片,但请**先用图片编辑工具裁剪**,只保留持仓表格部分\n"
                "- 隐藏:账户号 / 总资产 / 个人信息 / 二维码"
            )
            ack = st.checkbox("我已知悉,继续使用截图识别", key="dc_vlm_privacy_check")
            if ack:
                st.session_state["dc_vlm_privacy_ack"] = True
                st.rerun()
            return

    uploaded = st.file_uploader(
        "上传持仓截图",
        type=["png", "jpg", "jpeg", "webp", "gif"],
        accept_multiple_files=False,
        key="dc_intake_image",
    )

    if uploaded is None:
        return

    st.image(uploaded, caption="预览", width="stretch")

    if st.button("🔍 识别(Claude Vision)", type="primary", key="dc_intake_vlm_run"):
        with st.spinner("VLM 识别中..."):
            try:
                image_bytes = uploaded.getvalue()
                parsed = parse_image(image_bytes)
            except Exception as e:
                st.error(f"❌ 识别失败:{e}")
                st.caption("可在下方「📋 粘贴文本」路径手动输入,或检查 ANTHROPIC_API_KEY / 网络。")
                return

        if not parsed:
            st.warning("⚠️ 未识别到任何持仓行 — 请检查截图清晰度,或裁剪只留持仓表格")
            return

        universe, name_map = _load_universe()
        held = _held_tickers()
        rows = build_candidates(parsed, universe, held, name_map)
        st.session_state["dc_intake_rows"] = [r.to_dict() for r in rows]
        st.success(f"✅ 识别 {len(parsed)} 行 — 候选清单已展示在下方,请勾选确认后写入")
        st.rerun()


def _apply_to_yaml(selected: list[dict]) -> None:
    """把已勾选的候选 upsert 到 portfolio.yaml。"""
    if not selected:
        st.warning("无勾选行")
        return

    # 字段完整性最后兜底
    payload: list[dict] = []
    skipped: list[str] = []
    for row in selected:
        t = str(row.get("代码", "")).strip()
        shares = row.get("股数")
        cost = row.get("成本价")
        if not t:
            skipped.append(f"(无代码)→ {row.get('原文', '')}")
            continue
        if shares is None or pd.isna(shares):
            skipped.append(f"{t} 缺股数")
            continue
        if cost is None or pd.isna(cost):
            skipped.append(f"{t} 缺成本价")
            continue
        payload.append({
            "ticker": t,
            "name": row.get("公司") or "",
            "status": "active",
            "shares": float(shares),
            "cost_basis": float(cost),
            "first_buy_date": _date_cls.today().isoformat(),
        })

    if not payload:
        st.error(f"全部行字段不全,未写入。问题:{', '.join(skipped)}")
        return

    try:
        bak, stats = upsert_holdings(payload)
    except Exception as e:
        st.error(f"❌ 写入失败:{e}")
        return

    # 联动决策日志:每条新增/更新视作"买入/加仓"事件
    logged = _log_intake_decisions(payload)

    msgs = [f"✅ 已写入 {stats['added']} 新增 + {stats['updated']} 更新"]
    if logged:
        msgs.append(f"📝 决策日志追加 {logged} 条")
    if stats.get("status_flipped"):
        msgs.append("📌 _meta.status: demo → live")
    if bak:
        msgs.append(f"💾 备份:{bak.name}")
    if skipped:
        msgs.append(f"⚠️ 跳过 {len(skipped)} 条:{', '.join(skipped)}")
    st.success("  ·  ".join(msgs))

    st.session_state.pop("dc_intake_rows", None)
    st.cache_data.clear()
    st.rerun()


def _log_intake_decisions(payload: list[dict]) -> int:
    """智能录入写入后,自动追加决策日志。返回成功条数。

    每条 ticker:
      - 已在 portfolio → action="加仓"(updated)
      - 不在 → action="买入"(added)

    snapshot 含 peer_advice(C4)— 自动捕获当时 vs 同行评级。
    """
    try:
        sys.path.insert(0, str(ROOT / ".tools"))
        from decisions import db as decisions_db
        from decisions import snapshot as decisions_snapshot
    except Exception:
        return 0

    held = _held_tickers()
    logged = 0
    for row in payload:
        t = row.get("ticker")
        if not t:
            continue
        action = "加仓" if t in held else "买入"
        try:
            snap = {}
            try:
                snap = decisions_snapshot.capture(t)
            except Exception:
                pass
            decisions_db.insert(
                ticker=t,
                folder="",
                date=_date_cls.today(),
                action=action,
                weight_change=0.0,
                price=float(row.get("cost_basis") or 0.0),
                rationale=f"[智能录入] 录入 {row.get('shares')} 股,成本价 {row.get('cost_basis')}",
                thesis_5y="",
                risks="",
                tags="auto-intake",
                snapshot=snap,
            )
            logged += 1
        except Exception:
            pass
    return logged


def _render_rebalance_panel(snap: HoldingsSnapshot) -> None:
    """🚨 再平衡建议(M4-#5)— 结构化 proposal + diff 预览 + 一键写入."""
    try:
        proposals = plan_rebalance(snap)
    except Exception as e:
        st.warning(f"再平衡引擎失败:{e}")
        return

    if not proposals:
        if snap.rebalance_alerts:
            with st.expander(f"🚨 引擎原始提示({len(snap.rebalance_alerts)} 项)", expanded=False):
                for a in snap.rebalance_alerts:
                    st.markdown(f"- {a}")
        else:
            st.success("🟢 当前持仓全部在再平衡规则内,无建议")
        return

    actionable = [p for p in proposals if not p.review_only]
    review_only = [p for p in proposals if p.review_only]

    with st.expander(
        f"🚨 再平衡建议({len(proposals)} 项 · 可一键执行 {len(actionable)} 项)",
        expanded=True,
    ):
        if actionable:
            st.markdown("**🔧 可自动调整 target_weight:**")
            df = pd.DataFrame([
                {
                    "代码": p.ticker, "公司": p.name, "动作": p.action,
                    "规则": p.rule,
                    "调整": p.diff_label(),
                    "理由": p.rationale,
                }
                for p in actionable
            ])
            st.dataframe(df, width="stretch", hide_index=True)

        if review_only:
            st.markdown("**👀 仅提示(需人工判断,不自动改 yaml):**")
            for p in review_only:
                st.caption(f"- 🔸 {p.name}({p.ticker})· {p.rationale}")

        # 引擎原始字符串提示(可能含 planner 未结构化的兜底信息)
        if snap.rebalance_alerts:
            with st.expander(f"📋 引擎原始提示({len(snap.rebalance_alerts)} 项,只读)", expanded=False):
                for a in snap.rebalance_alerts:
                    st.markdown(f"- {a}")

        if not actionable:
            return

        # 二次确认
        col_a, col_b, col_c = st.columns([2, 1, 1])
        with col_a:
            confirm = st.checkbox(
                "我已审阅 diff,确认应用上述调整",
                key="dc_rebalance_confirm",
            )
        with col_b:
            preview_btn = st.button("👁️ 预览 diff", key="dc_rebalance_preview")
        with col_c:
            apply_btn = st.button(
                f"✏️ 一键应用 ({len(actionable)})",
                type="primary",
                disabled=not confirm,
                key="dc_rebalance_apply",
            )

        if preview_btn:
            st.markdown("**📋 修改预览(yaml diff)**")
            for p in actionable:
                st.code(
                    f"# {p.ticker} {p.name}\n"
                    f"- target_weight: {p.old_target}\n"
                    f"+ target_weight: {round(p.new_target, 4)}\n"
                    f"# 理由:{p.rationale}",
                    language="diff",
                )

        if apply_btn:
            try:
                import sys
                sys.path.insert(0, str(ROOT / ".tools"))
                from decisions import db as decisions_db_mod
            except Exception:
                decisions_db_mod = None

            try:
                result = apply_proposals(actionable, decisions_db=decisions_db_mod)
            except Exception as e:
                st.error(f"❌ 应用失败:{e}")
                return

            msgs = [f"✅ 已调整 {result['applied']} 条 target_weight"]
            if result.get("logged"):
                msgs.append(f"📝 决策日志追加 {result['logged']} 条")
            if result.get("backup"):
                msgs.append(f"💾 备份:{result['backup']}")
            st.success("  ·  ".join(msgs))
            st.cache_data.clear()
            st.rerun()


def _render_manual_add() -> None:
    """✏️ 手动新增单条 — 给 1-2 家小批量场景。"""
    universe, name_map = _load_universe()
    options = sorted(universe)

    with st.form("dc_manual_form", clear_on_submit=True):
        col_a, col_b = st.columns([1, 1])
        with col_a:
            ticker = st.selectbox("代码(15 家清单)", options, key="dc_manual_ticker") if options else st.text_input("代码", key="dc_manual_ticker_free")
            shares = st.number_input("股数", min_value=0.0, step=100.0, format="%.2f", key="dc_manual_shares")
        with col_b:
            cost = st.number_input("成本价 ¥", min_value=0.0, step=0.01, format="%.2f", key="dc_manual_cost")
            first_buy = st.date_input("建仓日", value=_date_cls.today(), key="dc_manual_date")

        target_w = st.slider("目标权重", 0.0, 0.30, 0.10, 0.01, key="dc_manual_tw")
        thesis = st.text_input("一句话逻辑(可选)", key="dc_manual_thesis")
        submitted = st.form_submit_button("💾 写入 portfolio.yaml", type="primary")

    if submitted:
        if not ticker or shares <= 0 or cost <= 0:
            st.error("代码 / 股数 / 成本价 三项必填且 > 0")
            return
        try:
            bak, stats = upsert_holdings([{
                "ticker": ticker,
                "name": name_map.get(ticker, ""),
                "status": "active",
                "shares": float(shares),
                "cost_basis": float(cost),
                "first_buy_date": first_buy.isoformat(),
                "target_weight": float(target_w),
                "thesis": thesis,
            }])
        except Exception as e:
            st.error(f"写入失败:{e}")
            return
        msgs = [f"✅ {ticker} 已写入"]
        if stats.get("status_flipped"):
            msgs.append("📌 demo → live")
        if bak:
            msgs.append(f"💾 备份:{bak.name}")
        st.success("  ·  ".join(msgs))
        st.cache_data.clear()
        st.rerun()


# ─── 段 1:持仓总览 ─────────────────────────────────────────────────
def _render_holdings_overview(snap: HoldingsSnapshot) -> None:
    """v2.8 重构:首屏待办 → 统一持仓表 → 动作面板,概况/再平衡/审计折叠。"""

    # 段 1:🚨 待办动作(首屏黄金位)
    _inbox.render(snap)
    st.divider()

    # 段 2:📋 持仓 / 观察池 单表(active + watch 同列)
    _table.render(snap, include_watch=True)
    st.divider()

    # 段 3:动作面板(清仓 / 取消 / 硬删)— 常驻可见,watch 也能用
    _actions.render(snap)

    # 段 4 起:折叠区
    with st.expander("📥 智能录入持仓(从券商导出文本一键解析)", expanded=False):
        _render_smart_intake()

    actives = [r for r in snap.rows if r.status == "active"]
    if actives:
        with st.expander("📊 持仓分布 · 权重饼图 + 行业集中度", expanded=False):
            col_pie, col_industry = st.columns(2)
            with col_pie:
                st.markdown("**🥧 持仓权重饼图**")
                df_pie = pd.DataFrame([
                    {"name": r.name, "actual_weight": r.actual_weight,
                     "target_weight": r.target_weight, "deviation": r.deviation}
                    for r in actives
                ])
                fig = px.pie(df_pie, names="name", values="actual_weight", hole=0.45,
                             hover_data=["target_weight", "deviation"])
                fig.update_traces(textposition="inside", textinfo="percent+label")
                fig.update_layout(height=320, margin=dict(t=10, b=10, l=10, r=10),
                                  showlegend=False)
                st.plotly_chart(fig, width="stretch")

            with col_industry:
                st.markdown("**🏭 行业集中度(按 portfolio.yaml tags[0])**")
                if snap.industry_agg:
                    df_ind = pd.DataFrame([
                        {"行业": a.tag, "持仓数": a.n_holdings,
                         "权重": a.weight, "F-Score 均值": a.avg_fscore}
                        for a in snap.industry_agg
                    ])
                    fig = px.bar(df_ind, x="行业", y="权重", color="F-Score 均值",
                                 color_continuous_scale="RdYlGn", range_color=[3, 9])
                    fig.update_layout(height=320, margin=dict(t=10, b=10, l=10, r=10))
                    fig.update_yaxes(tickformat=".0%")
                    st.plotly_chart(fig, width="stretch")
                else:
                    st.caption("(无 active 持仓或缺 tags)")

    # 再平衡建议(active=0 时函数自身会跳过)
    _render_rebalance_panel(snap)

    # 审计提示
    if snap.audit_alerts:
        with st.expander(f"⏰ 决策审计提示({len(snap.audit_alerts)} 项)", expanded=False):
            for a in snap.audit_alerts:
                st.markdown(f"- {a.msg}")


# ─── 段 3:决策日志(沿用原 tab_decisions)─────────────
def _render_decision_log(
    snap: HoldingsSnapshot, companies, selected, db_mtime,
    decisions_db, decisions_snapshot, folder_to_ticker,
) -> None:
    if decisions_db is None:
        st.error("`.tools/decisions` 模块导入失败,无法使用决策日志功能。")
        return

    # 审计提示已迁移至段 1 顶部(_render_section1_holdings)

    # ─── 录入区(精简版,完整版仍在原 tab_decisions 中)──────────
    with st.expander("➕ 新增决策(快速录入)", expanded=False):
        col_a, col_b, col_c = st.columns([2, 1, 1])
        with col_a:
            d_company = st.selectbox("🏢 公司", companies,
                                     index=companies.index(selected) if selected in companies else 0,
                                     key="dc_company")
        with col_b:
            d_date = st.date_input("📅 日期", value=_date_cls.today(), key="dc_date")
        with col_c:
            d_action = st.selectbox("⚡ 动作", list(decisions_db.ACTIONS), key="dc_action")

        # C4 · 录入前同行建议提示(动态显示当前 d_company 的 peer_advice 摘要)
        try:
            _d_ticker = folder_to_ticker.get(d_company, "")
            if _d_ticker:
                import sys as _sys
                _dash = ROOT / ".tools" / "dashboard"
                if str(_dash) not in _sys.path:
                    _sys.path.insert(0, str(_dash))
                import peers.advisor as _pa  # noqa: WPS433
                _adv = _pa.advise(_d_ticker)
                if _adv is not None and _adv.n_peers > 0:
                    _top3 = sorted(
                        _adv.verdicts,
                        key=lambda x: abs(x.signal) * x.weight,
                        reverse=True,
                    )
                    _evidence = [
                        f"{v.metric}={v.percentile:.0f}%·{v.label}"
                        for v in _top3 if v.signal != 0 and v.percentile is not None
                    ][:3]
                    _bg = (
                        "#1b8a3a" if "低估" in _adv.overall_label else
                        "#d9534f" if "高估" in _adv.overall_label else
                        "#f0ad4e"
                    )
                    st.markdown(
                        f'<div style="padding:8px 12px;border-radius:6px;'
                        f'background:{_bg};color:white;margin:6px 0;font-size:13px">'
                        f'💡 vs 同行业(<b>{_adv.industry or "—"}</b> {_adv.n_peers} 家):'
                        f'<b>{_adv.overall_emoji} {_adv.overall_label}</b> '
                        f'· {_adv.quality_label} · 加权 {_adv.weighted_sum:+.0f}'
                        f'<br><span style="font-size:12px;opacity:0.92">'
                        f'Top: {" / ".join(_evidence) if _evidence else "(无显著信号)"}'
                        f'</span></div>',
                        unsafe_allow_html=True,
                    )
                    st.caption("⤴️ 录入快照会自动包含此结论(可在历史表 vs 同行 列回看)")
        except Exception:
            pass  # 同行库未刷新或缺数据时静默(主流程不阻塞)

        col_d, col_e = st.columns([1, 2])
        with col_d:
            d_weight = st.number_input("Δ 仓位 %", value=0.0, step=0.5, format="%.2f", key="dc_weight")
            d_price = st.number_input("成交价 ¥", value=0.0, step=0.01, format="%.2f", key="dc_price")
        with col_e:
            d_rationale = st.text_area("rationale", height=80, key="dc_rationale_short",
                                       placeholder="为什么是现在(2 个独立数据点)")
            d_tags = st.text_input("tags(逗号)", key="dc_tags_short")

        if st.button("💾 保存决策", type="primary", key="dc_save"):
            if not d_rationale.strip():
                st.error("rationale 必填")
            else:
                d_ticker = folder_to_ticker.get(d_company, "")
                snap_dict = (decisions_snapshot.capture(d_ticker)
                             if (d_ticker and decisions_snapshot is not None) else {})
                try:
                    new_id = decisions_db.insert(
                        ticker=d_ticker, folder=d_company,
                        date=d_date, action=d_action,
                        weight_change=d_weight, price=d_price,
                        rationale=d_rationale, thesis_5y="", risks="",
                        tags=d_tags, snapshot=snap_dict,
                    )
                    st.success(f"✅ 已保存(id={new_id})· 完整三件事请到原「📝 决策日志」Tab")
                except Exception as e:
                    st.error(f"保存失败:{e}")

    # 历史列表
    st.markdown("**📚 历史决策(最近 100 条)**")
    df = decisions_db.list_all(limit=100)
    if df is None or df.empty:
        st.caption("(暂无决策记录)")
        return

    # C4 · 从 snapshot_json 解出 peer_advice
    import json as _json
    def _peer_label(j):
        if not j or pd.isna(j):
            return "—"
        try:
            d = _json.loads(j) if isinstance(j, str) else j
            pa = d.get("peer_advice")
            if pa:
                sig = pa.get("weighted_sum", 0)
                return f"{pa['overall_label']}({sig:+.0f})"
        except Exception:
            return "—"
        return "—"
    df = df.copy()
    df["vs_peer"] = df["snapshot_json"].apply(_peer_label)

    df_view = df[["date", "folder", "ticker", "action", "weight_change", "price",
                  "snapshot_pe", "snapshot_pe_pct_10y", "snapshot_fscore",
                  "vs_peer", "rationale"]].copy()
    df_view.columns = ["日期", "公司", "代码", "动作", "Δ%", "价格",
                       "PE", "PE 分位(10y)", "F-Score", "vs 同行", "理由"]

    def _action_color(v):
        if not isinstance(v, str): return ""
        if v in ("买入", "加仓"): return "background-color:#1b8a3a; color:white"
        if v in ("减仓", "清仓"): return "background-color:#d9534f; color:white"
        return "background-color:#f0ad4e; color:black"

    styler = (
        df_view.style
        .map(_action_color, subset=["动作"])
        .format({
            "PE": "{:.1f}", "PE 分位(10y)": "{:.1%}", "Δ%": "{:+.2f}", "价格": "{:.2f}",
        }, na_rep="—")
    )
    st.dataframe(styler, width="stretch", hide_index=True, height=320)


# ─── 段 3:月报历史 ─────────────────────────────────────────────────
def _render_monthly_reports() -> None:
    # 聚合两类月报:.temp 自动数据 + 知识库手写复盘
    raw_reports = sorted(REVIEW_DIR_TEMP.glob("monthly_review_*.md"), reverse=True)
    final_reports = (sorted(REVIEW_DIR_KNOWLEDGE.glob("月度复盘_*.md"), reverse=True)
                     if REVIEW_DIR_KNOWLEDGE.exists() else [])

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown(f"**📊 原始数据快照({len(raw_reports)} 份)**")
        if not raw_reports:
            st.caption("(无 — 跑 `python3 .tools/portfolio/monthly_review.py` 生成)")
        else:
            picked = st.selectbox("选择月份", [p.name for p in raw_reports], key="mr_raw")
            target = REVIEW_DIR_TEMP / picked
            if target.exists():
                with st.expander("📖 内容预览", expanded=False):
                    st.markdown(target.read_text(encoding="utf-8"))
                st.download_button(
                    "⬇️ 下载 markdown",
                    target.read_bytes(), file_name=picked, mime="text/markdown",
                    key="mr_dl_raw",
                )

    with col_r:
        st.markdown(f"**📝 完整复盘报告({len(final_reports)} 份)**")
        if not final_reports:
            st.caption("(无 — 让 Claude 按 .claude/prompts/monthly_review.md 写)")
        else:
            picked = st.selectbox("选择月份", [p.name for p in final_reports], key="mr_final")
            target = REVIEW_DIR_KNOWLEDGE / picked
            if target.exists():
                with st.expander("📖 内容预览", expanded=False):
                    st.markdown(target.read_text(encoding="utf-8"))

    # PDF 渲染入口
    st.divider()
    with st.expander("🖨️ 月报 PDF 渲染 / 邮件发送(dash-04 后台)", expanded=False):
        st.markdown(
            "- 渲染 PDF:`python3 .tools/portfolio/render_monthly_pdf.py --month YYYY-MM`\n"
            "- 邮件发送:`python3 .tools/portfolio/send_monthly_email.py --month YYYY-MM --to you@example.com`\n"
            "- LaunchAgent 安装:`bash .tools/portfolio/install_monthly_cron.sh`(每月 1 号 09:00 自动)"
        )


# ─── 四段式 section 包装 ───────────────────────────────────────────
def _render_section1_holdings(snap: HoldingsSnapshot) -> None:
    """段 1:持仓总览 + 审计提示(从原段 2 顶部迁来)。"""
    # 审计提示置顶(从原 _render_decision_log L572-577 迁来)
    if snap.audit_alerts:
        with st.container(border=True):
            st.markdown(f"**🔔 审计提示({len(snap.audit_alerts)} 项 active 持仓需复盘)**")
            for a in snap.audit_alerts:
                st.caption(f"- {a.msg}")

    _render_holdings_overview(snap)


def _render_section2_tracker(snap: HoldingsSnapshot) -> None:
    """段 2:持仓跟踪与决策(Agent-B 交付的 holding_tracker)。"""
    try:
        from tabs.decision.holding_tracker import render as _render_tracker
    except ImportError:
        st.info("段 2 持仓跟踪与决策模块加载中…")
        return
    try:
        _render_tracker(snap)
    except Exception as e:
        st.warning(f"段 2 渲染失败:{e}")


def _render_section3_decision_log(
    snap: HoldingsSnapshot, companies, selected, db_mtime,
    decisions_db, decisions_snapshot, folder_to_ticker,
) -> None:
    """段 3:决策日志(审计提示已迁至段 1)。"""
    _render_decision_log(snap, companies, selected, db_mtime,
                         decisions_db, decisions_snapshot, folder_to_ticker)


def _render_section4_monthly_reports() -> None:
    """段 4:月报历史。"""
    _render_monthly_reports()


def apply_nav_prefill(prefill: dict | list | str | None) -> None:
    """从 nav_prefill 或 nav_intent.prefill 注入决策录入表单默认值。"""
    if not isinstance(prefill, dict):
        return
    _price = prefill.get("price")
    if _price is not None:
        try:
            st.session_state["dc_price"] = float(_price)
        except (TypeError, ValueError):
            pass
    _reason = prefill.get("reason_template")
    if _reason:
        st.session_state["dc_rationale_short"] = str(_reason)


# ─── 主入口 ────────────────────────────────────────────────────────
def render(companies, selected, db_mtime, decisions_db, decisions_snapshot,
           folder_to_ticker_fn) -> None:
    """dash-04 决策中心 = 4 个子 Tab。

    子 Tab 1:持仓总览(含审计提示)
    子 Tab 2:持仓跟踪与决策(4 卡片单股决策视图)
    子 Tab 3:决策日志
    子 Tab 4:月报历史

    参数:
      companies: 全 15 家公司 folder 列表
      selected:  当前选中的公司 folder(供录入预填)
      db_mtime:  preson.duckdb mtime(用于 cache 失效)
      decisions_db / decisions_snapshot: app.py 已 import 的模块
      folder_to_ticker_fn: 现成的 dict(folder -> ticker)
    """
    try:
        snap = cached_snapshot()
    except Exception as e:
        st.error(f"持仓快照装配失败:{e}")
        return

    # 跨页跳转:prefill(公司研究 → 决策日志) + sub_tab 指引
    _prefill = st.session_state.pop("nav_prefill", None)
    _sub_tab_hint = None
    try:
        from navigation import consume_intent as _consume_intent
        _intent = _consume_intent()
        if _intent:
            if _intent.get("prefill"):
                _prefill = _intent["prefill"]
            _sub_tab_hint = _intent.get("sub_tab")
    except Exception:
        pass
    apply_nav_prefill(_prefill)
    if _sub_tab_hint:
        st.info(f"👉 请点击 sub-tab:**{_sub_tab_hint}**")

    st.subheader(f"💼 决策中心 · portfolio status={snap.portfolio_status}")
    st.caption(
        f"📌 数据源:portfolio.yaml + DuckDB(prices/valuation/Piotroski) + decisions.duckdb"
        f"  ·  加权 F-Score = Σ(F-Score × 目标权重)"
    )

    tab_holdings, tab_tracker, tab_log, tab_reports = st.tabs([
        "📋 持仓总览",
        "📊 持仓跟踪",
        "📝 决策日志",
        "📅 月报历史",
    ])
    with tab_holdings:
        _render_section1_holdings(snap)
    with tab_tracker:
        _render_section2_tracker(snap)
    with tab_log:
        _render_section3_decision_log(
            snap, companies, selected, db_mtime,
            decisions_db, decisions_snapshot, folder_to_ticker_fn,
        )
    with tab_reports:
        _render_section4_monthly_reports()
