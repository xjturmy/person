"""大师哲学速读 + 投票卡 — 把 11_大师哲学_深化补充.md 的核心条目接入 UI。

两个核心 API:
- philosophy_panel(master_key, score_pct, ticker_name) → Streamlit 渲染侧栏
- vote_card(ticker, year, db_path) → Streamlit 渲染 ACTIVE_MASTERS 一行投票

每位大师的"思想 / 决策问 / A 股调整 / 误用陷阱" 来自 11_大师哲学_深化补充.md,
为避免运行时解析 markdown 的脆弱性,直接以 Python dict 内嵌(版本随文档同步)。

启用范围:
- MASTERS:7 大师全量元数据(供其他模块如方法论速读复用,不要删)
- ACTIVE_MASTERS:投票卡当前启用的大师子集 — 改这里就能切换投票阵容
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[3]
KNOWLEDGE_DOC = ROOT / "01_knowledge" / "03_投资策略与选股" / "11_大师哲学_深化补充.md"


# ───── 7 大师哲学卡 ──────────────────────────────────────────────────────

MASTERS: dict[str, dict] = {
    "buffett": {
        "name_cn": "巴菲特",
        "name_en": "Warren Buffett",
        "color": "#1b8a3a",  # 绿
        "thesis": "用合理价格买伟大公司,资本配置 + 护城河耐久性 决定长期复合收益。",
        "key_question": "十年后竞争对手能否抢走它的客户?能否用一句话说清未来十年怎么赚钱?",
        "metric_cue": "看 Owner Earnings 增速 ≥ 10%/y、ROE 连续 10 年 ≥ 15%、长期 ROIC 高于资金成本",
        "pitfall": "把'长期持有'等同于'永不卖出',忽视护城河可能被科技颠覆(柯达、诺基亚)",
        "a_share_tweak": "护城河叙事容易被'政策红利'伪装(白酒/新能源),需引入'政策依赖度'维度",
        "anchor": "1️⃣-warren-buffett巴菲特",
    },
    "graham": {
        "name_cn": "格雷厄姆",
        "name_en": "Benjamin Graham",
        "color": "#0d6efd",  # 蓝
        "thesis": "安全边际是世界观,不是估值技巧 — 用价格 < 价值的差额对抗未来不可知。",
        "key_question": "现价是否足够低,即使我对企业判断错了 30%,也不会亏本?",
        "metric_cue": "P/E ≤ 15 + P/B ≤ 1.5 + 流动比率 ≥ 2 + 长期连续派息(10 年+)",
        "pitfall": "Graham Number 滥用为唯一估值器 — 对轻资产/科技公司严重低估(Amazon)",
        "a_share_tweak": "派息 20 年条件几乎无公司满足,放宽为 10 年;ST/退市预警股需排除",
        "anchor": "2️⃣-benjamin-graham格雷厄姆",
    },
    "lynch": {
        "name_cn": "彼得林奇",
        "name_en": "Peter Lynch",
        "color": "#f0ad4e",  # 黄
        "thesis": "散户对生活产品的观察,比券商分析师早 6-12 个月发现拐点 — 但'know'不等于'用过'。",
        "key_question": "这家公司属于六类中的哪类(慢/稳/快/周期/反转/资产)?能否对 11 岁孩子在 1 分钟内说清?",
        "metric_cue": "PEG < 1 合理,< 0.5 便宜;Stalwart 涨 30-50% 就要轮动",
        "pitfall": "在周期股上误用低 P/E(P/E 5 时往往离顶很近);把 stalwart 当 fast grower 死守",
        "a_share_tweak": "'散户先于券商发现' 在 A 股需谨慎(散户占比高,信息已被定价);PEG 需配合业绩兑现度过滤",
        "anchor": "3️⃣-peter-lynch彼得林奇",
    },
    "piotroski": {
        "name_cn": "皮奥乔斯基",
        "name_en": "Joseph Piotroski",
        "color": "#6f42c1",  # 紫
        "thesis": "在便宜股池(高 BM)里用 9 项财报信号筛'质量改善方向'— 纯机械,不靠主观判断。",
        "key_question": "盈利在改善吗?现金流能覆盖净利润吗?杠杆在降吗?",
        "metric_cue": "F-Score ≥ 8 做多 / ≤ 1 做空;9 项以变化量(ΔROA/ΔGM/ΔAT)为主",
        "pitfall": "脱离 BM 前提应用到成长股 — alpha 来源是'便宜+质量改善',不是单纯质量",
        "a_share_tweak": "A 股做空受限 → 短腿(空高 BM 低 F-Score 股)效应 > 长腿;高情绪期效果更强",
        "anchor": "4️⃣-joseph-piotroski皮奥乔斯基",
    },
    "altman": {
        "name_cn": "阿特曼",
        "name_en": "Edward Altman",
        "color": "#d9534f",  # 红
        "thesis": "破产不是黑箱事件,5 个公开财务比率的线性组合就能在 1-2 年前预测。",
        "key_question": "这家公司未来 2 年内破产的概率高不高?是不是其他大师方法的'安全开关'?",
        "metric_cue": "Z > 2.99 安全 / 1.81-2.99 灰色 / < 1.81 高破产风险;非制造业用 Z''",
        "pitfall": "应用到金融机构(银行/保险/地产)— Altman 本人警告,这些行业表外资产多,Z 完全不适用",
        "a_share_tweak": "A 股 ST 公司多为非制造业服务业 → 推荐用 Z'' 而非原始 Z",
        "anchor": "5️⃣-edward-altman阿特曼",
    },
    "greenblatt": {
        "name_cn": "格林布拉特",
        "name_en": "Joel Greenblatt",
        "color": "#20c997",  # 青
        "thesis": "便宜(高 EBIT/EV)+ 优质(高 ROC)两个简单指标排序就能跑赢 80% 主动基金 — 前提是 5+ 年纪律执行。",
        "key_question": "这家公司在全市场的 EBIT/EV 排名 + ROC 排名 合计排第几?是否在前 30?",
        "metric_cue": "EBIT/EV 高 + ROC 高 → 合计排名前 30;持有满 1 年再换",
        "pitfall": "半途而废 — Magic Formula 在 3 年内可能跑输,只在 5+ 年才稳定跑赢",
        "a_share_tweak": "EBIT 需剔除非经常性损益和政府补助;排除范围扩大到军工/央企集成商等非市场化行业",
        "anchor": "6️⃣-joel-greenblatt格林布拉特",
    },
    "damodaran": {
        "name_cn": "达摩达兰",
        "name_en": "Aswath Damodaran",
        "color": "#fd7e14",  # 橙
        "thesis": "估值 = 故事 + 数字。纯数字模型和纯叙事都不可靠 — 必须用故事约束数字假设,再让数字反过来检验故事。",
        "key_question": "这家公司未来 10 年最合理的故事是什么?故事映射出的隐含市场份额/利润率是否可能?",
        "metric_cue": "DCF FCFF 5-10 年明确预测期 + 终值 g ≤ 长期无风险利率;中国 ERP ≈ 6.07%",
        "pitfall": "终值假设过激(g 超过 GDP)→ TV 占总价值 80%+ → 估值变成对终值的赌博",
        "a_share_tweak": "用 Damodaran 中国 ERP 6.07% 作基准;国企 WACC 加'治理风险溢价';政策密集行业故事中显式建模'政策反转'分支",
        "anchor": "7️⃣-aswath-damodaran达摩达兰",
    },
}


# ───── 投票卡启用阵容(改这里切换;其他模块仍可用 MASTERS 全量) ─────
# 当前:格雷厄姆(深度价值)+ 彼得林奇(GARP)
# 顺序按价值 → 成长 的投资风格谱系
ACTIVE_MASTERS: list[str] = ["graham", "lynch"]


def _verdict(score_pct: float | None) -> tuple[str, str, str]:
    """根据归一化得分返回 (徽章, 决策词, 颜色)。"""
    if score_pct is None:
        return "⚪", "数据不足", "#888"
    if score_pct >= 75:
        return "✅", "买入", "#1b8a3a"
    if score_pct >= 60:
        return "🟢", "倾向买", "#5cb85c"
    if score_pct >= 45:
        return "🟡", "观望", "#f0ad4e"
    if score_pct >= 30:
        return "🟠", "倾向卖", "#fd7e14"
    return "🔴", "卖出", "#d9534f"


def _verdict_reason(master_key: str, score_pct: float | None,
                    valid: int = 0, total: int = 0) -> str:
    """单句结论文案,贴合该大师的语气 + 评分。"""
    m = MASTERS[master_key]
    if score_pct is None or total == 0:
        return f"{m['name_cn']}:{total} 项规则但无有效数据"
    n_pass = round(score_pct / 100 * total)
    if score_pct >= 75:
        flavors = {
            "buffett":    f"护城河 / ROE 等通过 {n_pass}/{total},合规候选",
            "graham":     f"PE/PB/分红等通过 {n_pass}/{total},安全边际充足",
            "lynch":      f"PEG / 增长一致性通过 {n_pass}/{total},GARP 候选",
            "piotroski":  f"F-Score {n_pass}/{total},质量改善信号强",
            "altman":     f"Z 评估 {n_pass}/{total},财务安全",
            "greenblatt": f"EBIT/EV + ROC 通过 {n_pass}/{total},Magic 候选",
            "damodaran":  f"DCF 关键假设 {n_pass}/{total},合理或低估",
        }
    elif score_pct >= 60:
        flavors = {k: f"通过 {n_pass}/{total},基本合格但有瑕疵" for k in MASTERS}
    elif score_pct >= 45:
        flavors = {k: f"仅通过 {n_pass}/{total},部分维度未达标" for k in MASTERS}
    else:
        flavors = {
            "buffett":    f"通过 {n_pass}/{total},护城河/ROE 不足",
            "graham":     f"通过 {n_pass}/{total},估值不够便宜",
            "lynch":      f"通过 {n_pass}/{total},PEG/增长一致性差",
            "piotroski":  f"F-Score {n_pass}/{total},质量在恶化",
            "altman":     f"Z 评估 {n_pass}/{total},财务有压力",
            "greenblatt": f"通过 {n_pass}/{total},Magic 排名靠后",
            "damodaran":  f"通过 {n_pass}/{total},DCF 高估或假设失败",
        }
    return flavors.get(master_key, f"通过 {n_pass}/{total}")


# ───── UI 1:大师投票卡(7 大师一行结论)─────────────────────────────────

def vote_card(ticker: str, year: int = 2024, *, st_module=None) -> dict:
    """渲染 ACTIVE_MASTERS 投票一览。返回 {master: (score_pct, valid, total)} 用于上层聚合。

    依赖:multi_master.py 的 list_executable_yamls + run_one。
    启用范围由模块顶部 ACTIVE_MASTERS 控制(默认 graham/buffett/lynch)。
    """
    import streamlit as st
    s = st_module or st

    try:
        import sys
        sd = ROOT / ".tools" / "score"
        if str(sd) not in sys.path:
            sys.path.insert(0, str(sd))
        import multi_master as mm
    except Exception as e:
        s.warning(f"multi_master 不可用:{e}")
        return {}

    yamls = mm.list_executable_yamls()
    active_set = set(ACTIVE_MASTERS)
    results: dict[str, tuple] = {}
    for yp in yamls:
        master = yp.stem
        if master not in active_set:
            continue  # 仅跑启用阵容,避开非启用 + 行业适配版(_bank/_insurance)
        try:
            res = mm.run_one(yp, ticker, year)
        except Exception:
            res = None
        if res is None:
            results[master] = (None, 0, 0)
        else:
            sc, valid, total = res
            pct = (sc / total * 100.0) if total > 0 else None
            results[master] = (pct, valid, total)

    # 排序:按 ACTIVE_MASTERS 列表顺序
    ordered = [(k, results.get(k, (None, 0, 0))) for k in ACTIVE_MASTERS]

    n_total = len(ACTIVE_MASTERS)
    # 渲染:卡片标题 + N 行
    with s.container(border=True):
        s.markdown(f"##### 🗳️ {n_total} 大师投票 · {ticker} · 年份 {year}")
        n_buy = sum(1 for _, (p, _, _) in ordered if p is not None and p >= 60)
        n_watch = sum(1 for _, (p, _, _) in ordered if p is not None and 45 <= p < 60)
        n_sell = sum(1 for _, (p, _, _) in ordered if p is not None and p < 45)
        n_na = sum(1 for _, (p, _, _) in ordered if p is None)
        s.caption(f"📊 {n_buy} 倾向买 / {n_watch} 观望 / {n_sell} 倾向卖 / {n_na} 数据不足")

        for master_key, (pct, valid, total) in ordered:
            m = MASTERS[master_key]
            badge, verdict, color = _verdict(pct)
            reason = _verdict_reason(master_key, pct, valid, total)
            score_str = f"{pct:.0f}/100" if pct is not None else "—"
            s.markdown(
                f"<div style='display:flex;align-items:center;padding:6px 0;border-bottom:1px solid #f0f0f0'>"
                f"<div style='flex:0 0 90px;font-weight:600;color:{m['color']}'>"
                f"{m['name_cn']}</div>"
                f"<div style='flex:0 0 60px;text-align:center'>{badge}</div>"
                f"<div style='flex:0 0 80px;color:{color};font-weight:600'>{verdict}</div>"
                f"<div style='flex:0 0 80px;text-align:right;color:#888;font-size:13px'>{score_str}</div>"
                f"<div style='flex:1;color:#444;font-size:13px;padding-left:14px'>{reason}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    return results


# ───── UI 2:哲学速读侧栏(单大师深度展开)──────────────────────────────

def philosophy_panel(master_key: str, *, ticker: str = "",
                     vote: tuple | None = None, st_module=None) -> None:
    """渲染单大师的哲学速读卡(用于 L3 个股页右侧 / Tab 切换内容)。

    Args:
        master_key: 'buffett' / 'graham' / ... 7 个之一
        ticker: 当前公司 ticker(用于个性化展示标题)
        vote: (score_pct, valid, total),来自 vote_card 输出 — 用于把"该公司当前评分"嵌入侧栏
    """
    import streamlit as st
    s = st_module or st
    if master_key not in MASTERS:
        s.warning(f"未知大师:{master_key}")
        return
    m = MASTERS[master_key]

    with s.container(border=True):
        s.markdown(
            f"<div style='border-left:4px solid {m['color']};padding-left:12px;margin-bottom:8px'>"
            f"<div style='font-size:18px;font-weight:600;color:{m['color']}'>💡 {m['name_cn']} 视角</div>"
            f"<div style='font-size:11px;color:#888'>{m['name_en']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # 当前公司评分(若提供)
        if vote is not None:
            pct, valid, total = vote
            badge, verdict, color = _verdict(pct)
            reason = _verdict_reason(master_key, pct, valid, total)
            score_str = f"{pct:.0f}/100" if pct is not None else "—"
            head = f"{ticker or '此公司'}" if ticker else "此公司"
            s.markdown(
                f"<div style='background:#f8f9fa;border-radius:6px;padding:8px 12px;margin-bottom:10px'>"
                f"<span style='color:#888;font-size:12px'>对 {head} 的判断 · </span>"
                f"<span style='font-weight:600;color:{color}'>{badge} {verdict} · {score_str}</span>"
                f"<div style='color:#555;font-size:12px;margin-top:2px'>{reason}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # 4 段哲学速读
        s.markdown(f"**🎯 一句话**\n\n{m['thesis']}")
        s.markdown(f"**🔍 关键问题**\n\n{m['key_question']}")
        s.caption(f"📐 落地指标:{m['metric_cue']}")
        s.warning(f"⚠️ 常见误用:{m['pitfall']}")
        s.info(f"🇨🇳 A 股调整:{m['a_share_tweak']}")

        # 跳转完整文档
        if KNOWLEDGE_DOC.exists():
            try:
                rel = KNOWLEDGE_DOC.relative_to(ROOT)
                s.caption(f"📖 [完整哲学 → {rel.name}](/{rel})")
            except Exception:
                s.caption("📖 完整哲学:01_knowledge/03_投资策略与选股/11_大师哲学_深化补充.md")


def philosophy_tabs(ticker: str = "", year: int = 2024, *,
                    votes: dict | None = None, st_module=None) -> None:
    """渲染 ACTIVE_MASTERS Tab 切换的完整哲学速读区。

    建议接入位置:L3 个股页 大师矩阵 之后,作为'解读层'。
    """
    import streamlit as st
    s = st_module or st
    tab_labels = [MASTERS[k]["name_cn"] for k in ACTIVE_MASTERS]
    tabs = s.tabs(tab_labels)
    for tab, key in zip(tabs, ACTIVE_MASTERS):
        with tab:
            v = (votes or {}).get(key)
            philosophy_panel(key, ticker=ticker, vote=v, st_module=st_module)
