import pandas as pd
import numpy as np
from typing import Dict
from .exceptions import AlignmentError

class DataAligner:

    @staticmethod
    def _proxy_mapping_interpolation(target_series: pd.Series, proxy_series: pd.Series) -> pd.Series:
        # 找到目标序列(低频)中真实存在的点
        valid_points = target_series.dropna()
        if len(valid_points) < 2:
            return target_series.ffill() # 数据太少，退化为前向填充

        result_series = target_series.copy()
        
        # 获取有效日期的索引序列
        valid_dates = valid_points.index
        
        # 遍历每一段区间 (T1 到 T2)
        for i in range(len(valid_dates) - 1):
            t1, t2 = valid_dates[i], valid_dates[i+1]
            
            v_t1, v_t2 = valid_points.loc[t1], valid_points.loc[t2]
            
            # 截取该区间的 proxy 序列，如果 proxy 在该区间缺失，跳过（后续由ffill兜底）
            sub_proxy = proxy_series.loc[t1:t2].dropna()
            if len(sub_proxy) < 2:
                continue
                
            p_t1, p_t2 = sub_proxy.iloc[0], sub_proxy.iloc[-1]
            if p_t1 <= 0 or p_t2 <= 0 or v_t1 <= 0 or v_t2 <= 0:
                continue # 避免对数运算报错
                
            # 计算区间的对数收益率
            log_ret_target = np.log(v_t2 / v_t1)
            log_ret_proxy = np.log(p_t2 / p_t1)
            
            # 计算对数收益率的残差 (Alpha)
            residual_log_ret = log_ret_target - log_ret_proxy
            
            # 计算该区间内的总天数 (交易日数量)
            n_days = len(sub_proxy) - 1
            if n_days == 0:
                continue
                
            # 将残差平均分配到每一天
            daily_alpha = residual_log_ret / n_days
            
            # 重构该区间内每日的净值
            # 算法：V(t) = V(t-1) * ( P(t)/P(t-1) ) * exp(daily_alpha)
            # 等价于计算累计日对数收益率后求指数
            daily_proxy_log_ret = np.log(sub_proxy / sub_proxy.shift(1)).fillna(0)
            adjusted_daily_log_ret = daily_proxy_log_ret + daily_alpha
            adjusted_daily_log_ret.iloc[0] = 0 # 起点t1收益率为0
            
            # 推算该区间每日的真实估算净值
            reconstructed_nav = v_t1 * np.exp(adjusted_daily_log_ret.cumsum())
            
            # 填补回原序列
            result_series.loc[sub_proxy.index] = reconstructed_nav

        return result_series.ffill()

    @classmethod
    def align_to_panel(
        cls,
        data_dict: Dict[str, pd.DataFrame], 
        target_col: str = 'adj_nav',
        freq: str = 'B', 
        method: str = 'ffill', 
        proxy_data: pd.Series = None
    ) -> pd.DataFrame:
        """
        生成对齐宽表。
        :param method: 'ffill'(前向填充), 'linear'(线性插值), 'proxy_mapping'(Proxy映射/Beta映射)
        :param proxy_data: 当 method 为 'proxy_mapping' 时，必须传入一个日频的pd.Series作为参考基准。
        """
        if not data_dict:
            raise AlignmentError("传入的数据字典为空")

        series_list = []
        for code, df in data_dict.items():
            if target_col not in df.columns:
                raise AlignmentError(f"基金 {code} 缺少目标列 {target_col}")
            series_list.append(df[target_col].rename(code))
        
        # 宽表外连接
        panel_df = pd.concat(series_list, axis=1).sort_index()

        # 生成目标时间轴（确保覆盖所有区间的工作日）
        start_dt = panel_df.index.min()
        end_dt = panel_df.index.max()
        target_idx = pd.date_range(start=start_dt, end=end_dt, freq=freq)

        # 重建索引，此时会产生大量 NaN
        aligned_df = panel_df.reindex(target_idx)

        # 执行重采样插值逻辑
        if method == 'ffill':
            aligned_df = aligned_df.ffill()
            
        elif method == 'linear':
            aligned_df = aligned_df.interpolate(method='linear').ffill()
            
        elif method == 'proxy_mapping':
            if proxy_data is None or not isinstance(proxy_data, pd.Series):
                raise AlignmentError("使用 'proxy_mapping' 方法必须提供有效的 proxy_data (pd.Series)")
            
            # 确保 Proxy 也覆盖目标时间轴，并填补Proxy的空缺
            proxy_series = proxy_data.reindex(target_idx).ffill()
            
            # 遍历每一个基金列，应用 Beta Mapping 平滑
            for col in aligned_df.columns:
                aligned_df[col] = cls._proxy_mapping_interpolation(aligned_df[col], proxy_series)
        else:
            raise AlignmentError(f"不支持的插值方法: {method}")

        return aligned_df