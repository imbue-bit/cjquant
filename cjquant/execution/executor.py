import pandas as pd
from typing import List, Union, Dict, Callable
from datetime import datetime
from ..backtest.model import Order, TradeRecord

class OrderExecutor:
    """
    订单执行与导出模块
    支持将回测引擎生成的订单（Order）或交易记录（TradeRecord）直接下单并保存为交易指令文件。
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
        
        # 默认导出的交易列名映射
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

    def place_orders(
        self, 
        orders: Union[List[Order], List[TradeRecord]], 
        file_path: str = "orders.csv", 
        format: str = "csv", 
        **kwargs
    ) -> pd.DataFrame:
        """
        下单并直接导出下单列表文件
        """
        if not orders:
            raise ValueError("没有需要处理的下单记录")

        records = []
        for item in orders:
            if isinstance(item, Order):
                fund_code = item.fund_code
                direction = item.direction
                order_value = round(item.order_value, 2) if item.direction == "BUY" else 0.0
                order_shares = round(item.order_shares, 4) if item.direction == "SELL" else 0.0
                t_date = item.submit_date
            elif isinstance(item, TradeRecord):
                fund_code = item.fund_code
                direction = item.direction
                order_value = round(item.gross_amount, 2) if item.direction == "BUY" else 0.0
                order_shares = round(item.filled_shares, 4) if item.direction == "SELL" else 0.0
                t_date = item.submit_date
            else:
                raise TypeError("不支持的数据类型，必须为 Order 或 TradeRecord 列表")

            if isinstance(t_date, datetime):
                t_date_str = t_date.strftime("%Y%m%d")
            else:
                t_date_str = str(t_date) if t_date else datetime.now().strftime("%Y%m%d")

            records.append({
                "fund_code": self._process_code(fund_code),
                "direction": self.direction_mapping.get(direction, direction),
                "order_value": order_value,
                "order_shares": order_shares,
                "portfolio_id": self.portfolio_id,
                "asset_unit": self.asset_unit,
                "trade_date": t_date_str
            })

        df = pd.DataFrame(records)
        if df.empty:
            df = pd.DataFrame(columns=list(self.column_mapping.keys()))
            
        columns_to_keep = [k for k in self.column_mapping.keys() if k in df.columns]
        df = df[columns_to_keep].rename(columns=self.column_mapping)

        # 确保导出目录存在
        import os
        dir_name = os.path.dirname(file_path)
        if dir_name and not os.path.exists(dir_name):
            os.makedirs(dir_name, exist_ok=True)

        if format.lower() == "csv":
            encoding = kwargs.get("encoding", "gbk")
            df.to_csv(file_path, index=False, encoding=encoding)
        elif format.lower() in ["xlsx", "xls", "excel"]:
            df.to_excel(file_path, index=False)
        else:
            raise ValueError(f"不支持的导出格式: {format}")

        print(f"下单列表已成功导出到: {file_path}")
        return df
