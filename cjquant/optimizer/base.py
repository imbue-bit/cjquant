import pandas as pd
import numpy as np

class BaseOptimizer:
    def __init__(self, returns: pd.DataFrame):
        self.returns = returns
        self.assets = list(returns.columns)
        self.num_assets = len(self.assets)

    def _validate_weights(self, weights) -> pd.Series:
        w = np.array(weights).flatten()
        sum_w = np.sum(w)
        if sum_w > 0:
            w = w / sum_w
        return pd.Series(w, index=self.assets)
