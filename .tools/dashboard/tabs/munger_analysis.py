"""v2.4 step-C · 芒格多元思维 Tab — 决策检查清单 + 心理偏差自检 + 反向思维。

5 sub-tabs:
  ① 多元思维速览 → 4 层格栅 / 7 类模型 / 4 大原则 / 经典语录
  ② 决策检查清单 → 10 项打分(1-5)+ 自动加权总分 + 决策规则
  ③ 反向思维   → 4 大失败路径 + 用户自填(checkbox + textarea)
  ④ 心理偏差自检 → 9 项偏差(yes/no)+ 防御策略提示
  ⑤ 决策报告导出 → md 写入 02_companies/{N}/05_投资决策/

设计原则:
  - 芒格法主要是**定性**,不与 graham/lynch/piotroski 重复定量评分
  - 唯一的"硬指标对照"放在 ② 第 4/5/8/9 项,自动从 DuckDB 拉
  - 复用 lynch_classifier.load_metrics_from_db
  - 顶部 banner 主色:芒格紫(对照林奇绿/格雷厄姆蓝/黄金金)

入口:
  from tabs.munger_analysis import render
  render(companies, selected, db_mtime, decisions_db, folder_to_ticker_fn)

知识来源:
  - 01_knowledge/03_投资策略与选股/00_芒格决策检查清单.md(10 项实战清单)
  - 01_knowledge/03_投资策略与选股/03_多元思维.md(理论层 4 层格栅)
  - 11_大师哲学_深化补充.md(芒格哲学速读已在 master_philosophy.py)

Author: Claude (v2.4 step-C, 2026-05-08)
"""
from __future__ import annotations

import sys
from datetime import date as _date_cls
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
COMPANIES_DIR = ROOT / "02_companies"
KNOWLEDGE_BASE = ROOT / "01_knowledge" / "03_投资策略与选股"

if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

# 紫色系(对照林奇绿 / 格雷厄姆蓝 / 黄金金)
BANNER_GRADIENT = "linear-gradient(90deg, #4c1d95 0%, #6d28d9 50%, #8b5cf6 100%)"

# ─── 数据加载(复用 lynch_classifier)────────────────────────────────────


@st.cache_data(ttl=600, show_spinner=False)
def _metrics_cached(ticker: str, db_mtime: float) -> dict | None:
    if not ticker:
        return None
    try:
        from masters.lynch.classifier import load_metrics_from_db
        return load_metrics_from_db(ticker)
    except Exception as e:
        return {"_error": str(e)}


# ─── 顶部 banner ────────────────────────────────────────────────────────


def _render_banner(company: str, ticker: str, m: dict) -> None:
    pe = m.get("pe_ttm")
    pb = m.get("pb")
    roe = (m.get("roe") or 0) * 100
    dy = (m.get("dividend_yield") or 0) * 100
    pe_str = f"{pe:.1f}" if pe else "—"
    pb_str = f"{pb:.2f}" if pb else "—"

    st.markdown(
        f'<div style="padding:14px 18px;border-radius:10px;'
        f'background:{BANNER_GRADIENT};color:white;margin:8px 0">'
        f'<span style="font-size:26px">🧠</span> '
        f'<span style="font-size:21px;font-weight:700;margin-left:8px">'
        f'{company} · 芒格多元思维决策框架</span>'
        f'<span style="margin-left:14px;background:rgba(255,255,255,0.25);'
        f'padding:3px 10px;border-radius:10px;font-size:13px">'
        f'PE {pe_str} · PB {pb_str} · ROE {roe:.1f}% · 股息 {dy:.2f}%</span>'
        f'<div style="font-size:13px;opacity:0.92;margin-top:6px">'
        f'📍 芒格视角:决策不是打勾,是用 4 层格栅交叉验证 + 反向思维 + 心理偏差自检</div>'
        f'<div style="font-size:12px;opacity:0.82;margin-top:4px">'
        f'💡 "告诉我我会死在哪里,我就永远不去那里。" — 查理·芒格</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─── ① 多元思维速览(知识层)────────────────────────────────────────────

LATTICE_LAYERS = [
    ("第一层 · 基础学科", [
        ("📐 数学", "概率 / 统计 / 逻辑 / 复利 / 贝叶斯"),
        ("⚙️ 物理", "能量守恒 / 惯性 / 临界质量 / 反馈循环"),
        ("🧬 生物", "进化 / 适应 / 生态位 / 达尔文法则"),
        ("💭 心理学", "认知偏差 / 激励 / 损失厌恶 / 锚定"),
    ]),
    ("第二层 · 应用学科", [
        ("🏗️ 工程", "系统优化 / 容错设计 / 冗余备份"),
        ("🔬 化学", "化合 / 反应 / 平衡"),
        ("💰 经济学", "供需 / 博弈 / 激励机制 / 机会成本"),
        ("📊 会计", "现金流 / 资产 / 价值 / 复式记账"),
    ]),
    ("第三层 · 高阶理论", [
        ("📈 统计", "正态分布 / 抽样偏差 / 肥尾"),
        ("🌐 复杂系统", "涌现性 / 反馈环 / 非线性"),
        ("🧪 进化论", "适应性 / 竞争 / 生存"),
        ("🎯 人类误判", "损失厌恶 / 锚定效应 / 社会认同"),
    ]),
    ("第四层 · 决策融合", [
        ("🔄 双轨分析", "理性算账 + 心理理解"),
        ("🎯 能力圈", "只投自己理解的"),
        ("🔁 逆向思维", "先想如何失败"),
        ("✅ 检查清单", "系统避免遗漏"),
    ]),
]

PRINCIPLES = [
    ("多学科整合", "从不同学科汲取重要模型 — 不局限于财务分析"),
    ("双轨分析", "理性 + 心理双管齐下 — 算对账,也理解人性"),
    ("能力圈原则", "只投资自己能理解的 — 不懂不投"),
    ("逆向思维", "先想如何失败 — 避免愚蠢比追求聪明更重要"),
]

QUOTES = [
    "告诉我我会死在哪里,我就永远不去那里。",
    "投资本来并不难,困难的是保持简单。",
    "承认自己的无知是智慧的开端。",
    "每天起床时,都要比昨天更聪明一点。",
    "我们不学习教训是因为我们过于相信自己已经知道了。",
    "投资的秘诀是坐着等待,拥抱无聊。",
    "买好公司不等于好生意,一个好生意配好价格,才是伟大投资。",
]


def _render_step1_lattice() -> None:
    st.markdown("### 🧠 多元思维格栅 · 4 层结构")
    st.caption("📚 知识来源:[01_knowledge/03_投资策略与选股/03_多元思维.md](01_knowledge/03_投资策略与选股/03_多元思维.md)")

    for layer_name, models in LATTICE_LAYERS:
        with st.expander(f"**{layer_name}**", expanded=True):
            cols = st.columns(2)
            for i, (icon_name, desc) in enumerate(models):
                with cols[i % 2]:
                    st.markdown(
                        f'<div style="padding:8px 12px;background:#f5f3ff;'
                        f'border-left:3px solid #8b5cf6;border-radius:4px;margin:4px 0">'
                        f'<div style="font-weight:600;color:#4c1d95">{icon_name}</div>'
                        f'<div style="font-size:13px;color:#555;margin-top:2px">{desc}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    st.markdown("---")
    st.markdown("### 🎯 4 大核心原则")
    cols = st.columns(2)
    for i, (name, desc) in enumerate(PRINCIPLES):
        with cols[i % 2]:
            st.markdown(
                f'<div style="padding:10px 14px;background:#ede9fe;'
                f'border-radius:6px;margin:6px 0">'
                f'<div style="font-weight:700;color:#4c1d95;font-size:15px">'
                f'{i+1}. {name}</div>'
                f'<div style="font-size:13px;color:#444;margin-top:4px">{desc}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")
    st.markdown("### 💬 芒格经典语录")
    for q in QUOTES:
        st.markdown(
            f'<blockquote style="border-left:4px solid #8b5cf6;'
            f'padding:8px 14px;margin:8px 0;color:#444;background:#fafafa;'
            f'border-radius:0 4px 4px 0;font-style:italic">'
            f'"{q}"</blockquote>',
            unsafe_allow_html=True,
        )


# ─── ② 决策检查清单(交互打分)──────────────────────────────────────────

CHECKLIST_ITEMS = [
    {
        "id": "circle",
        "title": "1️⃣ 能力圈 — 我真的理解这个生意吗?",
        "questions": [
            "业务模式清晰(能用一句话解释如何赚钱)",
            "竞争优势明显(品牌/技术/成本/网络效应)",
            "优势能持续 5 年以上",
            "管理层我信任",
        ],
        "weight": 1.5,
        "data_hint": None,
    },
    {
        "id": "reverse",
        "title": "2️⃣ 反向思维 — 这家公司会怎样失败?",
        "questions": [
            "行业不在衰退,无颠覆性风险",
            "竞争对手未在蚕食市场份额",
            "管理层无频繁更换/创始人依赖过度",
            "财务无急剧恶化(负债/现金流)",
            "无政策/监管的重大风险",
        ],
        "weight": 1.5,
        "data_hint": None,
    },
    {
        "id": "multi",
        "title": "3️⃣ 多元思维 — 至少 3 个学科角度交叉验证",
        "questions": [
            "经济学:市场规模 + 增速合理",
            "心理学:产品/服务有持续需求",
            "数学:利润增长率现实(无会计技巧)",
            "生物学:公司在适应环境变化",
            "系统论:在生态系统中地位稳固",
        ],
        "weight": 1.0,
        "data_hint": None,
    },
    {
        "id": "margin",
        "title": "4️⃣ 安全边际 — 价格足够便宜吗?",
        "questions": [
            "PE 低于历史中位数 20% 以上",
            "PB 低于 1.5 倍 或 行业中位数",
            "股息率高于 3% 或 高于 10y 国债",
        ],
        "weight": 1.5,
        "data_hint": "checklist_pe_pb_dy",
    },
    {
        "id": "longterm",
        "title": "5️⃣ 长期价值 — 3 年后这个生意会更强吗?",
        "questions": [
            "营收增速未在放缓",
            "毛利/净利率趋势改善或平稳",
            "ROE/ROIC 持续 ≥ 15%",
            "市场地位相对竞争对手在改善",
        ],
        "weight": 1.2,
        "data_hint": "checklist_roe",
    },
    {
        "id": "psych",
        "title": "6️⃣ 心理陷阱 — 我是否陷入了常见偏差?(详细见④)",
        "questions": [
            "无确认偏差(主动看反面证据)",
            "无从众效应(独立思考)",
            "无近因偏差(不因最近涨而买)",
            "无沉没成本(不因之前亏而继续拿)",
        ],
        "weight": 1.0,
        "data_hint": None,
    },
    {
        "id": "moat",
        "title": "7️⃣ 护城河 — 这家公司有「城堡」吗?",
        "questions": [
            "有 ≥ 1 个明显护城河(品牌/技术/网络/成本/转换成本)",
            "护城河在加深而非弱化",
        ],
        "weight": 1.2,
        "data_hint": None,
    },
    {
        "id": "mgmt",
        "title": "8️⃣ 管理层 — 我在为谁工作?",
        "questions": [
            "诚信(无欺骗股东/监管历史)",
            "能力(过往决策明智)",
            "对股东友好(无大股东套现/薪酬合理)",
            "资本配置能力(投资/回购/分红/并购合理)",
            "长期思维(看 5 年+ 未来)",
        ],
        "weight": 1.2,
        "data_hint": None,
    },
    {
        "id": "valuation",
        "title": "9️⃣ 价格与价值 — 这是便宜货还是陷阱?",
        "questions": [
            "至少用 2 种估值方法交叉验证",
            "目标价相近(PE/PB/DCF/相对估值)",
            "PEG 合理(< 1 便宜,1-2 合理)",
        ],
        "weight": 1.2,
        "data_hint": "checklist_peg",
    },
    {
        "id": "risk",
        "title": "🔟 风险评估 — 最坏情况会怎样?",
        "questions": [
            "构建了乐观/基础/悲观 3 情景",
            "悲观情景下不会亏本(下行可控)",
            "考虑了行业衰退 50% 的极端情况",
            "考虑了政策反转的影响",
        ],
        "weight": 1.0,
        "data_hint": None,
    },
]

DECISION_RULES = [
    (4.0, "✅", "强烈买入", "#1b8a3a", "值得持仓 3-5 年"),
    (3.0, "🟢", "可以买入", "#5cb85c", "需要定期复核"),
    (2.0, "🟡", "观望", "#f0ad4e", "等待更好时机"),
    (0.0, "🔴", "PASS", "#d9534f", "不符合标准"),
]


def _verdict_from_avg(avg: float) -> tuple[str, str, str, str]:
    for threshold, icon, label, color, advice in DECISION_RULES:
        if avg >= threshold:
            return icon, label, color, advice
    return "⚪", "数据不足", "#888", ""


def _data_hint_for(hint_id: str | None, m: dict) -> str | None:
    """根据 hint_id 从 DB 拉硬指标,在清单项下方显示参考。"""
    if not hint_id or not m:
        return None
    if hint_id == "checklist_pe_pb_dy":
        pe = m.get("pe_ttm")
        pb = m.get("pb")
        dy = (m.get("dividend_yield") or 0) * 100
        parts = []
        if pe:
            parts.append(f"PE-TTM = **{pe:.1f}**")
        if pb:
            parts.append(f"PB = **{pb:.2f}**")
        if dy:
            parts.append(f"股息率 = **{dy:.2f}%**")
        return " · ".join(parts) if parts else None
    if hint_id == "checklist_roe":
        # ① 修复:lynch loader 实际写 gross_margin_self / net_margin_5y_mean,
        # 旧 key gross_margin / net_margin 恒为 None,毛利率/净利率从不显示。
        roe = (m.get("roe") or 0) * 100
        gm = (m.get("gross_margin_self") or m.get("gross_margin") or 0) * 100
        nm = (m.get("net_margin_5y_mean") or m.get("net_margin") or 0) * 100
        parts = []
        if roe:
            parts.append(f"ROE = **{roe:.1f}%**")
        if gm:
            parts.append(f"毛利率 = **{gm:.1f}%**")
        if nm:
            parts.append(f"净利率 = **{nm:.1f}%**")
        return " · ".join(parts) if parts else None
    if hint_id == "checklist_peg":
        # ① 修复:lynch loader 写 peg_lixinger(理杏仁口径),无 peg 键 → 旧值恒 None。
        peg = m.get("peg_lixinger") if m.get("peg_lixinger") is not None else m.get("peg")
        pe = m.get("pe_ttm")
        if peg:
            return f"PEG ≈ **{peg:.2f}** · PE-TTM = {pe:.1f}" if pe else f"PEG ≈ **{peg:.2f}**"
        return None
    return None


def _render_step2_checklist(ticker: str, m: dict) -> dict:
    """渲染 10 项决策清单,返回 {item_id: score(1-5)}。"""
    st.markdown("### ✅ 10 项决策检查清单 · 给每项打 1-5 分")
    st.caption("📚 知识来源:[00_芒格决策检查清单.md](01_knowledge/03_投资策略与选股/00_芒格决策检查清单.md) · 加权平均决定决策建议")

    scores: dict[str, int] = {}
    weighted_sum = 0.0
    weight_total = 0.0

    for item in CHECKLIST_ITEMS:
        with st.container(border=True):
            st.markdown(f"**{item['title']}**")

            # 数据钩子:从 DB 拉硬指标作参考
            hint = _data_hint_for(item.get("data_hint"), m)
            if hint:
                st.caption(f"📊 当前数据 — {hint}")

            # 子问题列表
            for q in item["questions"]:
                st.caption(f"• {q}")

            # 1-5 打分(slider)
            score = st.slider(
                f"评分(1=完全不符 / 3=部分符合 / 5=完全符合)",
                min_value=1, max_value=5, value=3, step=1,
                key=f"munger_{ticker}_{item['id']}",
                label_visibility="collapsed",
            )
            scores[item["id"]] = score
            weighted_sum += score * item["weight"]
            weight_total += item["weight"]

    # 加权平均 + 决策建议
    avg = weighted_sum / weight_total if weight_total > 0 else 0
    icon, label, color, advice = _verdict_from_avg(avg)

    st.markdown("---")
    st.markdown(
        f'<div style="padding:16px;border-radius:8px;background:{color}15;'
        f'border-left:5px solid {color};margin:10px 0">'
        f'<div style="font-size:14px;color:#666">📊 加权平均分</div>'
        f'<div style="font-size:32px;font-weight:700;color:{color};margin:4px 0">'
        f'{icon} {avg:.2f} / 5.0</div>'
        f'<div style="font-size:18px;color:{color};font-weight:600">{label}</div>'
        f'<div style="font-size:13px;color:#444;margin-top:6px">{advice}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    return {"scores": scores, "avg": avg, "label": label}


# ─── ③ 反向思维(失败路径分析)─────────────────────────────────────────

FAILURE_CATEGORIES = [
    {
        "id": "industry",
        "title": "📉 行业衰退 / 颠覆",
        "color": "#d9534f",
        "examples": [
            "行业总需求在萎缩(如传统媒体被互联网冲击)",
            "颠覆性技术出现(如柯达被数码相机)",
            "替代品威胁(如新能源汽车冲击燃油车)",
            "产业链上下游议价能力被夺走",
        ],
    },
    {
        "id": "competition",
        "title": "⚔️ 竞争失利",
        "color": "#fd7e14",
        "examples": [
            "护城河被新进入者侵蚀",
            "市场份额持续丢失(年度对比)",
            "毛利率被价格战压缩",
            "失去关键大客户/分销渠道",
        ],
    },
    {
        "id": "management",
        "title": "👔 管理层 / 公司治理",
        "color": "#f0ad4e",
        "examples": [
            "创始人离世/退休 — 二代接班失败",
            "管理层频繁更换 — 战略不连续",
            "财务造假 / 大股东套现 / 关联交易",
            "资本配置失误(高位并购 / 烧钱扩张)",
        ],
    },
    {
        "id": "macro",
        "title": "🌍 宏观 / 政策 / 监管",
        "color": "#6f42c1",
        "examples": [
            "政策反转(教培/游戏/医美 等)",
            "新监管出台增加合规成本",
            "关税/贸易战切断海外市场",
            "汇率/利率剧变冲击成本结构",
        ],
    },
]


def _render_step3_reverse(ticker: str, company: str) -> dict:
    """渲染反向思维 — 4 大失败路径 + 用户自填。返回 {category_id: notes}。"""
    st.markdown("### 💀 反向思维 — 这家公司会怎么死?")
    st.caption("📚 芒格:'告诉我我会死在哪里,我就永远不去那里。' — 先想清楚失败路径,再决定是否买入。")

    notes: dict[str, str] = {}
    flagged: dict[str, list[str]] = {}

    for cat in FAILURE_CATEGORIES:
        with st.container(border=True):
            st.markdown(
                f'<div style="font-weight:700;color:{cat["color"]};font-size:16px">'
                f'{cat["title"]}</div>',
                unsafe_allow_html=True,
            )
            picked: list[str] = []
            for i, ex in enumerate(cat["examples"]):
                if st.checkbox(ex, key=f"munger_rev_{ticker}_{cat['id']}_{i}"):
                    picked.append(ex)
            flagged[cat["id"]] = picked
            note = st.text_area(
                f"补充 {cat['title']} 的具体担忧(可选)",
                key=f"munger_revnote_{ticker}_{cat['id']}",
                height=68,
                placeholder="如:具体的政策文件 / 竞品名称 / 财务数据异动……",
            )
            notes[cat["id"]] = note.strip()

    # 失败信号合计
    total_flagged = sum(len(v) for v in flagged.values())
    if total_flagged >= 5:
        st.error(
            f"⚠️ 已勾选 {total_flagged} 个失败信号 — 危险信号过多,芒格规则建议 PASS",
            icon="🚨",
        )
    elif total_flagged >= 3:
        st.warning(
            f"勾选 {total_flagged} 个失败信号 — 进入观察名单,需要更高安全边际",
            icon="⚠️",
        )
    elif total_flagged >= 1:
        st.info(
            f"勾选 {total_flagged} 个失败信号 — 风险点已识别,需在决策日志中记录应对",
            icon="📌",
        )
    else:
        st.success("无明显失败路径勾选 — 但仍需保持警觉,黑天鹅永远存在", icon="✅")

    return {"flagged": flagged, "notes": notes, "total_flagged": total_flagged}


# ─── ④ 心理偏差自检 ────────────────────────────────────────────────────

BIASES = [
    ("确认偏差", "只寻找支持自己观点的证据", "主动列 3 条反面证据"),
    ("可得性偏差", "过度关注容易想起的信息", "系统性收集 5 年数据"),
    ("锚定效应", "被第一印象/初次估值过度影响", "从多个维度独立估值"),
    ("损失厌恶", "对损失的恐惧大于对收益的喜悦", "预先设定止损/卖出规则"),
    ("社会认同(从众)", "羊群效应,因别人买而买", "独立思考,问'我自己的逻辑是?'"),
    ("权威偏差", "过度信任专家/分析师", "质疑权威,要求其逻辑可验证"),
    ("激励偏差", "被利益(自己/他人)影响判断", "理解各方利益,识别动机"),
    ("禀赋效应", "对自己持有的标的估值过高", "假设自己未持有,客观重估"),
    ("沉没成本", "因已投入(亏损/时间)而继续持有", "面向未来决策,过去已沉没"),
]


def _render_step4_biases(ticker: str) -> dict:
    """渲染 9 项心理偏差自检。返回 {bias_name: bool}。"""
    st.markdown("### 🪞 9 项心理偏差自检 — 我陷入了哪些陷阱?")
    st.caption("📚 知识来源:[03_多元思维.md § 2.4](01_knowledge/03_投资策略与选股/03_多元思维.md) · 勾选=我可能陷入这个偏差")

    triggered: dict[str, bool] = {}
    for name, symptom, defense in BIASES:
        with st.container(border=True):
            col_a, col_b = st.columns([4, 1])
            with col_a:
                st.markdown(f"**{name}** · {symptom}")
                st.caption(f"🛡️ 防御:{defense}")
            with col_b:
                triggered[name] = st.checkbox(
                    "我中招了",
                    key=f"munger_bias_{ticker}_{name}",
                )

    n_triggered = sum(1 for v in triggered.values() if v)
    if n_triggered >= 3:
        st.error(
            f"⚠️ 已识别 {n_triggered} 个心理偏差 — 暂停决策,先用防御策略复盘",
            icon="🛑",
        )
    elif n_triggered >= 1:
        st.warning(
            f"识别到 {n_triggered} 个偏差 — 在决策前应用防御策略",
            icon="⚠️",
        )
    else:
        st.success("无明显偏差勾选 — 保持自省,偏差往往是无意识的", icon="✅")

    return {"triggered": triggered, "n_triggered": n_triggered}


# ─── ⑤ 决策报告导出 ────────────────────────────────────────────────────


def _find_company_dir(company: str) -> Path | None:
    """根据公司中文名找 02_companies/ 下的目录。"""
    if not COMPANIES_DIR.exists():
        return None
    # 直接精确匹配
    direct = COMPANIES_DIR / company
    if direct.exists():
        return direct
    # 否则:N_公司名 模式
    for d in COMPANIES_DIR.iterdir():
        if d.is_dir() and (d.name.endswith(f"_{company}") or company in d.name):
            return d
    return None


def _build_decision_md(*, ticker: str, company: str, m: dict,
                       checklist: dict, reverse: dict, biases: dict) -> str:
    """构建决策 markdown 报告。"""
    today = _date_cls.today().isoformat()
    pe = m.get("pe_ttm")
    pb = m.get("pb")
    roe = (m.get("roe") or 0) * 100
    dy = (m.get("dividend_yield") or 0) * 100

    lines = [
        f"# 芒格多元思维决策报告 — {company}",
        "",
        f"> 生成日期:{today} · Ticker:{ticker}",
        f"> 框架:芒格 10 项决策清单 + 反向思维 + 心理偏差自检",
        "",
        "## 一、当前估值快照",
        "",
        f"- PE-TTM:{pe:.1f}" if pe else "- PE-TTM:—",
        f"- PB:{pb:.2f}" if pb else "- PB:—",
        f"- ROE:{roe:.1f}%",
        f"- 股息率:{dy:.2f}%",
        "",
        "## 二、10 项决策清单评分",
        "",
        f"**加权平均分:{checklist['avg']:.2f} / 5.0 → {checklist['label']}**",
        "",
        "| 清单项 | 评分 |",
        "|---|---|",
    ]

    for item in CHECKLIST_ITEMS:
        score = checklist["scores"].get(item["id"], 0)
        # 去掉 emoji 数字前缀,只保留标题
        title = item["title"]
        lines.append(f"| {title} | {score} |")

    lines.extend(["", "## 三、反向思维(失败路径)", ""])

    if reverse["total_flagged"] == 0:
        lines.append("无明显失败路径勾选。")
    else:
        lines.append(f"**总计勾选 {reverse['total_flagged']} 个失败信号**")
        lines.append("")
        for cat in FAILURE_CATEGORIES:
            picked = reverse["flagged"].get(cat["id"], [])
            note = reverse["notes"].get(cat["id"], "")
            if picked or note:
                lines.append(f"### {cat['title']}")
                lines.append("")
                for p in picked:
                    lines.append(f"- ⚠️ {p}")
                if note:
                    lines.append(f"- 📝 备注:{note}")
                lines.append("")

    lines.extend(["## 四、心理偏差自检", ""])
    bias_picked = [k for k, v in biases["triggered"].items() if v]
    if not bias_picked:
        lines.append("无明显心理偏差勾选。")
    else:
        lines.append(f"**识别到 {len(bias_picked)} 个偏差,需在决策前应用防御策略:**")
        lines.append("")
        for name in bias_picked:
            for bn, sym, defense in BIASES:
                if bn == name:
                    lines.append(f"- **{bn}**({sym}) → 🛡️ {defense}")
                    break

    lines.extend(["", "## 五、综合结论", ""])
    if checklist["avg"] >= 4.0 and reverse["total_flagged"] < 3 and biases["n_triggered"] < 3:
        verdict = "✅ **强烈买入** — 清单 4.0+ / 失败信号 <3 / 偏差 <3"
    elif checklist["avg"] >= 3.0 and reverse["total_flagged"] < 5:
        verdict = "🟢 **可以买入** — 清单 3.0-4.0 / 失败信号可控"
    elif checklist["avg"] >= 2.0:
        verdict = "🟡 **观望** — 清单 2.0-3.0 / 等待更好时机"
    else:
        verdict = "🔴 **PASS** — 清单 <2.0 / 不符合芒格标准"
    lines.append(verdict)

    lines.extend([
        "",
        "---",
        "",
        f"> 决策报告由芒格多元思维 Tab 自动生成 · {today}",
        f"> 框架来源:01_knowledge/03_投资策略与选股/00_芒格决策检查清单.md + 03_多元思维.md",
    ])

    return "\n".join(lines)


def _render_step5_export(ticker: str, company: str, m: dict,
                         checklist: dict, reverse: dict, biases: dict,
                         decisions_db=None) -> None:
    st.markdown("### 📤 决策报告导出")
    st.caption(
        f"基于上面 4 个 sub-tab 的输入,生成 markdown 决策报告写入 "
        f"`02_companies/{company}/05_投资决策/`"
    )

    md = _build_decision_md(
        ticker=ticker, company=company, m=m,
        checklist=checklist, reverse=reverse, biases=biases,
    )

    with st.expander("📄 预览 markdown", expanded=False):
        st.code(md, language="markdown")

    col_a, col_b = st.columns([1, 1])
    with col_a:
        st.download_button(
            "💾 下载 markdown",
            md.encode("utf-8"),
            file_name=f"芒格决策清单_{company}_{_date_cls.today().isoformat()}.md",
            mime="text/markdown",
            width="stretch",
        )
    with col_b:
        if st.button("📁 写入公司目录(05_投资决策)", width="stretch"):
            company_dir = _find_company_dir(company)
            if company_dir is None:
                st.error(f"⚠️ 未找到 {company} 的公司目录")
            else:
                target = company_dir / "05_投资决策" / f"芒格决策清单_{_date_cls.today().isoformat()}_auto.md"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(md, encoding="utf-8")
                st.success(f"✅ 已写入 `{target.relative_to(ROOT)}`")


# ─── 主入口 ─────────────────────────────────────────────────────────────


def render(companies: list[str], selected: str, db_mtime: float,
           decisions_db=None, folder_to_ticker_fn=None) -> None:
    st.subheader("🧠 芒格多元思维 · 决策检查框架")

    # 顶部公司选择
    col_c, col_r = st.columns([4, 1])
    with col_c:
        idx = companies.index(selected) if selected in companies else 0
        company = st.selectbox(
            "公司", companies, index=idx,
            key="munger_company", label_visibility="collapsed",
        )
    with col_r:
        if st.button("🔄 重新评估", key="munger_refresh", width="stretch"):
            _metrics_cached.clear()
            st.rerun()

    # ticker 解析
    if folder_to_ticker_fn:
        f2t = folder_to_ticker_fn if isinstance(folder_to_ticker_fn, dict) else folder_to_ticker_fn
        ticker = f2t.get(company, "") if hasattr(f2t, "get") else ""
    else:
        from dashboard_helpers import _folder_to_ticker
        ticker = _folder_to_ticker(db_mtime).get(company, "")

    if not ticker:
        st.error(f"⚠️ 未找到 {company} 的 ticker 映射")
        return

    m = _metrics_cached(ticker, db_mtime)
    if m is None or "_error" in (m or {}):
        err = (m or {}).get("_error", "数据加载失败")
        st.warning(f"⚠️ {company} 数据加载提示:{err} — 仍可使用清单/反向思维/偏差自检")
        m = {}

    # 顶部 banner
    _render_banner(company, ticker, m)

    # 5 sub-tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🧠 多元思维速览",
        "✅ 决策清单(打分)",
        "💀 反向思维",
        "🪞 心理偏差自检",
        "📤 决策报告导出",
    ])

    with tab1:
        _render_step1_lattice()
    with tab2:
        checklist = _render_step2_checklist(ticker, m)
    with tab3:
        reverse = _render_step3_reverse(ticker, company)
    with tab4:
        biases = _render_step4_biases(ticker)
    with tab5:
        _render_step5_export(
            ticker, company, m, checklist, reverse, biases,
            decisions_db=decisions_db,
        )


__all__ = ["render"]
