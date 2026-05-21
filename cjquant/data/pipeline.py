import pandas as pd
from typing import Union, List, Dict, Optional
from .providers.public import PublicFundProvider
from .providers.private import PrivateFundLocalProvider
from .aligner import DataAligner

class DataPipeline:
    def __init__(self):
        self.public_provider = PublicFundProvider()
        
    def get_public_fund(self, fund_code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        return self.public_provider.fetch(fund_code, start_date, end_date)

    def get_private_fund(self, fund_code: str, file_path: str, **kwargs) -> pd.DataFrame:
        provider = PrivateFundLocalProvider(file_path=file_path, column_mapping=kwargs.get('column_mapping'))
        return provider.fetch(fund_code, kwargs.get('start_date'), kwargs.get('end_date'))

    def create_universe_panel(
        self, 
        public_codes: List[str] = None, 
        private_configs: Dict[str, str] = None, 
        start_date: str = None,
        freq: str = 'B',
        resample_method: str = 'ffill',
        proxy_fund_code: str = None # 如果使用 proxy_mapping，可以指定一只公募指数基金做基准
    ) -> pd.DataFrame:
        data_pool = {}
        
        if public_codes:
            for code in public_codes:
                data_pool[code] = self.get_public_fund(code, start_date)
                
        if private_configs:
            for code, path in private_configs.items():
                df = self.get_private_fund(code, path, start_date=start_date)
                data_pool[code] = df

        proxy_series = None
        if resample_method == 'proxy_mapping':
            if not proxy_fund_code:
                raise ValueError("使用 proxy_mapping 时必须提供 proxy_fund_code (例如: 000300.OF 沪深300基准)")
            
            proxy_df = self.get_public_fund(proxy_fund_code, start_date)
            proxy_series = proxy_df['adj_nav']

        return DataAligner.align_to_panel(
            data_dict=data_pool, 
            target_col='adj_nav', 
            freq=freq,
            method=resample_method,
            proxy_data=proxy_series
        )

data_api = DataPipeline()