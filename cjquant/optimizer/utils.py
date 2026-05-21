import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

def calculate_shrunk_covariance(returns: pd.DataFrame) -> pd.DataFrame:
    """
    解决场外基金样本量不足导致的协方差矩阵奇异值问题。
    """
    cleaned_returns = returns.dropna(how='all').fillna(0)
    lw = LedoitWolf()
    lw.fit(cleaned_returns)
    return pd.DataFrame(lw.covariance_, index=returns.columns, columns=returns.columns)

def calculate_expected_returns(returns: pd.DataFrame, method: str = 'capm') -> pd.Series:
    if method == 'mean':
        return returns.mean() * 252 # 年化
    return np.exp(np.log1p(returns).mean() * 252) - 1