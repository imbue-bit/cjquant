import pandas as pd
from typing import Dict, List, Optional
from .model import ExposureResult

class HBASymbolResolver:
    """
    持仓数据解析器。用户需提供一个 DataFrame：
    columns=['fund_code', 'stock_code', 'weight', 'industry', 'style']
    """
    def __init__(self, holdings_df: pd.DataFrame):
        self.holdings = holdings_df

    def get_fund_exposure(self, fund_code: str, category_col: str = 'industry') -> Dict[str, float]:
        """按类别归集某只基金的底层暴露"""
        fund_data = self.holdings[self.holdings['fund_code'] == fund_code]
        if fund_data.empty:
            return {}
        
        # 归一化权重 (防止公开披露的前十大加总不等于1的情况)
        total_weight = fund_data['weight'].sum()
        exposure = fund_data.groupby(category_col)['weight'].sum() / total_weight
        return exposure.to_dict()

class HBAEngine:
    def __init__(self, resolver: HBASymbolResolver):
        self.resolver = resolver

    def look_through_portfolio(self, weights: Dict[str, float], category: str = 'industry') -> ExposureResult:
        """
        对整个组合进行穿透分析
        :param weights: 组合权重 {fund_code: weight}
        """
        total_exposure = {}
        
        for fund_code, fund_w in weights.items():
            fund_exp = self.resolver.get_fund_exposure(fund_code, category)
            for cat, exp_val in fund_exp.items():
                total_exposure[cat] = total_exposure.get(cat, 0) + exp_val * fund_w
                
        return ExposureResult(
            fund_code="PORTFOLIO",
            analysis_date="LATEST",
            method="HBA",
            exposures=total_exposure
        )