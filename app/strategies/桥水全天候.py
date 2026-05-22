# -*- coding: utf-8 -*-
"""
桥水全天候策略 (Bridgewater All Weather Portfolio)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
由桥水基金（Bridgewater Associates）的瑞·达利欧（Ray Dalio）设计。

核心逻辑：经济由"增长"与"通胀"两个维度驱动，各有上行/下行，
构成四个象限，每个象限配置一类资产，以"风险平价"理念分配权重，
使得每个象限对组合的风险贡献相等。

四象限配置思路（桥水公开版本参考比例）:
  ┌──────────────────────┬──────────────────────┐
  │  经济增长↑ / 通胀↑   │  经济增长↑ / 通胀↓   │
  │  大宗商品  + 通胀债  │  股票（权益）         │
  │  (TIPS/黄金)  约15%  │          约30%        │
  ├──────────────────────┼──────────────────────┤
  │  经济增长↓ / 通胀↑   │  经济增长↓ / 通胀↓   │
  │  黄金  +  大宗商品   │  长期国债（利率债）   │
  │          约7.5%      │          约55%        │
  └──────────────────────┴──────────────────────┘

→ 汇总为四类资产，风险平价方式动态分配：
    权益类（股票）    ~30%  → 110020.OF (沪深300)
    黄金/通胀对冲     ~15%  → 000216.OF (华安黄金ETF联接)
    长端利率债        ~40%  → 012752.OF (中债7-10年国开债)
    中短期信用/货基   ~15%  → 161115.OF (此处示例用，可替换为债基)

策略机制：
  - 每季度末（3月/6月/9月/12月底）以风险平价优化器重新计算权重
  - 历史数据不足时退化为静态目标权重
  - 再平衡使用 context.rebalance() 确保考虑 T+1/T+3 结算

使用说明（组合回测 → 调仓策略 下拉选此文件）:
  - 回测时在基金标的处输入：110020.OF,000216.OF,012752.OF,161115.OF
  - 调仓策略选择本文件
"""

import pandas as pd
from cjquant.optimizer.traditional import RiskParityOptimizer

# 四象限静态目标权重（数据不足时的回退值）
STATIC_WEIGHTS = {
    "110020.OF": 0.30,   # 权益/经济增长受益
    "000216.OF": 0.15,   # 黄金/通胀对冲
    "012752.OF": 0.40,   # 长端利率债/衰退受益
    "161115.OF": 0.15,   # 消费/中短端（可替换货基或信用债）
}

# 季度再平衡触发月份
REBALANCE_MONTHS = {3, 6, 9, 12}

# 风险平价历史窗口（交易日数）
HISTORY_WINDOW = 120


def init(context):
    """初始化：记录上次再平衡季度"""
    context.last_rebalance_quarter = None
    print("=" * 60)
    print("  桥水全天候策略 (All Weather Portfolio) 已初始化")
    print("  静态目标权重 (数据不足时回退):")
    for code, w in STATIC_WEIGHTS.items():
        print(f"    {code}  →  {w:.0%}")
    print("  再平衡频率: 每季度末 (3月/6月/9月/12月)")
    print(f"  风险平价历史窗口: {HISTORY_WINDOW} 个交易日")
    print("=" * 60)


def _get_current_quarter(date):
    """获取当前季度标识 (year, quarter)"""
    return (date.year, (date.month - 1) // 3 + 1)


def _compute_rp_weights(context):
    """
    用过去 HISTORY_WINDOW 个交易日的日收益率计算风险平价权重。
    若历史数据不足，返回 None（由调用方回退到静态权重）。
    """
    funds = list(STATIC_WEIGHTS.keys())
    hist_returns = {}

    for fund in funds:
        navs = context.get_history_navs(fund, count=HISTORY_WINDOW)
        if len(navs) >= 20:
            rets = navs.pct_change().dropna()
            hist_returns[fund] = rets

    if len(hist_returns) < 2:
        return None  # 数据太少，无法优化

    df_rets = pd.DataFrame(hist_returns).dropna()
    if len(df_rets) < 15:
        return None

    try:
        opt = RiskParityOptimizer(df_rets)
        weights_series = opt.optimize()
        # 转为字典，确保所有目标基金都有权重
        weights = {}
        for i, fund in enumerate(df_rets.columns):
            weights[fund] = float(weights_series.iloc[i])
        # 归一化确保合计=1
        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()} if total > 0 else None
    except Exception as e:
        print(f"  [风险平价优化失败] {e}，回退到静态权重")
        return None


def handle_bar(context):
    """每个交易日驱动函数"""
    current_date = context.current_date
    is_first_day = (context.current_date_idx == 0)

    # ── 期初建仓（使用静态目标权重）────────────────────────
    if is_first_day:
        print(f"[{current_date.strftime('%Y-%m-%d')}] 期初建仓（全天候静态权重）")
        for code, w in STATIC_WEIGHTS.items():
            print(f"    {code}: {w:.0%}")
        context.rebalance(STATIC_WEIGHTS)
        context.last_rebalance_quarter = _get_current_quarter(current_date)
        return

    # ── 季度再平衡检测 ───────────────────────────────────
    current_quarter = _get_current_quarter(current_date)
    is_month_end_of_quarter = (
        current_date.month in REBALANCE_MONTHS
        and current_quarter != context.last_rebalance_quarter
    )

    if not is_month_end_of_quarter:
        return  # 非季末，跳过

    # 计算风险平价权重
    rp_weights = _compute_rp_weights(context)

    if rp_weights is not None:
        print(
            f"[{current_date.strftime('%Y-%m-%d')}] 季度再平衡（风险平价）"
            f"  Q{current_quarter[1]}/{current_quarter[0]}"
        )
        for code, w in rp_weights.items():
            print(f"    {code}: {w:.2%}")
        context.rebalance(rp_weights)
    else:
        # 回退到静态权重
        print(
            f"[{current_date.strftime('%Y-%m-%d')}] 季度再平衡（静态权重回退）"
            f"  Q{current_quarter[1]}/{current_quarter[0]}"
        )
        context.rebalance(STATIC_WEIGHTS)

    context.last_rebalance_quarter = current_quarter
