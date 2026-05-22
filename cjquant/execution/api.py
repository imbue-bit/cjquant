import os
import pandas as pd
from typing import List, Dict, Union
from datetime import datetime
from ..backtest.model import Order
from .o32 import O32OrderExporter

class OTCExecutor:
    """
    场外基金高级下单 API
    提供极简的 buy/sell 接口，底层支持多种导出通道（如 O32 格式、微信理财通格式等）。
    默认保存到运行目录。
    """
    def __init__(
        self,
        portfolio_id: str = "FOF_PORTFOLIO",
        asset_unit: str = "FOF_UNIT",
        output_dir: str = "./",
        strip_suffix: bool = True
    ):
        self.portfolio_id = portfolio_id
        self.asset_unit = asset_unit
        self.output_dir = output_dir
        self.strip_suffix = strip_suffix
        
        # 内部订单缓存
        self.orders: List[Order] = []
        self._order_counter = 0

    def buy(self, fund_code: str, amount: float) -> Order:
        """
        申购/买入基金
        :param fund_code: 基金代码 (如 "000001.OF")
        :param amount: 申购金额
        """
        self._order_counter += 1
        order = Order(
            order_id=f"OTC_BUY_{self._order_counter}_{datetime.now().strftime('%M%S')}",
            submit_date=datetime.now(),
            fund_code=fund_code,
            direction="BUY",
            order_value=float(amount),
            order_shares=0.0
        )
        self.orders.append(order)
        return order

    def sell(self, fund_code: str, shares: float) -> Order:
        """
        赎回/卖出基金
        :param fund_code: 基金代码 (如 "000001.OF")
        :param shares: 赎回份额
        """
        self._order_counter += 1
        order = Order(
            order_id=f"OTC_SELL_{self._order_counter}_{datetime.now().strftime('%M%S')}",
            submit_date=datetime.now(),
            fund_code=fund_code,
            direction="SELL",
            order_value=0.0,
            order_shares=float(shares)
        )
        self.orders.append(order)
        return order

    def clear(self):
        """清空当前缓存的订单"""
        self.orders.clear()

    def _process_code(self, code: str) -> str:
        if self.strip_suffix and "." in code:
            return code.split(".")[0]
        return code

    def export_wechat(self, file_path: str) -> pd.DataFrame:
        """
        导出为微信理财通格式的下单列表
        """
        records = []
        for order in self.orders:
            t_date_str = order.submit_date.strftime("%Y-%m-%d") if isinstance(order.submit_date, datetime) else str(order.submit_date)
            records.append({
                "基金代码": self._process_code(order.fund_code),
                "交易类型": "申购" if order.direction == "BUY" else "赎回",
                "发生金额": round(order.order_value, 2) if order.direction == "BUY" else 0.0,
                "发生份额": round(order.order_shares, 4) if order.direction == "SELL" else 0.0,
                "交易渠道": "微信理财通",
                "申请时间": t_date_str
            })
            
        df = pd.DataFrame(records)
        if df.empty:
            df = pd.DataFrame(columns=["基金代码", "交易类型", "发生金额", "发生份额", "交易渠道", "申请时间"])
            
        df.to_csv(file_path, index=False, encoding="utf-8-sig")
        return df

    def execute(self, channels: List[str] = None, file_prefix: str = "order_export", trade_date: Union[str, datetime] = None) -> Dict[str, str]:
        """
        执行下单（导出交易文件），默认保存到运行目录。
        :param channels: 支持的导出渠道列表，可选 "o32", "wechat"。如果为 None，默认全部导出。
        :param file_prefix: 导出文件的前缀名称。
        :param trade_date: 交易日期。
        :return: 导出的文件路径映射字典。
        """
        if not self.orders:
            print("警告: 当前无订单，未生成任何交易文件。")
            return {}

        if channels is None:
            channels = ["o32", "wechat"]

        # 确保输出目录存在
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

        exported_files = {}

        # 1. 导出为 O32 格式
        if "o32" in channels:
            o32_path = os.path.join(self.output_dir, f"{file_prefix}_o32.csv")
            exporter = O32OrderExporter(
                portfolio_id=self.portfolio_id,
                asset_unit=self.asset_unit,
                strip_suffix=self.strip_suffix
            )
            exporter.export(self.orders, o32_path, format="csv", encoding="gbk", trade_date=trade_date)
            exported_files["o32"] = o32_path

        # 2. 导出为微信理财通格式
        if "wechat" in channels:
            wechat_path = os.path.join(self.output_dir, f"{file_prefix}_wechat.csv")
            self.export_wechat(wechat_path)
            exported_files["wechat"] = wechat_path

        print(f"所有通道交易文件已成功导出到: {self.output_dir}")
        return exported_files
