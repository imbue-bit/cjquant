import numpy as np
import pandas as pd
from scipy.optimize import minimize
from typing import List, Dict
from .model import ExposureResult

class RBSAEngine:
    """
    Returns-Based Style Analysis (Sharpe's Method)
    """
    def __init__(self, factor_returns: pd.DataFrame):
        """
        :param factor_returns: 因子收益率矩阵 (T x K), 如 沪深300, 创业板指, 中证全债 等
        """
        self.factors = factor_returns.dropna()
        self.factor_names = self.factors.columns.tolist()

    def _objective(self, w, factor_matrix, target_ret):
        """最小化残差平方和"""
        pred_ret = np.dot(factor_matrix, w)
        return np.sum((target_ret - pred_ret)**2)

    def analyze_fund(self, fund_returns: pd.Series, rolling_window: int = None) -> ExposureResult:
        """
        对单只基金进行回归分析
        :param rolling_window: 如果提供，则只取最近 N 天的数据进行拟合
        """
        # 对齐数据
        common_idx = self.factors.index.intersection(fund_returns.index)
        if rolling_window:
            common_idx = common_idx[-rolling_window:]
            
        y = fund_returns.loc[common_idx].values
        X = self.factors.loc[common_idx].values
        
        num_factors = X.shape[1]
        initial_w = np.array([1.0 / num_factors] * num_factors)
        
        # 约束条件：Sum(w) = 1
        cons = ({'type': 'eq', 'fun': lambda x: np.sum(x) - 1.0})
        # 边界条件：w >= 0 (不允许做空因子)
        bounds = [(0, 1) for _ in range(num_factors)]
        
        res = minimize(
            self._objective, 
            initial_w, 
            args=(X, y), 
            method='SLSQP', 
            constraints=cons, 
            bounds=bounds
        )
        
        # 计算 R-Squared (解释度)
        y_pred = np.dot(X, res.x)
        r_sq = 1 - np.sum((y - y_pred)**2) / np.sum((y - np.mean(y))**2)
        
        exposures = dict(zip(self.factor_names, res.x))
        
        return ExposureResult(
            fund_code=str(fund_returns.name),
            analysis_date=str(common_idx[-1]),
            method="RBSA",
            exposures=exposures,
            r_squared=r_sq
        )