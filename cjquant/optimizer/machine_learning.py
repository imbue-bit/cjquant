import pandas as pd
import numpy as np
from scipy.cluster.hierarchy import linkage
from .base import BaseOptimizer

class HRPOptimizer(BaseOptimizer):
    """
    层次风险平价
    基于机器学习聚类原理，将相似的基金归类，并在类间分配风险。
    """
    def optimize(self) -> pd.Series:
        returns = self.returns.fillna(0)
        corr = returns.corr().values
        # 1. 距离矩阵计算 (基于相关系数)
        dist = np.sqrt(0.5 * (1 - corr))
        
        # 2. 聚类 (单联动聚类)
        link = linkage(dist, 'single')
        
        # 3. 递归二分分配权重 (Quasi-Diagonalization)
        sort_ix = self._get_quasi_diag(link)
        ordered_assets = [self.assets[i] for i in sort_ix]
        weights = pd.Series(1.0, index=ordered_assets)
        
        self._recursive_bisection(weights, sort_ix)
        return self._validate_weights(weights.values)

    def _get_quasi_diag(self, link):
        """递归获取类对角化顺序"""
        return list(map(int, self._recursive_cluster_order(link, 2 * self.num_assets - 2)))

    def _recursive_cluster_order(self, link, idx):
        if idx < self.num_assets:
            return [idx]
        left = int(link[idx - self.num_assets, 0])
        right = int(link[idx - self.num_assets, 1])
        return self._recursive_cluster_order(link, left) + self._recursive_cluster_order(link, right)

    def _recursive_bisection(self, weights, sort_ix):
        """递归二分分配权重逻辑"""
        if len(sort_ix) <= 1:
            return
        
        # 将当前资产列表二分
        mid = len(sort_ix) // 2
        left_ix = sort_ix[:mid]
        right_ix = sort_ix[mid:]
        
        # 计算左/右簇的方差，分配权重比例
        v_left = self._get_cluster_var(left_ix)
        v_right = self._get_cluster_var(right_ix)
        
        alpha = 1 - v_left / (v_left + v_right)
        
        weights.iloc[left_ix] *= alpha
        weights.iloc[right_ix] *= (1 - alpha)
        
        self._recursive_bisection(weights, left_ix)
        self._recursive_bisection(weights, right_ix)

    def _get_cluster_var(self, indices):
        """计算子簇的逆方差权重风险"""
        sub_cov = self.returns.iloc[:, indices].cov().fillna(0).values
        inv_diag = 1.0 / np.diag(sub_cov)
        inv_diag[np.isinf(inv_diag)] = 0
        w = inv_diag / np.sum(inv_diag)
        return np.dot(w.T, np.dot(sub_cov, w))