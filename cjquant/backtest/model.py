from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class PositionLot:
    """持仓批次 (对应中登公司的单笔买入确认单，用于FIFO算费)"""
    fund_code: str
    confirm_date: datetime  # 确认日期 (T+1)
    shares: float           # 持有份额
    unit_cost: float        # 买入单位成本

@dataclass
class Order:
    """用户提交的交易指令"""
    order_id: str
    submit_date: datetime
    fund_code: str
    direction: str          # 'BUY' 或 'SELL'
    order_value: float = 0.0  # 申购金额 (仅 BUY 有效)
    order_shares: float = 0.0 # 赎回份额 (仅 SELL 有效)
    status: str = 'PENDING'   # PENDING, CONFIRMED, REJECTED, CANCELED
    
@dataclass
class TradeRecord:
    """成交确认凭证"""
    trade_id: str
    order_id: str
    fund_code: str
    direction: str
    submit_date: datetime
    confirm_date: datetime    # 净值确认日 (T+1)
    settle_date: datetime     # 资金到账日 (赎回T+n)
    confirm_nav: float        # 确认净值(包含冲击成本)
    filled_shares: float      # 成交份额
    gross_amount: float       # 发生金额(税前)
    fee: float                # 手续费
    net_amount: float         # 实际到账/扣除金额