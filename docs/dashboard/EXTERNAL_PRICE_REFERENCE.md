# 外部价格参考层

## 定位

外部目标价不替代内部合理价,只用于校验:

- 内部合理价:作为买入线、加仓线、卖出线的主锚。
- Wind/券商目标价:作为市场一致预期和乐观/悲观偏差检查。
- 条件单:只有当内部估值与外部参考方向一致时,才提高执行信心。

## 数据入口

优先级:

1. `.config/external_price_refs.csv`:手工导入 Wind/Choice/券商 App 的一致目标价。
2. `02_companies/*/04_券商分析/02_评级与目标价.csv`:Tushare 或手工整理的券商目标价。

`external_price_refs.csv` 字段:

| 字段 | 含义 |
|---|---|
| as_of | 数据日期 |
| ticker | 股票代码 |
| name | 标的名称 |
| source | Wind / Choice / broker / manual |
| current_price | 外部数据截图或导出时的当前价 |
| target_mid | 一致目标价或目标价均值 |
| target_low | 目标价低值 |
| target_high | 目标价高值 |
| coverage | 覆盖机构数 |
| note | 备注 |

## 审计规则

| 内外差异 | 结论 | 动作 |
|---|---|---|
| `abs(外部/内部-1) <= 10%` | 内外基本一致 | 按原条件单纪律执行 |
| `外部/内部-1 > 10%` | 外部更乐观 | 复核增长假设,不直接抬高买入线 |
| `外部/内部-1 < -10%` | 外部更谨慎 | 收紧加仓条件,复核内部估值是否过度乐观 |

## 日常命令

```bash
cd /Users/gongyong/Desktop/Projects/preson
.venv/bin/python .tools/portfolio/external_price_audit.py
```

输出:

- `01_knowledge/05_实战案例与持仓/持仓统计与复盘/YYYY-MM-DD_外部价格参考审计.md`
- `01_knowledge/05_实战案例与持仓/持仓统计与复盘/YYYY-MM-DD_外部价格参考审计.csv`
