# Rules YAML 统一格式说明

> 为 6 位大师评分规则定义的统一 schema。
> 配套 `score.py` 引擎（待实现）按此格式解析并执行。

---

## 📐 顶层结构

```yaml
master: <英文标识，如 buffett / piotroski>
master_cn: <中文译名>
method: <方法名，如 Owner Earnings / F-Score>
score_type: <binary | continuous | rank | composite>
max_score: <最高分>
threshold:
  excellent: <优秀阈值>
  good: <合格阈值>
  warning: <警戒阈值>
exclude_industries: [<不适用行业列表>]
rules:
  - id: <规则唯一 ID>
    name: <规则名>
    formula: <SQL/Python 表达式>
    weight: <权重>
    pass_condition: <通过条件>
    score_if_pass: <满足时得分>
    score_if_fail: <不满足时得分>
    data_source: <DuckDB 表/列>
    notes: <备注，A 股调整等>
```

---

## 🏷️ score_type 取值

| 类型 | 含义 | 示例 |
|------|------|------|
| `binary` | 0/1 评分（满足或不满足） | Piotroski 9 项 |
| `continuous` | 连续值（如 Z 值） | Altman Z-Score |
| `rank` | 排名（全市场比较） | Greenblatt 双 rank |
| `composite` | 综合（多维度加权） | Buffett 5 项门槛 |

---

## 🔧 公式表达式约定

- 字段引用 DuckDB 表名：`valuation.pe_ttm`、`profitability.roe`
- 同比函数：`yoy(metric)` → 当年值 - 去年值
- 滚动函数：`rolling_avg(metric, n)` → n 年均值
- 排名函数：`market_rank(metric, desc=True)` → 全市场排名

---

## 🇨🇳 行业适配机制

每条规则可附加 `industry_overrides`：

```yaml
- id: f5_leverage
  formula: yoy(ltd_ratio) < 0
  industry_overrides:
    银行:
      formula: yoy(cet1_ratio) > 0    # 银行用 CET1 替代
    保险:
      formula: yoy(solvency_ratio) > 0
```

---

## 🚦 引擎执行流程（参考实现）

```python
def run_score(ticker: str, rule_file: str) -> dict:
    rules = yaml.safe_load(open(rule_file))
    industry = get_industry(ticker)
    if industry in rules.get('exclude_industries', []):
        return {'skip': True, 'reason': f'{industry} 不适用'}

    total = 0
    detail = []
    for rule in rules['rules']:
        # 行业覆盖
        if industry in rule.get('industry_overrides', {}):
            rule = {**rule, **rule['industry_overrides'][industry]}
        # 评估
        passed = eval_formula(rule['formula'], ticker)
        score = rule['score_if_pass'] if passed else rule['score_if_fail']
        total += score * rule.get('weight', 1)
        detail.append({'rule': rule['id'], 'passed': passed, 'score': score})

    return {
        'master': rules['master'],
        'total_score': total,
        'max_score': rules['max_score'],
        'rating': classify(total, rules['threshold']),
        'detail': detail,
    }
```

---

## 📚 文件清单

| 文件 | 大师 | 知识文档 |
|------|------|---------|
| `buffett.yaml` | 巴菲特 | [06_价值确认法.md](../../01_knowledge/03_投资策略与选股/06_价值确认法.md) |
| `piotroski.yaml` | Piotroski | [07_量化体检法.md](../../01_knowledge/03_投资策略与选股/07_量化体检法.md) |
| `altman.yaml` | Altman | [08_破产预警法.md](../../01_knowledge/03_投资策略与选股/08_破产预警法.md) |
| `greenblatt.yaml` | Greenblatt | [09_神奇公式法.md](../../01_knowledge/03_投资策略与选股/09_神奇公式法.md) |
| `damodaran.yaml` | Damodaran | [10_DCF估值法.md](../../01_knowledge/03_投资策略与选股/10_DCF估值法.md) |
| `graham.yaml` | 格雷厄姆 | [01_价值投资法/](../../01_knowledge/03_投资策略与选股/01_价值投资法/) |
| `lynch.yaml` | 彼得·林奇 | [02_彼得林奇投资法/](../../01_knowledge/03_投资策略与选股/02_彼得林奇投资法/) |
