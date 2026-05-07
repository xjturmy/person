"""D3 阶段 B · 格雷厄姆深度价值五步法 Tab(对照 lynch_analysis.py 模式)。

5 sub-tabs:
  ① 商业模式 → 类型判定 + 行业 + 叙事自评
  ② 盈利能力 → 杜邦三因子 + 现金流验证 + 增长质量
  ③ 财务健康 → 三层防御工事 + 防御 7 准则
  ④ 估值 + 安全边际 → 格氏数 + NCAV + PEG + 仪表盘
  ⑤ 深度审视 → 预警信号 + 卖出触发 + 心理陷阱清单
  🎯 综合结论 → ABCD 评级 + 决策矩阵 + 一键导出 md

设计原则:
  - 复用 graham_steps.py 纯逻辑 + lynch_classifier.load_metrics
  - 不重写底层数据访问,只做 UI 包装
  - 顶部 banner 主色:格雷厄姆蓝(对照林奇绿)
  - Emoji 💎 vs 🌱 区分

入口:
  from tabs.graham_analysis import render
  render(companies, selected, db_mtime, folder_to_ticker_fn)

Author: Claude (D3 Phase B, 2026-05-07)
"""
from __future__ import annotations

import sys
from datetime import date as _date_cls
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
COMPANIES_DIR = ROOT / "02_companies"
KNOWLEDGE_BASE = ROOT / "01_knowledge" / "03_投资策略与选股" / "01_格雷厄姆投资法"

if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from graham_steps import (  # noqa: E402
    CLASS_META, GUARDRAIL_THRESHOLDS,
    classify_graham_type, load_graham_metrics,
    evaluate_earnings_quality, evaluate_three_lines_defense,
    check_graham_number, check_ncav, evaluate_defensive_seven,
    deep_inspection_signals, evaluate_sell_triggers,
)

# 蓝色系(区分林奇绿)
BANNER_GRADIENT = "linear-gradient(90deg, #1e3a8a 0%, #0e7490 100%)"


@st.cache_data(ttl=600, show_spinner=False)
def _metrics_cached(ticker: str, db_mtime: float) -> dict | None:
    if not ticker:
        return None
    try:
        return load_graham_metrics(ticker)
    except Exception as e:
        return {"_error": str(e)}


@st.cache_data(ttl=600, show_spinner=False)
def _classify_cached(ticker: str, db_mtime: float) -> dict | None:
    m = _metrics_cached(ticker, db_mtime)
    if not m or "_error" in m:
        return None
    cls = classify_graham_type(m)
    return cls.to_dict()


# ─── 顶部 banner ────────────────────────────────────────────────────────

def _render_banner(cls_dict: dict, gn_dict: dict) -> None:
    pe_x_pb = gn_dict.get("pe_x_pb")
    safety = gn_dict.get("safety_margin_pct")
    pe_x_pb_str = f"{pe_x_pb:.1f}" if pe_x_pb else "—"
    safety_str = f"{safety:+.1f}%" if safety is not None else "—"

    st.markdown(
        f'<div style="padding:14px 18px;border-radius:10px;'
        f'background:{BANNER_GRADIENT};color:white;margin:8px 0">'
        f'<span style="font-size:26px">💎{cls_dict["cls_emoji"]}</span> '
        f'<span style="font-size:21px;font-weight:700;margin-left:8px">'
        f'价值类型:{cls_dict["cls_name"]}</span>'
        f'<span style="margin-left:14px;background:rgba(255,255,255,0.25);'
        f'padding:3px 10px;border-radius:10px;font-size:13px">'
        f'置信度 {cls_dict["confidence"]*100:.0f}%</span>'
        f'<span style="margin-left:14px;background:rgba(255,255,255,0.18);'
        f'padding:3px 10px;border-radius:10px;font-size:13px">'
        f'PE×PB = {pe_x_pb_str} · 隐含安全边际 {safety_str}</span>'
        f'<div style="font-size:13px;opacity:0.92;margin-top:6px">'
        f'📍 格雷厄姆视角:{CLASS_META.get(cls_dict["cls_id"], ("","",""))[2]}</div>'
        f'<div style="font-size:12px;opacity:0.78;margin-top:4px">'
        f'💡 {cls_dict.get("reason", "")}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── ① 商业模式 ─────────────────────────────────────────────────────────

def _render_step1_business(ticker: str, m: dict, cls_dict: dict, company: str) -> None:
    st.markdown("### 第一步 · 商业模式理解")
    st.caption("📚 方法论:[06_实战_商业模式.md](#)")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("公司", company)
        st.metric("行业(申万一级)", m.get("industry_sw_l1") or "—")
    with col_b:
        st.metric("行业(申万二级)", m.get("industry_sw_l2") or "—")
        st.metric("市值", f"{(m.get('market_cap') or 0)/1e8:.0f} 亿元" if m.get("market_cap") else "—")
    with col_c:
        st.metric("category", m.get("category") or "—")
        st.metric("Ticker", ticker)

    with st.expander("💡 格雷厄姆四类判定(决策树详见 01_四类价值分类.md)", expanded=True):
        st.markdown(f"""
**判定结果**:{cls_dict["cls_emoji"]} **{cls_dict["cls_name"]}** · 置信 {cls_dict["confidence"]*100:.0f}%

**判定依据**:
{cls_dict["reason"]}

**关键 metric**:
""")
        for k, v in cls_dict.get("key_metrics", {}).items():
            st.markdown(f"- **{k}**: {v}")
        if cls_dict.get("notes"):
            st.markdown("\n**提示**:")
            for n in cls_dict["notes"]:
                st.markdown(f"> {n}")

    with st.expander("📝 商业模式自评(用户输入,供决策日志参考)"):
        ss_key = f"graham_business_{ticker}"
        st.text_area(
            "1. 公司是怎么赚钱的?(收入结构 / 主要客户 / 价值链位置)",
            key=f"{ss_key}_revenue",
            placeholder="例:美的 = 暖通空调 45% + 消费电器 40% + 机器人 10% + 海外 5%...",
            height=80,
        )
        st.text_area(
            "2. 护城河:成本优势 / 品牌 / 技术 / 规模 / 渠道(至少 2 条)",
            key=f"{ss_key}_moat",
            placeholder="例:1) 美芝压缩机自给率 80% — 成本优势;2) COLMO 品牌溢价 +15pp...",
            height=80,
        )
        st.text_area(
            "3. 主要风险(内部 / 外部 / 行业)",
            key=f"{ss_key}_risk",
            placeholder="例:房地产链、铜价、库卡整合不及预期、海外地缘...",
            height=80,
        )


# ─── ② 盈利能力 ─────────────────────────────────────────────────────────

def _render_step2_earnings(ticker: str, m: dict) -> None:
    st.markdown("### 第二步 · 盈利能力诊断")
    st.caption("📚 方法论:杜邦三因子 + 现金流验证 + 增长质量(对照 07_实战_盈利.md)")

    quality = evaluate_earnings_quality(m)

    # 杜邦分解
    st.markdown("#### 杜邦三因子分解")
    dupont = quality.get("dupont", {})
    if dupont:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("ROE", f"{dupont.get('ROE', 0)*100:.1f}%" if dupont.get("ROE") else "—")
        with col2:
            st.metric("净利率(5y 均)", f"{dupont.get('net_margin', 0)*100:.1f}%" if dupont.get("net_margin") else "—")
        with col3:
            lev = dupont.get("leverage")
            st.metric("权益乘数", f"{lev:.2f}" if lev else "—",
                      help="杠杆代理 = 1 / (1 - 资产负债率)")
        with col4:
            st.metric("驱动模式", dupont.get("interpretation", "—"))

    # 现金流验证
    st.markdown("#### 现金流验证(利润含金量)")
    col_a, col_b = st.columns(2)
    with col_a:
        cfo_to_ni = quality.get("cfo_to_ni")
        st.metric("CFO/NI(5y 均)",
                  f"{cfo_to_ni:.2f}" if cfo_to_ni is not None else "—",
                  delta=quality.get("cfo_quality", "—"),
                  delta_color="off")
    with col_b:
        st.markdown(f"**质量评级**: {quality.get('cfo_quality')}")
        st.caption("≥ 0.9 优秀 / 0.7-0.9 一般 / < 0.7 预警(纸面富贵)")

    # 增长质量
    st.markdown("#### 增长质量")
    col1, col2, col3 = st.columns(3)
    with col1:
        rev_5y = quality.get("rev_cagr_5y")
        st.metric("营收 5y CAGR", f"{rev_5y*100:+.1f}%" if rev_5y is not None else "—")
    with col2:
        np_yoy = quality.get("np_yoy_recent")
        st.metric("最新净利 YoY", f"{np_yoy:+.1f}%" if np_yoy is not None else "—")
    with col3:
        st.metric("增长质量", quality.get("growth_quality", "—"))

    with st.expander("💡 解读速读"):
        st.markdown("""
**核心拷问**:
1. 增长来自高毛利业务还是低毛利规模产品?
2. 利润含金量(CFO/NI)是否 ≥ 0.9?
3. ROIC 5 年趋势是上升、稳定还是下行?

**ROE 驱动模式说明**:
- **高净利率驱动**(净利率 > 20%):品牌溢价 / 强成本控制(茅台型)
- **高杠杆驱动**(权益乘数 > 2.5):依赖财务杠杆(银行型)
- **均衡**:运营效率 + 适度杠杆(美的型)
""")


# ─── ③ 财务健康 ─────────────────────────────────────────────────────────

def _render_step3_health(ticker: str, m: dict, cls_id: str) -> None:
    st.markdown("### 第三步 · 财务健康(三层防御工事)")
    st.caption("📚 方法论:压力测试 vs 静态合规(对照 08_实战_财务健康.md)")

    tl = evaluate_three_lines_defense(m)

    st.markdown(f"#### 综合评级:{tl.overall_status}")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown("**🛡️ 第一道:现金缓冲**")
        st.markdown(tl.line1_status)
        st.caption(f"代理(流动比率):{m.get('current_ratio', 0):.2f}")
    with col_b:
        st.markdown("**💪 第二道:经营造血**")
        st.markdown(tl.line2_status)
        cfo_to_ni = m.get("cfo_to_ni")
        st.caption(f"CFO/NI = {cfo_to_ni:.2f}" if cfo_to_ni is not None else "—")
    with col_c:
        st.markdown("**🏦 第三道:外部融资空间**")
        st.markdown(tl.line3_status)
        dr = m.get("debt_ratio") or 0
        st.caption(f"资产负债率:{dr*100:.1f}%")

    # 类型驱动的财务护栏阈值
    st.markdown("#### 类型驱动财务护栏")
    th = GUARDRAIL_THRESHOLDS.get(cls_id, GUARDRAIL_THRESHOLDS["enterprising"])
    st.markdown(f"**当前类型**:{th['label']}")

    items = []
    dr = m.get("debt_ratio")
    cr = m.get("current_ratio")
    cn = m.get("cfo_to_ni")
    if dr is not None:
        passed = dr <= th["debt_ratio_max"]
        items.append((f"资产负债率 ≤ {th['debt_ratio_max']*100:.0f}%", f"{dr*100:.1f}%", passed))
    if cr is not None:
        passed = cr >= th["current_ratio_min"]
        items.append((f"流动比率 ≥ {th['current_ratio_min']:.1f}", f"{cr:.2f}", passed))
    if cn is not None:
        passed = cn >= th["cfo_to_ni_min"]
        items.append((f"CFO/NI ≥ {th['cfo_to_ni_min']:.1f}", f"{cn:.2f}", passed))

    if items:
        for name, actual, passed in items:
            emoji = "✅" if passed else "❌"
            st.markdown(f"- {emoji} **{name}** — 实际:{actual}")

    # 防御 7 准则(无论类型都展示)
    st.markdown("---")
    st.markdown("#### 《Intelligent Investor》第 14 章 · 防御 7 准则(A 股调整版)")
    ds = evaluate_defensive_seven(m)
    st.markdown(f"**通过率**:{ds.pass_count}/{ds.total_count} ({ds.pass_rate*100:.0f}%)")
    for it in ds.items:
        with st.container():
            cols = st.columns([0.5, 4, 2, 2])
            with cols[0]:
                st.markdown(it.emoji)
            with cols[1]:
                st.markdown(f"**{it.rule_id}.** {it.name}")
                if it.detail:
                    st.caption(it.detail)
            with cols[2]:
                st.markdown(f"实际:`{it.actual}`")
            with cols[3]:
                st.caption(it.threshold)


# ─── ④ 估值与安全边际 ───────────────────────────────────────────────────

def _render_step4_valuation(ticker: str, m: dict, cls_id: str) -> None:
    st.markdown("### 第四步 · 估值与安全边际")
    st.caption("📚 方法论:PE/PB/PS 三尺主选 + 格氏数 + NCAV + DCF 元检验(对照 09_实战_估值.md)")

    gn = check_graham_number(m)
    ncav = check_ncav(m)

    # 格氏数主面板
    st.markdown("#### 🔢 格氏数(PE × PB ≤ 22.5)")
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("PE-TTM", f"{gn.pe:.2f}" if gn.pe else "—")
    with col_b:
        st.metric("PB", f"{gn.pb:.2f}" if gn.pb else "—")
    with col_c:
        st.metric("PE × PB", f"{gn.pe_x_pb:.1f}" if gn.pe_x_pb else "—",
                  delta=gn.grade, delta_color="off")
    with col_d:
        st.metric("隐含安全边际", f"{gn.safety_margin_pct:+.1f}%" if gn.safety_margin_pct is not None else "—")

    st.markdown(f"**评级**:{gn.grade_emoji} {gn.grade}")

    with st.expander("💡 格氏数为什么是 22.5?"):
        st.markdown("""
- 来源:格雷厄姆原版要求 **PE ≤ 15** 且 **PB ≤ 1.5** → 乘积 ≤ 22.5
- A 股软达标:
  - **≤ 22.5**:严达标(原版,A 股极少)
  - **≤ 30**:软达标 1 档(满分扣减)
  - **≤ 50**:软达标 2 档(灰阶)
  - **> 50**:不达标(估值偏贵,需 PEG 验证)
""")

    # NCAV 面板
    st.markdown("#### 🪙 NCAV 净流动资产法(深度低估检验)")
    if ncav.market_cap and ncav.ncav and ncav.ncav > 0:
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("市值", f"{ncav.market_cap/1e8:.0f} 亿")
        with col_b:
            st.metric("NCAV(流动资产 - 总负债)", f"{ncav.ncav/1e8:.0f} 亿")
        with col_c:
            ratio_str = f"{ncav.mc_to_ncav:.2f}" if ncav.mc_to_ncav else "—"
            st.metric("市值 / NCAV", ratio_str, delta=ncav.grade, delta_color="off")
    else:
        st.info(f"⚪ {ncav.grade}(NCAV 不适用 — 多见于服务/金融业,适用于强资产型公司)")

    # PEG(理杏仁口径,从 lynch 已派生)
    st.markdown("#### 📈 PEG(理杏仁口径)")
    peg = m.get("peg_lixinger")
    if peg is not None:
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("PEG", f"{peg:.2f}")
        with col_b:
            grade = "🟢 便宜" if peg < 1.0 else "🟡 合理" if peg < 1.5 else "🟠 偏贵" if peg < 2.0 else "🔴 泡沫"
            st.metric("评级", grade)
        st.caption(f"PEG = PE-TTM ÷ (净利 3y CAGR × 100) = {gn.pe:.1f if gn.pe else 0} ÷ {(m.get('np_ttm_yoy') or 0):.1f}")
    else:
        st.info("PEG 数据不可用(可能是亏损 / 周期 / 隐蔽资产 — 此时 PEG 失真)")

    # PE 历史分位
    pe_pct = m.get("pe_pct_10y")
    if pe_pct is not None:
        st.markdown("#### 📊 PE 历史 10 年分位")
        st.progress(min(max(pe_pct, 0), 1.0))
        st.caption(f"当前 PE 在自身 10 年时序的 **{pe_pct*100:.0f}%** 分位 · "
                   f"{'🟢 低估' if pe_pct < 0.3 else '🟡 合理' if pe_pct < 0.7 else '🔴 高位'}")

    # 股息率 + 历史分位
    dy = m.get("dividend_yield")
    dy_pct = m.get("dividend_yield_5y_pct")
    if dy is not None:
        st.markdown("#### 💰 股息率 + 历史分位")
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("股息率", f"{dy*100:.2f}%")
        with col_b:
            if dy_pct is not None:
                st.metric("DY 5y 分位", f"{dy_pct*100:.0f}%",
                          delta="高位 = 价格便宜" if dy_pct > 0.7 else "中位",
                          delta_color="off")

    # 🎯 同行雷达联动(D3 阶段 C 项 2 · 5 维 Graham 指标)
    with st.expander("🎯 同行雷达 · 5 维格雷厄姆指标 vs 同行业", expanded=False):
        try:
            import sys as _sys
            _here = str(Path(__file__).resolve().parent.parent)
            if _here not in _sys.path:
                _sys.path.insert(0, _here)
            import graham_peer_radar as _gpr  # noqa: WPS433
            scores = _gpr.graham_peer_scores(ticker, max_peers=4)
            scores_with_data = [s for s in scores if _gpr.has_data(s)]
            if len(scores_with_data) < 1:
                st.info("(无 5 维数据 — peer 公司未在自选清单内)")
            else:
                col_l, col_r = st.columns([3, 2], gap="medium")
                with col_l:
                    st.plotly_chart(
                        _gpr.graham_radar_chart(scores_with_data, ticker),
                        use_container_width=True,
                    )
                with col_r:
                    st.markdown("**📊 同行明细**")
                    df_summary = _gpr.render_summary_table(scores_with_data)
                    st.dataframe(df_summary, use_container_width=True,
                                 hide_index=True)
                missing = [s for s in scores if not _gpr.has_data(s)]
                if missing:
                    miss_names = ", ".join(s.name for s in missing)
                    st.caption(
                        f"⚠️ 同行 {len(missing)} 家无完整数据(不在自选 14 公司清单):"
                        f"{miss_names}"
                    )
                st.caption(
                    "💡 5 维归一化 0-100,高=优 · "
                    "PE/PB/资产负债率「越低越好」· DY/流动比率「越高越好」"
                )
        except Exception as _e:
            st.caption(f"⚠️ 同行雷达加载失败:{_e}")


# ─── ⑤ 深度审视 ─────────────────────────────────────────────────────────

def _render_step5_inspection(ticker: str, m: dict, cls_id: str) -> None:
    st.markdown("### 第五步 · 深度审视(格雷厄姆式拷问)")
    st.caption("📚 方法论:报表深挖 + 多元安全边际 + 心理陷阱(对照 10_实战_深度审视.md)")

    # 预警信号
    st.markdown("#### 🚨 预警信号清单")
    signals = deep_inspection_signals(m)
    for sig in signals:
        with st.container():
            cols = st.columns([1, 4])
            with cols[0]:
                st.markdown(sig["type"])
            with cols[1]:
                st.markdown(sig["detail"])

    # 卖出触发(4 条通用)
    st.markdown("---")
    st.markdown("#### 🔴 4 条通用卖出触发(任一即严肃评估)")
    gn = check_graham_number(m)
    tl = evaluate_three_lines_defense(m)
    triggers = evaluate_sell_triggers(m, cls_id, gn, tl)
    fired_count = sum(1 for t in triggers if t["fired"])
    if fired_count > 0:
        st.error(f"⚠️ 已触发 {fired_count} 条卖出条件 — 严肃评估持仓")
    else:
        st.success("✅ 4 条卖出触发未激活 — 持仓状态健康")

    for t in triggers:
        emoji = "🔴" if t["fired"] else "🟢"
        st.markdown(f"- {emoji} **{t['id']} {t['name']}**: {t['detail']}")

    # 心理陷阱清单
    st.markdown("---")
    st.markdown("#### 🧠 心理陷阱审查(用户自检)")
    with st.expander("4 条独立判断拷问(诚实回答)", expanded=True):
        ss = f"graham_psych_{ticker}"
        st.checkbox("我的买入决定**源于独立研究**,而非市场情绪 / 朋友推荐 / 媒体追捧", key=f"{ss}_indep")
        st.checkbox("我**没有为「成长故事」支付过高溢价**(警惕「明日的明星」宣传)", key=f"{ss}_no_premium")
        st.checkbox("我有**耐心等待 3+ 年**让价值实现 — 不会因为 6 个月不涨就放弃", key=f"{ss}_patience")
        st.checkbox("我能**承受再跌 30%** 的浮亏 — 安全边际是真,不是数字游戏", key=f"{ss}_drawdown")
        st.caption("4 项全勾 = 心理状态健康;< 4 项 = 暂停加仓,等冷静期")


# ─── 🎯 综合结论(ABCD/12345 评级 + 决策导出) ────────────────────────────

def _render_summary(ticker: str, company: str, m: dict,
                     cls_dict: dict, decisions_db=None) -> None:
    st.markdown("### 🎯 综合结论 · ABCD/12345 评级 + 决策导出")
    st.caption("📚 决策矩阵:00_方法论总览 第三节")

    # 简化的 ABCD 评分(满分制 100):
    # 公司质量 = 防御 7 通过率 × 70 + (CFO/NI 健康 + ROE 高) × 30
    ds = evaluate_defensive_seven(m)
    base_company = (ds.pass_count / max(ds.total_count, 1)) * 70
    cfo_to_ni = m.get("cfo_to_ni") or 0
    roe = m.get("roe") or 0
    bonus = (15 if cfo_to_ni >= 0.9 else 8 if cfo_to_ni >= 0.7 else 0)
    bonus += (15 if roe >= 0.18 else 10 if roe >= 0.12 else 0)
    company_score = base_company + bonus
    company_grade = "A" if company_score >= 85 else "B" if company_score >= 70 else "C" if company_score >= 55 else "D"

    # 价格吸引力 = 格氏数 + PE 分位 + DY 分位
    gn = check_graham_number(m)
    pe_pct = m.get("pe_pct_10y") or 0.5
    dy_pct = m.get("dividend_yield_5y_pct") or 0.5

    price_score = 0
    if gn.pe_x_pb:
        if gn.pe_x_pb <= 22.5: price_score += 50
        elif gn.pe_x_pb <= 30: price_score += 35
        elif gn.pe_x_pb <= 50: price_score += 20
    if pe_pct < 0.3: price_score += 30
    elif pe_pct < 0.5: price_score += 18
    elif pe_pct < 0.7: price_score += 8
    if dy_pct > 0.7: price_score += 20
    elif dy_pct > 0.4: price_score += 10

    if price_score >= 85: price_grade = 1
    elif price_score >= 70: price_grade = 2
    elif price_score >= 55: price_grade = 3
    elif price_score >= 40: price_grade = 4
    else: price_grade = 5

    # 决策矩阵查表
    decision_matrix = {
        ("A", 1): ("🟢🟢🟢 全力出击", "长期 10-15% 仓位"),
        ("A", 2): ("🟢🟢 重点建仓", "5-10% 仓位"),
        ("A", 3): ("🟢 持有 / 谨慎新增", "维持现仓"),
        ("A", 4): ("🟡 减仓至跟踪仓", "降至 3-5%"),
        ("A", 5): ("🔴 坚决卖出", "估值反转"),
        ("B", 1): ("🟢🟢 重点建仓", "5-8% 仓位"),
        ("B", 2): ("🟢 适度配置", "3-5% 仓位"),
        ("B", 3): ("🟡 持有 / 跟踪", "—"),
        ("B", 4): ("🟠 考虑减仓", "—"),
        ("B", 5): ("🔴 卖出", "—"),
        ("C", 1): ("🟡 小仓试探", "≤ 3%"),
        ("C", 2): ("🟠 少量试探", "≤ 1%"),
        ("C", 3): ("⚪ 观望", "—"),
        ("C", 4): ("🔴 回避", "—"),
        ("C", 5): ("🔴 坚决回避", "—"),
        ("D", 1): ("⚠️ 不参与", "价值陷阱预警"),
        ("D", 2): ("🔴 不参与", "—"),
        ("D", 3): ("🔴 不参与", "—"),
        ("D", 4): ("🔴 不参与", "—"),
        ("D", 5): ("🔴 不参与", "—"),
    }
    decision, position = decision_matrix.get((company_grade, price_grade), ("⚪ 待评估", "—"))

    # 主面板
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("公司质量", f"{company_grade} 级",
                  delta=f"{company_score:.0f}/110 分", delta_color="off")
    with col_b:
        st.metric("价格吸引力", f"{price_grade} 级",
                  delta=f"{price_score:.0f}/110 分", delta_color="off")
    with col_c:
        st.metric("决策建议", decision, delta=position, delta_color="off")

    # 决策矩阵可视化
    st.markdown("#### 决策矩阵")
    matrix_md = "| 公司 \\ 价格 | 1 (低估) | 2 | 3 | 4 | 5 (高估) |\n"
    matrix_md += "|---|---|---|---|---|---|\n"
    for grade in ["A", "B", "C", "D"]:
        row = f"| **{grade} 级** |"
        for p in [1, 2, 3, 4, 5]:
            cell = decision_matrix.get((grade, p), ("—", ""))[0]
            if grade == company_grade and p == price_grade:
                row += f" **🎯 {cell}** |"
            else:
                row += f" {cell} |"
        matrix_md += row + "\n"
    st.markdown(matrix_md)

    # 一键导出 md
    st.markdown("---")
    st.markdown("#### 📤 导出决策报告")
    if st.button("💾 写到 02_companies/{N}_{name}/05_投资决策/", key=f"graham_export_{ticker}"):
        try:
            md_content = _build_decision_md(
                ticker=ticker, company=company, m=m, cls_dict=cls_dict,
                gn=gn, ds=ds,
                company_score=company_score, company_grade=company_grade,
                price_score=price_score, price_grade=price_grade,
                decision=decision, position=position,
            )
            target = _find_company_dir(company) / "05_投资决策"
            target.mkdir(parents=True, exist_ok=True)
            out_path = target / f"格雷厄姆五步分析_{_date_cls.today()}_auto.md"
            out_path.write_text(md_content, encoding="utf-8")
            st.success(f"✅ 已写入 {out_path.relative_to(ROOT)}")
            # 可选:写决策日志
            if decisions_db is not None:
                _write_decision_log(decisions_db, ticker, company, decision, position,
                                    company_grade, price_grade)
        except Exception as e:
            st.error(f"❌ 导出失败:{e}")


def _find_company_dir(company: str) -> Path:
    """匹配 02_companies/01_新华保险 这种目录。"""
    for child in COMPANIES_DIR.iterdir():
        if not child.is_dir():
            continue
        if child.name.endswith(f"_{company}"):
            return child
    # fallback
    return COMPANIES_DIR / company


def _build_decision_md(*, ticker: str, company: str, m: dict, cls_dict: dict,
                        gn, ds, company_score: float, company_grade: str,
                        price_score: float, price_grade: int,
                        decision: str, position: str) -> str:
    today = _date_cls.today()
    pe_x_pb = gn.pe_x_pb if gn.pe_x_pb else 0
    dy = (m.get("dividend_yield") or 0) * 100
    pe_str = f"{gn.pe:.2f}" if gn.pe else "—"
    pb_str = f"{gn.pb:.2f}" if gn.pb else "—"

    md = f"""# 格雷厄姆五步分析 · {company}({ticker})

> **日期**:{today} · **方法论**:格雷厄姆深度价值五步法
>
> **判定**:{cls_dict["cls_emoji"]} **{cls_dict["cls_name"]}** · 置信度 {cls_dict["confidence"]*100:.0f}%

---

## 一、商业模式速览

- **行业**:{m.get("industry_sw_l1") or "—"} / {m.get("industry_sw_l2") or "—"}
- **市值**:{(m.get("market_cap") or 0)/1e8:.0f} 亿元
- **判定依据**:{cls_dict["reason"]}

## 二、估值与安全边际

| 指标 | 数值 |
|------|------|
| PE-TTM | {pe_str} |
| PB | {pb_str} |
| **格氏数 PE × PB** | **{pe_x_pb:.1f}** |
| 评级 | {gn.grade_emoji} {gn.grade} |
| 隐含安全边际 | {gn.safety_margin_pct:+.1f}% |
| 股息率 | {dy:.2f}% |

## 三、防御 7 准则({ds.pass_count}/{ds.total_count})

"""
    for it in ds.items:
        md += f"- {it.emoji} **{it.rule_id}** {it.name} — 实际 `{it.actual}` / 阈值 `{it.threshold}`\n"

    md += f"""

## 四、ABCD/12345 综合评级

- **公司质量**:{company_grade} 级 ({company_score:.0f}/110)
- **价格吸引力**:{price_grade} 级 ({price_score:.0f}/110)
- **决策**:{decision} · {position}

---

## 五、自动结论

**当前判定**:
- 类型:{cls_dict["cls_name"]}
- 公司质量 {company_grade} 级 + 价格 {price_grade} 级 → **{decision}**
- 仓位建议:{position}

**注意事项**:
1. 本报告基于自动数据生成,需结合定性研究审视
2. 心理陷阱审查请在 Dashboard "⑤ 深度审视" Tab 完成
3. 关键卖出触发请定期复核(季度)

---

🤖 Generated by Dashboard · D3 阶段 B(2026-05-07)
"""
    return md


def _write_decision_log(decisions_db, ticker: str, company: str,
                         decision: str, position: str,
                         q_grade: str, p_grade: int) -> None:
    """写到 decisions.duckdb(若已挂载)。"""
    try:
        decisions_db.execute(
            "INSERT INTO decisions(date, ticker, company, action, reason, position, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [str(_date_cls.today()), ticker, company, decision,
             f"格雷厄姆 {q_grade}{p_grade}", position, "graham_tab"],
        )
    except Exception:
        pass  # 表不存在或其他失败不阻塞 UI


# ─── 主入口 ─────────────────────────────────────────────────────────────

def render(companies: list[str], selected: str, db_mtime: float,
           decisions_db=None, folder_to_ticker_fn=None) -> None:
    st.subheader("💎 格雷厄姆深度价值投资法 · 五步框架")

    # 顶部公司选择
    col_c, col_y, col_r = st.columns([3, 1, 1])
    with col_c:
        idx = companies.index(selected) if selected in companies else 0
        company = st.selectbox("公司", companies, index=idx,
                                key="graham_company", label_visibility="collapsed")
    with col_y:
        year = st.selectbox(
            "年份",
            list(range(_date_cls.today().year, _date_cls.today().year - 5, -1)),
            index=0, key="graham_year", label_visibility="collapsed",
        )
    with col_r:
        if st.button("🔄 重新评估", key="graham_refresh", use_container_width=True):
            _classify_cached.clear()
            _metrics_cached.clear()
            st.rerun()

    # ticker 解析
    if folder_to_ticker_fn:
        f2t = folder_to_ticker_fn if isinstance(folder_to_ticker_fn, dict) else folder_to_ticker_fn
        ticker = f2t.get(company, "")
    else:
        from dashboard_helpers import _folder_to_ticker
        ticker = _folder_to_ticker(db_mtime).get(company, "")

    if not ticker:
        st.error(f"⚠️ 未找到 {company} 的 ticker 映射")
        return

    m = _metrics_cached(ticker, db_mtime)
    cls_dict = _classify_cached(ticker, db_mtime)

    if m is None or cls_dict is None or "_error" in (m or {}):
        err = m.get("_error") if m else "数据加载失败"
        st.error(f"⚠️ {company} ({ticker}) — {err}")
        return

    # 顶部 banner
    gn = check_graham_number(m)
    gn_dict = {"pe_x_pb": gn.pe_x_pb, "safety_margin_pct": gn.safety_margin_pct}
    _render_banner(cls_dict, gn_dict)

    # 5 sub-tabs + 综合结论
    tab1, tab2, tab3, tab4, tab5, tab_sum = st.tabs([
        "① 商业模式", "② 盈利能力", "③ 财务健康",
        "④ 估值/安全边际", "⑤ 深度审视", "🎯 综合结论",
    ])

    with tab1:
        _render_step1_business(ticker, m, cls_dict, company)
    with tab2:
        _render_step2_earnings(ticker, m)
    with tab3:
        _render_step3_health(ticker, m, cls_dict["cls_id"])
    with tab4:
        _render_step4_valuation(ticker, m, cls_dict["cls_id"])
    with tab5:
        _render_step5_inspection(ticker, m, cls_dict["cls_id"])
    with tab_sum:
        _render_summary(ticker, company, m, cls_dict, decisions_db)


__all__ = ["render"]
