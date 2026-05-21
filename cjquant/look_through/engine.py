from typing import Dict, Union
import pandas as pd
from .hba_engine import HBAEngine, HBASymbolResolver
from .rbsa_engine import RBSAEngine

class LookThroughAnalyzer:
    def __init__(self, method: str = 'RBSA', **kwargs):
        self.method = method
        if method == 'HBA':
            # kwargs 需要包含 holdings_df
            resolver = HBASymbolResolver(kwargs.get('holdings_df'))
            self.engine = HBAEngine(resolver)
        else:
            # kwargs 需要包含 factor_returns
            self.engine = RBSAEngine(kwargs.get('factor_returns'))

    def run(self, data: Union[pd.Series, Dict[str, float]], **kwargs):
        """
        执行分析。
        如果 method=RBSA, data 为基金收益率序列。
        如果 method=HBA, data 为组合权重字典。
        """
        if self.method == 'RBSA':
            return self.engine.analyze_fund(data, rolling_window=kwargs.get('window', 60))
        else:
            return self.engine.look_through_portfolio(data, category=kwargs.get('category', 'industry'))