from abc import ABC, abstractmethod
import pandas as pd
from typing import Optional

class BaseProvider(ABC):
    @abstractmethod
    def fetch(self, fund_code: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        """必须返回符合 FundDataSchema 的 DataFrame"""
        raise NotImplementedError("子类必须实现 fetch 方法")