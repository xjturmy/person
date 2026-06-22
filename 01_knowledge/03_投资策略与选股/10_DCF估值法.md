# 10 DCF 估值法 — Aswath Damodaran

> **大师**：Aswath Damodaran（阿斯沃斯·达莫达兰，1957-）
> **方法**：DCF（Discounted Cash Flow，自由现金流折现）—— 估值的"第一性原理"
> **出处**：纽约大学 Stern 商学院教授，著有《Damodaran on Valuation》《The Little Book of Valuation》
> **定位**：**所有估值方法的母方法**，把企业未来现金流折回今天

---

## 🎯 一句话核心

> "**任何资产的价值 = 它未来产生的所有现金流，按风险折现到今天的总和。**"
>
> —— Damodaran

PE / PB 都是 DCF 的简化推论。
**DCF 是"为什么茅台值这个价"的根本性回答**，
PE 只是"市场愿意给多少倍"的快照。

---

## 📐 公式（两阶段 DCF，最常用）

### 整体框架

```
企业价值（EV）
  = 显性预测期 FCF 折现 + 永续价值折现

权益价值
  = 企业价值 - 净债务

每股内在价值
  = 权益价值 / 总股本
```

### 完整公式

```
            n     FCF_t        TV
EV  =  Σ  ───────────  +  ──────────
           t=1  (1+WACC)ᵗ   (1+WACC)ⁿ

其中：
  TV = FCF_(n+1) / (WACC - g)        # Gordon 增长模型
  n  = 显性预测期（通常 5-10 年）
```

### 关键变量

| 变量 | 含义 | 数据来源 |
|------|------|---------|
| **FCF** | 自由现金流 = 经营现金流 - 资本支出 | `04_现金流分析` |
| **WACC** | 加权平均资本成本 = E/V × Re + D/V × Rd × (1-t) | 自计算 |
| **Re** | 股权成本 = Rf + β × ERP | CAPM 模型 |
| **g** | 永续增长率 | 经验值（A 股取 2-3%） |
| **n** | 显性预测期 | 通常 5-10 年 |

---

## 🔑 Damodaran 三步估值法

### 1. **故事 → 数字**（Story to Numbers）

Damodaran 强调：估值开始于**讲一个商业故事**，再把故事翻译成数字。

> 例：茅台的故事 = "中国奢侈品 + 强定价权 + 现金流稳定"
> 翻译为数字 = "未来 10 年营收 CAGR 12%，毛利率维持 91%，资本支出/营收 5%"

### 2. **数字 → 估值**（Numbers to Value）

按公式跑 DCF，得到内在价值。

### 3. **测试故事**（Test the Story）

回看：故事**合不合理**？同行验证、历史验证、可能性验证。

---

## 🇨🇳 A 股关键参数（2026 年）

| 参数 | A 股取值 | 来源 |
|------|---------|------|
| **无风险利率 Rf** | 10 年期国债收益率 ≈ 2.3% | 中债信息网 |
| **股权风险溢价 ERP** | A 股 6-7% | Damodaran 官网每年更新 |
| **永续增长率 g** | 2-3%（接近长期 GDP） | — |
| **税率 t** | 25%（一般企业），15%（高新技术） | 财报实际有效税率 |

> Damodaran 官网（pages.stern.nyu.edu/~adamodar/）每月更新各国/各行业 ERP、Beta、WACC 数据，**国别数据中国可下**

---

## 🛠️ 公司分类与公式选择

### 类型 A：稳态成熟企业 → 单阶段 DCF
- 茅台 / 招商银行 / 美的 / 伊利
- 增长率稳定 → 直接 Gordon 模型

### 类型 B：高速增长期 → 两阶段 DCF
- 比亚迪 / 宁德 / 中际旭创 / 蜜雪
- 5-10 年高增长 + 之后永续

### 类型 C：周期股 → 跨周期平均 DCF
- 三美 / 中国中车
- 取**周期内平均** FCF 而非当期

### 类型 D：金融股 → DDM（股利贴现）替代
- 招商银行 / 新华保险
- DCF 不适用，改用 DDM 或剩余收益模型（RIM）

---

## 🇨🇳 A 股适用性评估

### ✅ 高适用度

| 行业 | 适用性 | 原因 |
|------|--------|------|
| 消费白马 | ⭐⭐⭐⭐⭐ | FCF 稳定，永续增长可预测 |
| 公用事业 | ⭐⭐⭐⭐ | 现金流稳定 |
| 成熟制造 | ⭐⭐⭐⭐ | 资本支出可预测 |

### ⚠️ 中等适用度

| 行业 | 问题 |
|------|------|
| 周期成长（新能源） | FCF 大幅波动，敏感性分析重要 |
| 科技成长（中际旭创） | 高 R&D 难拆分，Beta 不稳 |

### ❌ 不适用 → 改用其他方法

| 行业 | 替代方法 |
|------|---------|
| 银行 / 保险 | DDM、RIM（剩余收益模型）、PB-ROE |
| 房地产 | NAV（净资产价值法） |
| 早期亏损公司 | 风险投资法、收入倍数法 |

---

## 🧮 DCF 简化版（项目落地）

```python
def damodaran_dcf(ticker: str,
                  forecast_years: int = 5,
                  growth_rate: float = 0.10,    # 显性期增长率
                  perpetual_g: float = 0.025,    # 永续增长率
                  wacc: float = 0.085) -> float:
    """两阶段 DCF 估值"""

    # 1. 取最近 1 年 FCF（来自 DuckDB）
    fcf_0 = query_metric(ticker, 'fcf', period='ttm')

    # 2. 显性期 FCF 折现
    pv_explicit = sum(
        fcf_0 * (1 + growth_rate)**t / (1 + wacc)**t
        for t in range(1, forecast_years + 1)
    )

    # 3. 永续价值
    fcf_terminal = fcf_0 * (1 + growth_rate)**forecast_years * (1 + perpetual_g)
    tv = fcf_terminal / (wacc - perpetual_g)
    pv_tv = tv / (1 + wacc)**forecast_years

    # 4. 企业价值 → 权益价值 → 每股内在价值
    ev = pv_explicit + pv_tv
    net_debt = query_metric(ticker, 'net_debt')
    equity_value = ev - net_debt
    shares = query_metric(ticker, 'shares_outstanding')

    return equity_value / shares
```

---

## ⚖️ 敏感性分析（DCF 的关键补救）

DCF 对参数极度敏感，**单点估值不可靠**，必须做敏感性表：

```
            WACC=7.5%   WACC=8.5%   WACC=9.5%
g=2.0%       2,800       2,200       1,800
g=2.5%       3,100       2,400       1,950
g=3.0%       3,500       2,650       2,100
```

→ 给出**估值区间**而非单一数字（如"茅台内在价值 1800-3500 元/股"）

---

## 🎯 落地建议（项目集成）

| 步骤 | 文件 | 说明 |
|------|------|------|
| 1. 参数库 | `rules/dcf_params.yaml` | 各行业 WACC / g 默认值 |
| 2. 实现 | `score.py::dcf_value()` | 输入 ticker + 假设，输出内在价值 |
| 3. 敏感性 | `score.py::dcf_sensitivity()` | 输出 3×3 矩阵 |
| 4. 与市价对比 | `safety_margin = (intrinsic - price) / intrinsic` | 安全边际 |
| 5. 输出 | DuckDB View `v_dcf_valuation` | 15 家公司 DCF 估值表 |

---

## ⚠️ Damodaran 三大警告

### 1. **Garbage In, Garbage Out**
DCF 的输入假设错了，输出再精确也是错的。**永远用区间，不用单点**。

### 2. **DCF 不适合"故事股"**
没有稳定盈利的成长股，DCF 失效。Damodaran 自己也用 **VC 估值法 / 实物期权法** 估值早期公司。

### 3. **不要用 DCF 反推假设**
错误用法："我觉得茅台值 3000 元，反推 g 应该是多少？" → 这变成了**自我验证**。
正确用法：先定故事 → 定数字 → 算估值 → 与市价对比。

---

## 📚 延伸阅读

- 《Damodaran on Valuation》（达摩达兰估值学，进阶教材）
- 《The Little Book of Valuation》（小本估值，入门）
- **Damodaran 官网**：https://pages.stern.nyu.edu/~adamodar/
  - 每月更新各国 ERP、各行业 Beta/WACC，**估值必查数据库**
- 项目内对照：[01_价值投资法/04_估值分析.md](01_价值投资法/04_估值分析.md)
- A 股 DCF 实操：可参考券商深度报告（"DCF 估值"+"白酒/电力"等关键词）
