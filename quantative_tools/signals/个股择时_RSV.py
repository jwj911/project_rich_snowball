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
    '策略直播': ['https://www.quantclass.cn/online-player/69d4beb6c8a11048adbafb42',
                'https://www.quantclass.cn/online-player/69e1cc7e14a864cdf9812e9d'],
    '论坛帖子': [],
    '相关船队': ['https://bbs.quantclass.cn/category/176?search_ids=176'],
    '策略说明': 'RSV处于“低位”开仓，RSV处于“高位”平仓',
    '使用案例': {
        "stock_timing_list": [
            {
                "name": "个股择时_RSV",
                "factor_list": [
                    ('N日最高收盘价', True, 250, 1),
                    ('N日最低收盘价', True, 250, 1),
                ],
                "params": '',
                "weight": 1,
                "period": "1H",
            },
        ]
    }
}


def stock_signal(stock_timing: "StockTiming", stock_df: pd.DataFrame) -> pd.Series:
    """
    根据资金曲线，动态调整杠杆
    :param stock_timing: StockTiming实例
    :param stock_df: 因子面板数据（不会被修改）
    :return: 返回包含 leverage 的 Series
    """

    max_col = stock_timing.factor_list[0].col_name
    min_col = stock_timing.factor_list[1].col_name

    # --- 1. 计算指标 (保持原逻辑不变) ---
    stock_df['RSV'] = (stock_df['收盘价_复权'] - stock_df[min_col]) / (
            stock_df[max_col] - stock_df[min_col] + 1e-8) * 100

    # --- 2. 定义反转阈值 ---
    # 通常 RSV 的反转阈值设为 10 和 90
    oversold_threshold = 10  # 超卖区（小于此值说明跌过头了）
    overbought_threshold = 90  # 超买区（大于此值说明涨过头了）

    # --- 3. 生成反转信号 ---
    signal = pd.Series(np.nan, index=stock_df.index)

    # 【买入条件】：“低位” (RSV < 10)
    buy_condition = (stock_df['RSV'] < oversold_threshold)

    # 【卖出条件】：“高位” (RSV > 90)
    sell_condition = (stock_df['RSV'] > overbought_threshold)

    signal.loc[buy_condition] = 1  # 反转做多
    signal.loc[sell_condition] = 0  # 反转平仓/做空

    # --- 4. 填充持仓状态 ---
    # 只有触发买入才持仓，触发卖出就空仓
    signal = signal.ffill().fillna(0)

    return signal
