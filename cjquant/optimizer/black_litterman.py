import numpy as np
import pandas as pd
from .base import BaseOptimizer
from .utils import calculate_shrunk_covariance

class BlackLittermanOptimizer(BaseOptimizer):
    """
    Black-Litterman 优化器
    将市场均衡权重 (Prior) 与 投资者主观观点 (Views) 融合。
    """
    def __init__(self, returns: pd.DataFrame, 
                 pi: pd.Series,         # 市场先验预期收益率 (均衡收益率)
                 tau: float = 0.05):    # 对先验的置信度
        super().__init__(returns)
        self.cov = calculate_shrunk_covariance(returns).values
        self.pi = pi.values
        self.tau = tau

    def optimize(self, 
                 Q: np.ndarray, # 观点收益率 (Vector of views)
                 P: np.ndarray, # 观点矩阵 (Pick matrix)
                 Omega: np.ndarray = None # 观点的不确定性矩阵
                 ) -> pd.Series:
        """
        Posterior E[R] = [ (tau*Sigma)^-1 + P'*Omega^-1*P ]^-1 * [ (tau*Sigma)^-1*Pi + P'*Omega^-1*Q ]
        """
        sigma = self.cov
        if Omega is None:
            # 默认使用 Idzorek 简化法，将观点不确定性设为观点投影下的方差
            Omega = np.diag(np.diag(P @ (self.tau * sigma) @ P.T))

        # 计算后验预期收益率
        term1 = np.linalg.inv(np.linalg.inv(self.tau * sigma) + P.T @ np.linalg.inv(Omega) @ P)
        term2 = np.linalg.inv(self.tau * sigma) @ self.pi + P.T @ np.linalg.inv(Omega) @ Q
        posterior_expected_ret = term1 @ term2
        
        # 按预期收益率正向分配
        weights = np.linalg.inv(sigma) @ posterior_expected_ret
        weights = weights / np.sum(np.abs(weights)) # 允许一定程度的归一化
        
        return self._validate_weights(weights)