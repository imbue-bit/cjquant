import pandas as pd
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional
from .model import Order, TradeRecord
from .portfolio import TransitCashAccount, FundPosition
from .fee import OTCFeeModel
from .slippage import BaseSlippage, ZeroSlippage
from .exceptions import InsufficientCashError, InsufficientPositionError

class OTCBacktestEngine:
    def __init__(self, 
                 market_data: pd.DataFrame, 
                 initial_cash: float = 1e7,
                 t_plus_confirm: int = 1, # T+1确认净值
                 t_plus_settle: int = 3,  # 赎回T+3到账
                 slippage_model: BaseSlippage = None):
        
        self.market_data = market_data.copy()
        self.trading_dates = list(self.market_data.index.unique().sort_values())
        
        # 预建 NAV 快查表（含前向填充，解决节假日/数据缺口时市值归零问题）
        self._nav_cache: dict = {}  # {(date, fund_code): adj_nav}
        for code in self.market_data['fund_code'].unique():
            fund_df = self.market_data[self.market_data['fund_code'] == code]['adj_nav']
            # 对交易日历进行前向填充：缺失的交易日用上一个有效净值代替
            fund_series = fund_df.reindex(self.trading_dates, method='ffill')
            for date, nav_val in fund_series.items():
                if pd.notna(nav_val):
                    self._nav_cache[(date, code)] = float(nav_val)
        
        self.cash_account = TransitCashAccount(initial_cash)
        self.positions: Dict[str, FundPosition] = {}
        self.fee_model = OTCFeeModel()
        self.slippage = slippage_model or ZeroSlippage()
        
        self.t_plus_confirm = t_plus_confirm
        self.t_plus_settle = t_plus_settle
        
        self.pending_orders: List[Order] = []
        self.trade_history: List[TradeRecord] = []
        self.daily_stats: List[dict] = []
        
        self.current_date_idx = 0
        self.logger = logging.getLogger("OTC_Engine")

    @property
    def current_date(self) -> datetime:
        return self.trading_dates[self.current_date_idx]

    def _get_nav(self, fund_code: str, date) -> float:
        """从预建缓存中查询复权净值（含前向填充，不会因节假日返回 None）"""
        return self._nav_cache.get((date, fund_code), None)

    def _get_future_trading_date(self, start_date_idx: int, t_plus_days: int) -> datetime:
        """按照交易日历向后推算 (自动跳过节假日)"""
        target_idx = start_date_idx + t_plus_days
        if target_idx >= len(self.trading_dates):
            # 越界处理，返回最后一个可用日期
            return self.trading_dates[-1]
        return self.trading_dates[target_idx]

    def submit_order(self, fund_code: str, direction: str, value: float = 0, shares: float = 0):
        if direction == 'BUY':
            self.cash_account.lock_cash(value) # 提交时立即冻结资金
        elif direction == 'SELL':
            if fund_code not in self.positions:
                raise InsufficientPositionError(f"无持仓: {fund_code}")
            pos = self.positions[fund_code]
            if pos.total_available_shares < shares:
                raise InsufficientPositionError(f"可用份额不足. 可用:{pos.total_available_shares}, 需求:{shares}")
            pos.frozen_shares += shares

        order = Order(
            order_id=uuid.uuid4().hex[:8],
            submit_date=self.current_date,
            fund_code=fund_code,
            direction=direction,
            order_value=value,
            order_shares=shares
        )
        self.pending_orders.append(order)

    def step(self):
        today = self.current_date
        
        # 1. 资金到账处理
        self.cash_account.process_daily_arrival(today)
        
        # 2. 撮合确认队列中的订单
        unprocessed_orders = []
        for order in self.pending_orders:
            # 找到指令对应日期的 Index
            submit_idx = self.trading_dates.index(order.submit_date)
            confirm_date = self._get_future_trading_date(submit_idx, self.t_plus_confirm)
            
            # 如果今天就是确认日
            if today == confirm_date:
                self._execute_order(order, confirm_date)
            else:
                unprocessed_orders.append(order)
                
        self.pending_orders = unprocessed_orders
        
        # 3. 每日结算
        self._record_daily_stats()
        
        # 时间推移
        self.current_date_idx += 1

    def _execute_order(self, order: Order, confirm_date: datetime):
        nav = self._get_nav(order.fund_code, confirm_date)
        if nav is None:
            self.logger.warning(f"基金 {order.fund_code} 在 {confirm_date} 无净值数据，订单作废")
            order.status = 'REJECTED'
            if order.direction == 'BUY':
                self.cash_account.available_cash += order.order_value
                self.cash_account.frozen_cash -= order.order_value
            elif order.direction == 'SELL':
                if order.fund_code in self.positions:
                    self.positions[order.fund_code].frozen_shares -= order.order_shares
            return

        if order.fund_code not in self.positions:
            self.positions[order.fund_code] = FundPosition(order.fund_code, self.fee_model)
        
        pos = self.positions[order.fund_code]

        if order.direction == 'BUY':
            # 计入冲击成本
            exec_nav = self.slippage.get_impact_nav(nav, order.order_value, 'BUY')
            fee = self.fee_model.get_buy_fee(order.order_value)
            net_cash = order.order_value - fee
            shares_bought = net_cash / exec_nav
            
            self.cash_account.frozen_cash -= order.order_value
            pos.add_lot(confirm_date, shares_bought, exec_nav)
            
            settle_date = confirm_date # 买入当即确认份额
            trade = TradeRecord(uuid.uuid4().hex[:8], order.order_id, order.fund_code, 'BUY', 
                                order.submit_date, confirm_date, settle_date, exec_nav, 
                                shares_bought, order.order_value, fee, order.order_value)
                                
        elif order.direction == 'SELL':
            # 基于 FIFO 结算惩罚性手续费
            exec_nav = self.slippage.get_impact_nav(nav, order.order_shares * nav, 'SELL')
            gross_val, fee, net_val = pos.process_sell(confirm_date, order.order_shares, exec_nav)
            
            # 计算 T+n 的赎回到账日
            submit_idx = self.trading_dates.index(order.submit_date)
            settle_date = self._get_future_trading_date(submit_idx, self.t_plus_settle)
            
            # 资金扔进黑洞队列
            self.cash_account.add_to_transit(net_val, settle_date)
            
            trade = TradeRecord(uuid.uuid4().hex[:8], order.order_id, order.fund_code, 'SELL', 
                                order.submit_date, confirm_date, settle_date, exec_nav, 
                                order.order_shares, gross_val, fee, net_val)

        order.status = 'CONFIRMED'
        self.trade_history.append(trade)

    def _record_daily_stats(self):
        """计算每日 FOF 资产总值"""
        total_market_value = 0.0
        today = self.current_date
        
        for code, pos in self.positions.items():
            nav = self._get_nav(code, today)
            if nav is not None:
                total_market_value += pos.total_shares * nav

        # 包含 transit 中的资金，因为这是属于投资者的钱，只是在途
        transit_value = sum(self.cash_account.transit_queue.values())
        total_assets = self.cash_account.available_cash + self.cash_account.frozen_cash + transit_value + total_market_value
        
        self.daily_stats.append({
            'date': today,
            'available_cash': self.cash_account.available_cash,
            'frozen_cash': self.cash_account.frozen_cash,
            'transit_cash': transit_value,
            'market_value': total_market_value,
            'total_assets': total_assets
        })

    def run_all(self):
        """执行完整回测"""
        while self.current_date_idx < len(self.trading_dates):
            # 这里可以接入你的策略逻辑 (例如月底调仓)
            # strategy.on_bar(self.current_date) 
            self.step()

    def export_trades_csv(self, file_path: str):
        if not self.trade_history:
            self.logger.warning("没有产生任何交易，跳过导出")
            return
        df = pd.DataFrame([vars(t) for t in self.trade_history])
        for col in ['submit_date', 'confirm_date', 'settle_date']:
            df[col] = df[col].dt.strftime('%Y-%m-%d')
        df.to_csv(file_path, index=False, encoding='utf-8-sig')

    def export_results_csv(self, file_path: str):
        if not self.daily_stats:
            return
        df = pd.DataFrame(self.daily_stats)
        df.set_index('date', inplace=True)
        # 顺便计算每日收益率
        df['daily_return'] = df['total_assets'].pct_change().fillna(0)
        df.to_csv(file_path, encoding='utf-8-sig')