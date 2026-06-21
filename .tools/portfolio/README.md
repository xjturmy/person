# portfolio — 持仓配置 + 再平衡引擎

> 维度 4 任务 4.1 — 机器可读的投资组合,服务于评分引擎、月度复盘、Dashboard
>
> 创建:2026-05-03(step-04)

## 文件清单

| 文件 | 用途 |
|------|------|
| [portfolio.yaml](portfolio.yaml) | 持仓 + 目标权重 + 再平衡规则(YAML 单一真相) |
| [loader.py](loader.py) | YAML → Python dataclass + 计算 helper |
| [report.py](report.py) | 跑一份带 F-Score + 估值分位 + 再平衡提示的快照报告 |

## 快速开始

```bash
# 跑当前报告(默认 F-Score 用 2024 年报)
python3 .tools/portfolio/report.py

# 切到 2023 年报对比
python3 .tools/portfolio/report.py --year 2023
```

## 编辑持仓

打开 [portfolio.yaml](portfolio.yaml),按需:

1. 把 `_meta.status: demo` 改为 `live`(代表已生效)
2. 把要建仓的公司 `status: watch` 改为 `active`,填上 `shares` / `cost_basis` / `first_buy_date`
3. 调整 `target_weight` 反映目标配置
4. `account.total_capital` 填实际总资本
5. `rebalance.*` 规则按风险偏好调整

## Python 集成

```python
from portfolio.loader import load_portfolio

p = load_portfolio()
print(f"在仓 {len(p.active())} 家,观察 {len(p.watch())} 家")

# 实际权重 + 偏离度
weights = p.actual_weights(prices={"600519": 1612.0, ...})
deviations = p.deviations(prices={...})

# 再平衡提示
alerts = p.rebalance_alerts(
    prices={...},
    scores={"600519": 7, "000333": 5, ...},  # F-Score
    valuation_pct={"600519": 0.094, ...},     # 0-1
)
```

## 再平衡规则(默认值)

| 规则 | 阈值 | 触发动作 |
|------|------|---------|
| 单一持仓权重上限 | 20% | ⚠️ 减仓 |
| 实际偏离目标权重 | ±5pp | 📊 再平衡 |
| F-Score 跌破 | < 4 | 🔴 清仓评估 |
| PE-TTM 分位 | > 85% | 🔥 减仓评估 |
| PE-TTM 分位 | < 15% | 💰 加仓评估 |
| 复盘节奏 | 30 天 | 月度复盘(配合 4.3) |

## 与其他模块联动

- **评分引擎**(.tools/score/):report.py 通过 `engine.run_score()` 拉 F-Score
- **DuckDB**(data/preson.duckdb):估值分位直接 SQL 查 valuation 表
- **Dashboard**(.tools/dashboard/):方向 B 实施时 import `loader` 显示持仓 + 偏离度 + 雷达图
- **月度复盘**(任务 4.3,待启动):复用 report.py 输出 + 加上当月业绩归因
