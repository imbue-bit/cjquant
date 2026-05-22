# -*- coding: utf-8 -*-
"""
永久投资组合 (Permanent Portfolio) 策略
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
由哈利·布朗（Harry Browne）于 1981 年提出，核心理念：
  - 经济扩张  → 股票受益（权益类）
  - 通货膨胀  → 黄金受益（商品类）
  - 通货紧缩  → 债券受益（利率债）
  - 经济衰退  → 现金/货币保值（货基）

四类资产各配置 25%，每年底再平衡一次以恢复目标比例。

标的池（场外开放式基金）:
  110020.OF  易方达沪深300联接A  → 权益/经济扩张
  161115.OF  招商中证白酒指数    → 权益/消费（可替换为宽基）
  000216.OF  华安黄金ETF联接A    → 黄金/通胀
  012752.OF  博时中债7-10年国开债 → 利率债/通缩

使用说明（组合回测 → 调仓策略 下拉选此文件）:
  - 回测时在基金标的处输入：110020.OF,161115.OF,000216.OF,012752.OF
  - 调仓策略选择本文件
"""

# 目标基金及固定权重（Browne 原版四等分）
PERMANENT_FUNDS = {
    "110020.OF": 0.25,  # 股票基金（权益）
    "161115.OF": 0.25,  # 权益/消费型基金
    "000216.OF": 0.25,  # 黄金 ETF 联接
    "012752.OF": 0.25,  # 中长期利率债
}

# 年度再平衡容忍阈值：任意资产偏离目标超过 5% 才触发再平衡
REBALANCE_THRESHOLD = 0.05


def init(context):
    """策略初始化：记录关键状态变量"""
    context.last_rebalance_year = None
    context.target_weights = PERMANENT_FUNDS.copy()
    print("=" * 55)
    print("  永久投资组合 (Permanent Portfolio) 已初始化")
    print("  目标配置:")
    for code, w in context.target_weights.items():
        print(f"    {code}  →  {w:.0%}")
    print("=" * 55)


def handle_bar(context):
    """每个交易日驱动函数"""
    current_date = context.current_date
    is_first_day = (context.current_date_idx == 0)

    # ── 期初全仓建仓 ──────────────────────────────────────
    if is_first_day:
        print(f"[{current_date.strftime('%Y-%m-%d')}] 期初建仓：等权四类资产各 25%")
        context.rebalance(context.target_weights)
        context.last_rebalance_year = current_date.year
        return

    # ── 年度再平衡（每年最后一个交易日附近）─────────────────
    is_new_year = (
        context.last_rebalance_year is not None
        and current_date.year != context.last_rebalance_year
    )

    if is_new_year:
        # 检查当前实际权重是否偏离目标超过阈值
        total_value = context.cash
        for code, pos_shares in context.positions.items():
            nav = context.get_nav(code, current_date)
            if nav:
                total_value += pos_shares * nav

        if total_value < 100:
            return  # 资金极少，跳过

        max_deviation = 0.0
        for code, target_w in context.target_weights.items():
            nav = context.get_nav(code, current_date)
            if nav and code in context.positions:
                actual_w = (context.positions[code] * nav) / total_value
                max_deviation = max(max_deviation, abs(actual_w - target_w))

        if max_deviation >= REBALANCE_THRESHOLD:
            print(
                f"[{current_date.strftime('%Y-%m-%d')}] 年度再平衡触发"
                f"（最大偏离 {max_deviation:.1%} ≥ 阈值 {REBALANCE_THRESHOLD:.0%}）"
            )
            context.rebalance(context.target_weights)
        else:
            print(
                f"[{current_date.strftime('%Y-%m-%d')}] 年度检查：偏离 {max_deviation:.1%}，"
                f"在容忍范围内，无需再平衡"
            )

        context.last_rebalance_year = current_date.year
