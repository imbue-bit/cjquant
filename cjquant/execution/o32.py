import pandas as pd
from typing import List, Union, Dict, Callable
from datetime import datetime
from ..backtest.model import Order, TradeRecord

class O32OrderExporter:
    """
    O32下单列表导出模块
    支持将回测引擎生成的订单（Order）或交易记录（TradeRecord）导出为恒生 O32 系统可导入的交易指令格式。
    """
    def __init__(
        self,
        portfolio_id: str = "FOF_PORTFOLIO",
        asset_unit: str = "FOF_UNIT",
        strip_suffix: bool = True,
        direction_mapping: Dict[str, str] = None,
        column_mapping: Dict[str, str] = None,
        code_mapping: Callable[[str], str] = None
    ):
        self.portfolio_id = portfolio_id
        self.asset_unit = asset_unit
        self.strip_suffix = strip_suffix
        
        # 默认业务类别转换：BUY -> 申购, SELL -> 赎回
        self.direction_mapping = direction_mapping or {
            "BUY": "申购",
            "SELL": "赎回"
        }
        
        # 默认导出的O32列名映射
        self.column_mapping = column_mapping or {
            "fund_code": "证券代码",
            "direction": "业务类别",
            "order_value": "委托金额",
            "order_shares": "委托数量",
            "portfolio_id": "组合编号",
            "asset_unit": "资产单元",
            "trade_date": "交易日期"
        }
        
        self.code_mapping = code_mapping

    def _process_code(self, code: str) -> str:
        if self.code_mapping:
            return self.code_mapping(code)
        if self.strip_suffix and "." in code:
            return code.split(".")[0]
        return code

    def from_orders(self, orders: List[Order], trade_date: Union[str, datetime] = None) -> pd.DataFrame:
        """
        从订单列表（Order List）转换
        """
        records = []
        for order in orders:
            # 确定交易日期
            t_date = trade_date or order.submit_date
            if isinstance(t_date, datetime):
                t_date_str = t_date.strftime("%Y%m%d")
            else:
                t_date_str = str(t_date) if t_date else datetime.now().strftime("%Y%m%d")

            records.append({
                "fund_code": self._process_code(order.fund_code),
                "direction": self.direction_mapping.get(order.direction, order.direction),
                "order_value": round(order.order_value, 2) if order.direction == "BUY" else 0.0,
                "order_shares": round(order.order_shares, 4) if order.direction == "SELL" else 0.0,
                "portfolio_id": self.portfolio_id,
                "asset_unit": self.asset_unit,
                "trade_date": t_date_str
            })

        df = pd.DataFrame(records)
        if df.empty:
            df = pd.DataFrame(columns=list(self.column_mapping.keys()))
            
        columns_to_keep = [k for k in self.column_mapping.keys() if k in df.columns]
        df = df[columns_to_keep].rename(columns=self.column_mapping)
        return df

    def from_trades(self, trades: List[TradeRecord]) -> pd.DataFrame:
        """
        从成交记录（TradeRecord List）转换
        """
        records = []
        for trade in trades:
            t_date = trade.submit_date
            t_date_str = t_date.strftime("%Y%m%d") if isinstance(t_date, datetime) else str(t_date)

            records.append({
                "fund_code": self._process_code(trade.fund_code),
                "direction": self.direction_mapping.get(trade.direction, trade.direction),
                # 对于 BUY，使用 gross_amount 作为申报委托金额
                "order_value": round(trade.gross_amount, 2) if trade.direction == "BUY" else 0.0,
                # 对于 SELL，使用 filled_shares 作为申报委托数量
                "order_shares": round(trade.filled_shares, 4) if trade.direction == "SELL" else 0.0,
                "portfolio_id": self.portfolio_id,
                "asset_unit": self.asset_unit,
                "trade_date": t_date_str
            })

        df = pd.DataFrame(records)
        if df.empty:
            df = pd.DataFrame(columns=list(self.column_mapping.keys()))
            
        columns_to_keep = [k for k in self.column_mapping.keys() if k in df.columns]
        df = df[columns_to_keep].rename(columns=self.column_mapping)
        return df

    def export(self, data: Union[List[Order], List[TradeRecord]], file_path: str, format: str = "csv", **kwargs) -> pd.DataFrame:
        """
        导出下单文件，支持 csv 或 excel 格式
        """
        if not data:
            raise ValueError("没有需要导出的下单记录")

        first_item = data[0]
        if isinstance(first_item, Order):
            df = self.from_orders(data, **kwargs)
        elif isinstance(first_item, TradeRecord):
            df = self.from_trades(data)
        else:
            raise TypeError("不受支持的数据类型，必须为 Order 或 TradeRecord 列表")

        # 确保导出目录存在
        import os
        dir_name = os.path.dirname(file_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

        if format.lower() == "csv":
            # O32系统在中文Windows环境下，通常期望带有 GBK 编码的 CSV 避免乱码
            encoding = kwargs.get("encoding", "gbk")
            df.to_csv(file_path, index=False, encoding=encoding)
        elif format.lower() in ["xlsx", "xls", "excel"]:
            df.to_excel(file_path, index=False)
        else:
            raise ValueError(f"不支持的导出格式: {format}")

        print(f"O32下单列表已成功导出到: {file_path}")
        return df
