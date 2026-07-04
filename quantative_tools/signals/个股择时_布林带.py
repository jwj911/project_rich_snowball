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
    '策略说明': '突破布林带上轨做多，突破布林带下轨平仓',
    '使用案例': {
        "stock_timing_list": [
            {
                "name": "个股择时_布林带",
                "factor_list": [
                    ('N日均价', True, 8, 1),
                    ('N日收盘价标准差', True, 8, 1),
                ],
                "params": 0.5,
                "weight": 1,
                "period": "1H",
            }, ]
    }
}


def stock_signal(stock_timing: "StockTiming", stock_df: pd.DataFrame) -> pd.Series:
    """
    根据资金曲线，动态调整杠杆
    :param stock_timing: StockTiming实例
    :param stock_df: 因子面板数据
    :return: 返回包含 leverage 的数据
    """

    # ======================== 解析策略参数 ===========================
    ma = stock_timing.factor_list[0].col_name
    std = stock_timing.factor_list[1].col_name
    std_mult = stock_timing.params

    # ======================== 生成交易信号 ===========================
    boll_upper = stock_df[ma] + std_mult * stock_df[std]
    boll_lower = stock_df[ma] - std_mult * stock_df[std]

    # 创建一个新的Series用于存储信号
    signal = pd.Series(np.nan, index=stock_df.index)

    # 价格在上轨上方给1
    signal.loc[stock_df['收盘价_复权'] > boll_upper] = 1

    # 价格在下轨下方给0
    signal.loc[stock_df['收盘价_复权'] < boll_lower] = 0

    # ======================== 信号后处理 ===========================
    # 按股票分组，前向填充信号（保持上一个有效信号）
    # 剩余缺失值填充为 0（默认空仓）
    signals = signal.ffill().fillna(0)

    return signals
