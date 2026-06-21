"""静态行业毛利率基准(回退方案)。

profitability 表无行业聚合 metric 时,用此字典给 baseline。
数据来源:A 股近 3 年(2022-2024)行业平均毛利率,基于公开行业概况
(同花顺行业、申万指数披露平均、年报行业平均值),verified=False。

银行(招行)/保险(新华保险)毛利率指标本身不适用——返回 None,
触发 lynch_abcd_scorer 走手填路径。
"""
from __future__ import annotations


# ticker → (industry_label, median_gm_pct)
# median_gm_pct = None 表示行业不适用毛利率指标
INDUSTRY_GM_BASELINE: dict[str, tuple[str, float | None]] = {
    # 白酒
    "600519": ("白酒", 78.0),
    "000858": ("白酒", 78.0),
    # 乳制品
    "600887": ("乳制品", 30.0),
    # 食品饮料(连锁茶饮)
    "02097":  ("食品饮料(连锁)", 33.0),
    # 创新药/医药
    "600276": ("创新药", 70.0),
    # 家电整机
    "000333": ("家用电器", 24.0),
    # 家电零部件 / 汽车热管理
    "002050": ("家电零部件", 26.0),
    # 电子制造(OEM/ODM)
    "002475": ("电子制造", 12.0),
    # 光通信模块
    "300308": ("光通信模块", 28.0),
    # 汽车整车(含电池一体化)
    "002594": ("汽车制造", 17.0),
    # 锂电池
    "300750": ("锂电池", 22.0),
    # 轨交装备
    "601766": ("轨交装备", 22.0),
    # 氟化工
    "603379": ("氟化工", 18.0),
    # 银行/保险:不适用
    "600036": ("银行", None),
    "601336": ("保险", None),
}


def get_static_industry_gm(ticker: str) -> tuple[str | None, float | None]:
    """返回 (行业标签, 中位毛利率%)。

    None 中位 = 行业不适用毛利率(银行/保险)。
    未收录 ticker = (None, None)。
    """
    return INDUSTRY_GM_BASELINE.get(ticker, (None, None))
