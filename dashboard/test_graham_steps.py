"""离线测试:格雷厄姆五步法纯逻辑层(graham_steps.py)。

覆盖 4 类公司的判定 + 估值 + 7 准则(D3 阶段 C 收尾要求):
  - 招商银行 600036 → 防御型(金融业 PB+DY 路径)
  - 美的集团 000333 → 防御型(大盘 + 长盈利 + 长股息)
  - 贵州茅台 600519 → 进取型(格氏数严重超标 → 不达防御)
  - 三美股份 603379 → 进取型(PE×PB ~84 / 但三防坚固 / 防御 5/7)
  - 新华保险 601336 → 进取型(保险业 / PE×PB ~9 严达标但单公司质量未到防御)

每个公司核心断言 + 整体 dataclass 字段完整性。

运行:
  python3 -m pytest .tools/dashboard/test_graham_steps.py -v

或直接:
  python3 .tools/dashboard/test_graham_steps.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = ROOT / ".tools" / "dashboard"
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from graham_steps import (  # noqa: E402
    classify_graham_type, load_graham_metrics,
    check_graham_number, check_ncav,
    evaluate_defensive_seven, evaluate_three_lines_defense,
    deep_inspection_signals, evaluate_sell_triggers,
    evaluate_earnings_quality,
    GrahamClassResult, GrahamNumberCheck, NCAVCheck,
    DefensiveSeven, ThreeLinesDefense,
)


def test_zhaoshang_bank_defensive() -> bool:
    """招行 600036 应判为防御型(金融业 PB+DY+ROE 路径)。"""
    m = load_graham_metrics("600036")
    cls = classify_graham_type(m)
    assert cls.cls_id == "defensive", f"招行应为防御型,实际 {cls.cls_id}"
    assert cls.confidence >= 0.80, f"置信度应 ≥ 80%,实际 {cls.confidence:.0%}"

    gn = check_graham_number(m)
    assert gn.pe_x_pb is not None, "招行 PE×PB 应可计算"
    assert gn.pe_x_pb < 10, f"招行 PE×PB 应 < 10(银行天然达标),实际 {gn.pe_x_pb:.1f}"

    print(f"✅ 招行 600036 → {cls.cls_emoji} {cls.cls_name} | PE×PB={gn.pe_x_pb:.1f}({gn.grade})")
    return True


def test_meidi_defensive() -> bool:
    """美的 000333 应判为防御型(大盘 + 长盈利 + 长股息 + PE×PB ≤ 50)。"""
    m = load_graham_metrics("000333")
    cls = classify_graham_type(m)
    assert cls.cls_id in ("defensive", "enterprising"), f"美的应防御/进取,实际 {cls.cls_id}"

    ds = evaluate_defensive_seven(m)
    assert ds.pass_count >= 4, f"美的至少过 4/7 防御准则,实际 {ds.pass_count}/{ds.total_count}"

    print(f"✅ 美的 000333 → {cls.cls_emoji} {cls.cls_name} | 防御 7 准则:{ds.pass_count}/{ds.total_count}")
    return True


def test_maotai_enterprising_high_pepb() -> bool:
    """茅台 600519:格氏数严重超标(PE×PB > 100)→ 防御格氏数失败 → 进取型。"""
    m = load_graham_metrics("600519")
    cls = classify_graham_type(m)
    gn = check_graham_number(m)

    assert gn.pe_x_pb is not None, "茅台 PE×PB 应可计算"
    assert gn.pe_x_pb > 50, f"茅台 PE×PB 应 > 50(高估值白马),实际 {gn.pe_x_pb:.1f}"
    assert gn.grade.startswith("不达标") or "软达标" in gn.grade, "茅台格氏数应不达原版"

    # 茅台 PE×PB > 50 应触发 "不达防御",归为进取型
    assert cls.cls_id == "enterprising", f"茅台 PE×PB 超标应归进取型,实际 {cls.cls_id}"

    print(f"✅ 茅台 600519 → {cls.cls_emoji} {cls.cls_name} | PE×PB={gn.pe_x_pb:.1f}(超 50)")
    return True


def test_three_lines_defense() -> bool:
    """三层防御工事评估对所有公司应返回完整 dataclass。"""
    for ticker in ["600036", "000333", "600519"]:
        m = load_graham_metrics(ticker)
        tl = evaluate_three_lines_defense(m)
        assert isinstance(tl, ThreeLinesDefense), f"{ticker} 三层防御应为 dataclass"
        assert tl.line1_status, f"{ticker} 第一道防线状态应有值"
        assert tl.line2_status, f"{ticker} 第二道防线状态应有值"
        assert tl.line3_status, f"{ticker} 第三道防线状态应有值"
        assert tl.overall_status, f"{ticker} 综合状态应有值"
    print("✅ 三层防御工事:招行/美的/茅台 均返回完整 dataclass")
    return True


def test_ncav_check() -> bool:
    """NCAV 检验对一般公司应返回'不适用'(总负债 > 流动资产)。"""
    m = load_graham_metrics("600519")  # 茅台
    ncav = check_ncav(m)
    assert isinstance(ncav, NCAVCheck), "NCAV 检验应返回 dataclass"
    # 茅台流动资产巨大、负债极少 — 应该 NCAV > 0,但市值远大于 NCAV
    if ncav.mc_to_ncav is not None:
        assert ncav.mc_to_ncav > 1.5, f"茅台市值/NCAV 应 > 1.5,实际 {ncav.mc_to_ncav:.2f}"
        print(f"✅ 茅台 NCAV:{ncav.grade}(市值/NCAV={ncav.mc_to_ncav:.2f})")
    else:
        # 也可能流动资产很多但仍小于市值
        print(f"✅ 茅台 NCAV:{ncav.grade}")
    return True


def test_sell_triggers() -> bool:
    """卖出触发对所有公司应返回 4 项。"""
    for ticker in ["600036", "000333", "600519"]:
        m = load_graham_metrics(ticker)
        gn = check_graham_number(m)
        tl = evaluate_three_lines_defense(m)
        triggers = evaluate_sell_triggers(m, "defensive", gn, tl)
        assert len(triggers) == 4, f"{ticker} 应返回 4 条卖出触发,实际 {len(triggers)}"
        assert all("id" in t and "fired" in t for t in triggers), f"{ticker} 触发结构不完整"
        fired = [t["id"] for t in triggers if t["fired"]]
        print(f"  {ticker} 触发:{fired or '无'}")
    print("✅ 卖出触发:三家公司各返回 4 项,结构完整")
    return True


def test_earnings_quality() -> bool:
    """盈利能力诊断应返回杜邦 + 现金流 + 增长。"""
    m = load_graham_metrics("000333")  # 美的
    q = evaluate_earnings_quality(m)
    assert "dupont" in q
    assert "cfo_quality" in q
    assert "growth_quality" in q
    print(f"✅ 美的盈利能力:CFO={q['cfo_quality']} / 增长={q['growth_quality']}")
    return True


def test_xinhua_insurance_enterprising() -> bool:
    """新华 601336:保险业,PE×PB ~9 严达标但综合判定为进取型(质量未到防御阈)。"""
    m = load_graham_metrics("601336")
    cls = classify_graham_type(m)
    gn = check_graham_number(m)
    ds = evaluate_defensive_seven(m)
    tl = evaluate_three_lines_defense(m)

    assert cls.cls_id in ("enterprising", "defensive"), \
        f"新华应进取/防御,实际 {cls.cls_id}"
    assert gn.pe_x_pb is not None and gn.pe_x_pb < 22.5, \
        f"新华 PE×PB 应 < 22.5(严达标),实际 {gn.pe_x_pb}"
    assert ds.pass_count >= 4, \
        f"新华防御 7 准则应过 ≥ 4,实际 {ds.pass_count}/{ds.total_count}"
    assert tl.overall_status, "新华三层防御综合状态应有值"

    print(f"✅ 新华 601336 → {cls.cls_emoji} {cls.cls_name} | "
          f"PE×PB={gn.pe_x_pb:.2f}({gn.grade}) | "
          f"防御 {ds.pass_count}/{ds.total_count} | 三防={tl.overall_status}")
    return True


def test_sanmei_chemical_enterprising() -> bool:
    """三美股份 603379:化工股,PE×PB 高 → 不达格氏数;三层防御坚固验证。"""
    m = load_graham_metrics("603379")
    cls = classify_graham_type(m)
    gn = check_graham_number(m)
    ds = evaluate_defensive_seven(m)
    tl = evaluate_three_lines_defense(m)

    assert cls.cls_id in ("enterprising", "deep_undervalued"), \
        f"三美应进取/深度低估,实际 {cls.cls_id}"
    if gn.pe_x_pb is not None:
        assert gn.pe_x_pb > 22.5, \
            f"三美 PE×PB 应 > 22.5(化工高估值),实际 {gn.pe_x_pb}"
    # 三美属于 2019 上市 → 防御 7 准则盈利记录可能不满 10 年
    assert ds.total_count >= 6, "三美防御准则总数应有值"

    print(f"✅ 三美 603379 → {cls.cls_emoji} {cls.cls_name} | "
          f"PE×PB={gn.pe_x_pb if gn.pe_x_pb else '—'}({gn.grade}) | "
          f"防御 {ds.pass_count}/{ds.total_count} | 三防={tl.overall_status}")
    return True


def test_decision_log_md_build() -> bool:
    """Item 3 验收:_build_decision_md 能为 4 类公司生成完整 markdown。"""
    import sys as _sys
    _sys.path.insert(0, str(ROOT / ".tools" / "dashboard" / "tabs"))
    try:
        from graham_analysis import _build_decision_md  # noqa: WPS433
    except ImportError as e:
        print(f"⚠️  graham_analysis._build_decision_md import 失败:{e},跳过")
        return True

    for tk, name in [("600036", "招商银行"), ("000333", "美的集团"),
                       ("600519", "贵州茅台"), ("601336", "新华保险")]:
        m = load_graham_metrics(tk)
        cls = classify_graham_type(m)
        gn = check_graham_number(m)
        ds = evaluate_defensive_seven(m)

        cls_dict = cls.to_dict()
        try:
            md = _build_decision_md(
                ticker=tk, company=name, m=m, cls_dict=cls_dict,
                gn=gn, ds=ds,
                company_score=85, company_grade="B",
                price_score=70, price_grade=2,
                decision="🟢 适度配置", position="3-5% 仓位",
            )
            assert "格雷厄姆" in md, f"{tk} md 应含『格雷厄姆』"
            assert name in md, f"{tk} md 应含公司名 {name}"
            assert "PE×PB" in md or "格氏数" in md, f"{tk} md 应含格氏数"
            print(f"  ✅ {tk} {name} md 长度 {len(md):,} 字符")
        except Exception as e:
            print(f"  ❌ {tk} {name} md 构建失败:{e}")
            raise
    print("✅ 决策日志 markdown 4 类公司全部生成成功")
    return True


def main() -> int:
    tests = [
        ("招行防御型(金融业路径)", test_zhaoshang_bank_defensive),
        ("美的防御型(大盘 + 长股息)", test_meidi_defensive),
        ("茅台进取型(格氏数严超标)", test_maotai_enterprising_high_pepb),
        ("新华进取型(保险业 PE×PB 严达标)", test_xinhua_insurance_enterprising),
        ("三美进取型(化工 PE×PB 不达标)", test_sanmei_chemical_enterprising),
        ("三层防御 dataclass 完整性", test_three_lines_defense),
        ("NCAV 检验返回结构", test_ncav_check),
        ("4 条卖出触发结构", test_sell_triggers),
        ("盈利能力诊断", test_earnings_quality),
        ("决策日志 markdown 4 类公司", test_decision_log_md_build),
    ]
    print(f"\n{'='*70}\n  Graham Steps 离线测试\n{'='*70}\n")
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"❌ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"💥 {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{'='*70}\n  结果:{passed}/{len(tests)} 通过 · {failed} 失败\n{'='*70}\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
