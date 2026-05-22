# cjquant

*The Quantitative Framework for China OTC Funds & Asset Allocation*

cjquant 是一个专为国内资管机构（公募FOF、理财子、券商资管、FO等）设计的场外基金量化与资产配置投研框架。针对国内二级市场外产品（公募基金、私募基金、银行理财）数据非标、流动性受限、费率结构复杂等核心痛点，提供从数据清洗、归因分析到复杂流动性回测与组合优化的全链路解决方案。

## 摘要

目前主流的量化框架（如 vn.py, qlib, backtrader）均针对场内高频及日频交易设计，在面对场外资产时存在底层逻辑不兼容的问题。cjquant 放弃了传统的“订单-撮合”模型，采用“份额-净值-流动性时间轴”模型重构了回测引擎，并内置了针对非标低频数据的量化评价体系，旨在为人民币资产配置提供工业级的基础设施。

---

## 功能特性

### 1. 场外资产真实撮合引擎
针对国内公私募产品复杂的申赎规则，完全重构了流动性与费率模拟机制：
*   非对称流动性时间轴：原生支持跨交易日的 T+n 确认与到账机制（例如：申购 T+1 确认并计息，赎回 T+2 确认 T+4 资金可用），精确还原资金占用成本。
*   非线性阶梯费率模型：支持根据持有自然日/交易日动态计算赎回费（如：持有<7天收取1.5%惩罚性赎回费，>365天免赎回费）。
*   多源收益分配与业绩报酬：支持公募基金的现金分红与红利再投（配息机制），以及私募基金复杂的高水位法（High-Water Mark）与门槛收益率（Hurdle Rate）业绩报酬提取扣减。
*   份额合并与映射：自动处理同一基金 A/C/E 类份额的申购费/销售服务费差异，在回测及归因中实现底层资产的合并穿透。

### 2. 异构数据对齐与治理 
解决国内大资管跨机构数据源的异构问题：
*   序列对齐：针对公募日频、私募周/月频、宏观指标季频的异构数据，提供前向填充（ffill）、三次样条插值（Cubic Spline）、以及基于自回归与同类指数映射的 Beta 填充算法。
*   去除幸存者偏差：支持底层存续期生命周期管理。引入退市/清盘基金的强制赎回机制与惩罚项，避免截面选取时的前视偏差。
*   基金经理职业生涯拼接：底层数据结构支持“人”与“产品”的解耦。支持将某基金经理在不同产品、不同机构的任职区间收益率进行拼接，并根据管理规模（AUM）进行加权平滑。

### 3. 穿透分析
针对场外基金“黑盒化”特性，提供多层次的因子解析：
*   基于净值的风格分析 (RBSA - Returns-Based Style Analysis)：内置带约束的非负最小二乘法（NNLS）与滚动多元回归。支持自定义因子库（如 Fama-French 3/5 因子，或申万一级行业指数），实时测算基金动态仓位与风格漂移水平。
*   基于持仓的归因测算 (HBSA - Holdings-Based Style Analysis)：解析公募季报/半年报底层真实持仓。支持经典的 Brinson-Fachler 归因模型（资产配置/个股选择/交互效应分离）。

### 4. 机资产配置优化
专为中低频调仓设计的组合优化算法库：
*   协方差矩阵收缩：针对场外低频数据样本不足导致的协方差矩阵失真，内置 Ledoit-Wolf 收缩算法。
*   机器学习与层次组合：除传统均值方差（M-V）外，提供基于图论与无监督聚类的层次风险平价算法及最大分散度组合（MDP）。
*   主观观点融合：集成 Black-Litterman 模型，支持投资经理将对特定宏观事件或行业板块的主观预测转化为后验权重。

---

以下示例代码展示了如何调用框架内各子模块完成复杂的资管投研任务。

### 考虑国内场外真实流动性与费率的 FOF 回测

传统量化框架默认买入即成交，而在实际 FOF 管理中，流动性占用与申赎损耗对组合收益影响巨大。调用 `cjquant.backtest` 可精确还原这一过程。

```python
import pandas as pd
from cjquant.backtest.engine import OTCBacktestEngine
from cjquant.backtest.fee import TieredFeeModel
from cjquant.backtest.slippage import LiquiditySlippageModel

public_fund_fee = TieredFeeModel(
    subscription_rate=0.0015,  # 前端申购费 0.15%
    redemption_tiers=[
        (7, 0.015),            # 持有 <7 天，赎回费 1.5%
        (30, 0.0075),          # 持有 <30 天，赎回费 0.75%
        (365, 0.005),          # 持有 <1 年，赎回费 0.5%
        (float('inf'), 0.0)    # 大于 1 年免申购费
    ]
)

# 初始化引擎，设定 T+N 流动性规则
engine = OTCBacktestEngine(
    initial_capital=50000000,
    fee_model=public_fund_fee,
    slippage_model=LiquiditySlippageModel(buy_delay=1, sell_delay=3) # T+1确认, T+3到账
)

# 月频动量轮动
def target_momentum_strategy(context):
    if context.is_month_end:
        # 获取多只公募基金对齐后的历史净值
        nav_data = context.data.history(context.universe, fields='nav', window=60)
        
        # 计算动量因子并生成目标权重
        momentum = nav_data.iloc[-1] / nav_data.iloc[0] - 1
        target_weights = momentum[momentum > 0].apply(lambda x: 1.0 / len(momentum))
        
        # 测算赎回费损耗、计算在途资金占用、触发订单
        context.order_target_portfolio(target_weights)

result = engine.run(target_momentum_strategy, start='2018-01-01', end='2023-12-31')
```

### 基金持仓与风格穿透

针对国内私募基金不披露底仓的黑盒特性，调用 `cjquant.look_through.rbsa_engine` 模块，通过滚动净值序列反推真实的因子暴露度。

```python
from cjquant.data.pipeline import DataPipeline
from cjquant.look_through.rbsa_engine import RBSAEngine
from cjquant.look_through.model import RollingOLSModel

# 加载目标私募的周频净值与基准因子系列（如：中证500、沪深300、国债指数）
pipeline = DataPipeline()
fund_nav = pipeline.load('P00001.PF')
factors = pipeline.load_factors(['000905.SH', '000300.SH', 'H11001.CSI'])

# 初始化 RBSA 引擎
rbsa = RBSAEngine(
    fund_returns=fund_nav.pct_change(),
    factor_returns=factors.pct_change(),
    model=RollingOLSModel(window=52, constrained=True) # 带非负与归一化约束的 52 周滚动回归
)

# 拟合并获取动态仓位暴露矩阵
exposures = rbsa.fit_exposures()

# 检测风格漂移 (例如：名义上的市场中性产品，其实际多头敞口是否超限)
drift_warnings = rbsa.detect_style_drift(threshold=0.15)
```

### 3. 基于机器学习的前沿组合优化

调用 `cjquant.optimizer.machine_learning` 处理传统均值方差模型在非标数据中协方差矩阵极易失效的问题。

```python
from cjquant.data.aligner import FrequencyAligner
from cjquant.optimizer.machine_learning import HRPOptimizer
from cjquant.visualizer.plotter import AllocationPlotter

# 对齐私募(周频)与公募(日频)序列
aligner = FrequencyAligner(method='cubic_spline')
aligned_returns = aligner.align([private_funds, public_funds], target_freq='W')

# 使用层次风险平价算法分配权重
# 1. 距离矩阵计算 2. 层次聚类 3. 递归二分配置
optimizer = HRPOptimizer(aligned_returns)
optimal_weights = optimizer.optimize()

# 可视化输出聚类树状图及最终权重
AllocationPlotter.plot_dendrogram(optimizer.cluster_linkage)
```

---

## 数据生态与系统集成

考虑到资管机构底层数据来源的复杂性，cjquant 核心库解耦了数据获取逻辑，提供标准化的 `Adapter` 接口。用户可根据自身环境快速接入私有或第三方数据源：

*   本地/私有数据库：支持接入 MySQL, PostgreSQL, ClickHouse 中存储的估值表。
*   金融终端接口：付费版维护针对 Wind (WdQx), 聚源 (JYDB), 东方财富 Choice 的对接层。
*   开源测试数据：内置测试适配器，便于冷启动与策略初步验证。

通过修改配置文件，即可无缝切换底层数据源，上层策略代码无需做任何修改。

---

## 安装

安装方式：

```bash
pip install cjquant
```

---

## Roadmap

我们致力于将 cjquant 打造成国内买方机构的场外投研标准件，未来演进重点包括：

- 完善衍生品与另类资产抽象层，支持包含雪球结构产品、CTA 私募的跨资产类别宏观配置测试。
- 支持基于因子表现和组合持仓的 Brinson 归因报告自动化生成。
- 开放合规风控引擎，提供事前交易拦截与机构白名单管理支持。

## 协议与授权

本项目的开源版本遵循 GPLv3  协议发布。对于资管机构的私有化定制、高级算子支持及系统级集成，请参考商业授权方案。
