import pandas as pd
import numpy as np
from .exceptions import DataFormatError

class FundDataSchema:
    DATE = 'date'
    CODE = 'fund_code'
    UNIT_NAV = 'unit_nav'       
    ACC_NAV = 'acc_nav'         
    ADJ_NAV = 'adj_nav'         

    @classmethod
    def validate(cls, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            raise DataFormatError("输入的数据集为空。")

        required_cols = [cls.CODE, cls.UNIT_NAV, cls.ACC_NAV, cls.ADJ_NAV]
        
        if df.index.name != cls.DATE:
            if cls.DATE in df.columns:
                df = df.set_index(cls.DATE)
            else:
                raise DataFormatError(f"DataFrame 必须包含 '{cls.DATE}' 列或以此作为索引")
        
        df.index = pd.to_datetime(df.index).tz_localize(None)
        
        for col in required_cols:
            if col not in df.columns:
                raise DataFormatError(f"缺失标准列: {col}")
                
        for col in [cls.UNIT_NAV, cls.ACC_NAV, cls.ADJ_NAV]:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        df = df.dropna(subset=[cls.UNIT_NAV, cls.ACC_NAV, cls.ADJ_NAV])
        df = df[df[cls.UNIT_NAV] > 0].copy()
        
        df = df[~df.index.duplicated(keep='last')]
        
        df = df.sort_index() 
        
        return df[required_cols]