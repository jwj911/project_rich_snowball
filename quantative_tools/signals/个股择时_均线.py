"""
邢不行™️选股框架
Python股票量化投资课程

版权所有 ©️ 邢不行
微信: xbx8662

未经授权，不得复制、修改、或使用本代码的全部或部分内容。仅限个人学习用途，禁止商业用途。

Author: 邢不行
"""

import numpy as np
import pandas as pd
from typing import TYPE_CHECKING
from core.model.strategy_config import filter_series_by_range

if TYPE_CHECKING:
    from core.model.timing_signal import StockTiming

# 策略相关信息
STG_INTRO = {
    '策略直播': ['https://www.quantclass.cn/online-player/69904b73b8be468dca1032ee', ],
    '论坛帖子': [],
    '相关船队': ['https://bbs.quantclass.cn/category/176?search_ids=176'],
    '策略说明': '均线上方开仓，均线下方平仓',
    '使用案例': {
        "stock_timing_list": [
            {
                "name": "个股择时_均线",
                "factor_list": [
                    ('N日均价', True, 12, 1),
                ],
                "params": 0,
                "weight": 1,
                "period": "1H",
            }, ]
    }
}


def stock_signal(stock_timing: "StockTiming", stock_df: pd.DataFrame) -> pd.Series:
    """
    根据资金曲线，动态调整杠杆
    :param stock_timing: StockTiming实例
    :param stock_df: 因子面板数据（不会被修改）
    :return: 返回包含 leverage 的 Series
    """
    # ======================== 解析策略参数 ===========================
    ma_col = stock_timing.factor_list[0].col_name
    threshold = stock_timing.params

    # ======================== 计算偏离度 ===========================
    ma_price = stock_df[ma_col]
    bias = stock_df["收盘价_复权"] / ma_price - 1

    # ======================== 生成交易信号 ===========================
    # 初始化信号为 NaN
    signal = pd.Series(np.nan, index=stock_df.index)

    # 偏离度 > 阈值 → 做多信号 (1)
    signal[bias > threshold] = 1

    # 偏离度 < 阈值 → 空仓信号 (0)
    signal[bias < threshold] = 0

    # ======================== 信号后处理 ===========================
    # 按股票分组，前向填充信号（保持上一个有效信号）
    # 剩余缺失值填充为 0（默认空仓）
    signal = signal.ffill().fillna(0)

    return signal
