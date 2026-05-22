import pandas as pd
import time
import logging
from typing import Optional
from .base import BaseProvider
from ..schema import FundDataSchema
from ..exceptions import DataFetchError

import akshare as ak 

logger = logging.getLogger(__name__)

class PublicFundProvider(BaseProvider):
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _get_raw_data(self, fund_code: str, indicator: str) -> pd.DataFrame:
        for attempt in range(self.max_retries):
            try:
                try:
                    df = ak.fund_open_fund_info_em(symbol=fund_code, indicator=indicator)
                except TypeError:
                    df = ak.fund_open_fund_info_em(fund=fund_code, indicator=indicator)
                if df is None or df.empty:
                    raise ValueError(f"接口返回空数据 (Indicator: {indicator})")
                return df
            except Exception as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"代码 {fund_code} 连续 {self.max_retries} 次获取 {indicator} 失败: {str(e)}")
                    raise DataFetchError(f"获取公募数据失败: {fund_code}")
                time.sleep(self.retry_delay)
        return pd.DataFrame()

    def fetch(self, fund_code: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        df_unit = self._get_raw_data(fund_code, "单位净值走势")
        df_acc = self._get_raw_data(fund_code, "累计净值走势")
        
        df_unit['date'] = pd.to_datetime(df_unit['净值日期'])
        df_acc['date'] = pd.to_datetime(df_acc['净值日期'])
        
        df = pd.merge(
            df_unit[['date', '单位净值', '日增长率']], 
            df_acc[['date', '累计净值']], 
            on='date', 
            how='outer'
        ).set_index('date').sort_index()

        df['累计净值'] = df['累计净值'].fillna(df['单位净值'])
        df['日增长率'] = pd.to_numeric(df['日增长率'], errors='coerce').fillna(0.0)

        returns = df['日增长率'] / 100.0
        base_nav = df['累计净值'].dropna().iloc[0] if not df['累计净值'].dropna().empty else 1.0
        df[FundDataSchema.ADJ_NAV] = base_nav * (1 + returns).cumprod()

        standard_df = pd.DataFrame({
            FundDataSchema.CODE: fund_code,
            FundDataSchema.UNIT_NAV: df['单位净值'],
            FundDataSchema.ACC_NAV: df['累计净值'],
            FundDataSchema.ADJ_NAV: df[FundDataSchema.ADJ_NAV]
        })

        if start_date:
            standard_df = standard_df[standard_df.index >= pd.to_datetime(start_date)]
        if end_date:
            standard_df = standard_df[standard_df.index <= pd.to_datetime(end_date)]

        return FundDataSchema.validate(standard_df)