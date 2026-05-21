import pandas as pd
import numpy as np
import chardet
from typing import Optional, Dict
from .base import BaseProvider
from ..schema import FundDataSchema
from ..exceptions import DataFormatError

class PrivateFundLocalProvider(BaseProvider):
    def __init__(self, file_path: str, column_mapping: Optional[Dict[str, str]] = None):
        self.file_path = file_path
        self.column_mapping = column_mapping or {
            '日期': 'date', '净值日期': 'date', '截止日期': 'date',
            '单位净值': 'unit_nav', '累计净值': 'acc_nav', '复权净值': 'adj_nav'
        }

    def _read_file(self) -> pd.DataFrame:
        if self.file_path.endswith('.csv'):
            with open(self.file_path, 'rb') as f:
                result = chardet.detect(f.read(10000))
            encoding = result['encoding'] or 'utf-8'
            # 处理私募排排网导出的千分位格式
            return pd.read_csv(self.file_path, encoding=encoding, thousands=',')
        elif self.file_path.endswith(('.xls', '.xlsx')):
            return pd.read_excel(self.file_path)
        else:
            raise DataFormatError("仅支持 .csv, .xls, .xlsx 文件")

    def fetch(self, fund_code: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> pd.DataFrame:
        df = self._read_file()
        
        df.columns = [str(c).strip() for c in df.columns]
        df.rename(columns=self.column_mapping, inplace=True)
        
        if 'date' not in df.columns:
            raise DataFormatError(f"无法找到日期列，可用列: {df.columns.tolist()}")

        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df.dropna(subset=['date'], inplace=True) # 踢掉表尾的说明性文字等脏数据
        df.set_index('date', inplace=True)

        if 'unit_nav' not in df.columns and 'acc_nav' in df.columns:
            df['unit_nav'] = df['acc_nav']
        elif 'unit_nav' not in df.columns:
            raise DataFormatError(f"私募文件 {self.file_path} 缺失净值数据列。")

        if 'acc_nav' not in df.columns:
            df['acc_nav'] = df['unit_nav']

        # 如果没有提供复权净值，采用单位净值的收益率近似推算 (私募分红极少，基本成立)
        if 'adj_nav' not in df.columns:
            df = df.sort_index()
            returns = df['unit_nav'].pct_change().fillna(0)
            df['adj_nav'] = df['unit_nav'].iloc[0] * (1 + returns).cumprod()

        df[FundDataSchema.CODE] = fund_code

        standard_df = pd.DataFrame({
            FundDataSchema.CODE: df[FundDataSchema.CODE],
            FundDataSchema.UNIT_NAV: df['unit_nav'],
            FundDataSchema.ACC_NAV: df['acc_nav'],
            FundDataSchema.ADJ_NAV: df['adj_nav']
        })

        if start_date:
            standard_df = standard_df[standard_df.index >= pd.to_datetime(start_date)]
        if end_date:
            standard_df = standard_df[standard_df.index <= pd.to_datetime(end_date)]

        return FundDataSchema.validate(standard_df)