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
    '策略说明': '动量超跌且股价处于长线低位开仓，动量过热且股价处于长线高位平仓',
    '使用案例': {
        "stock_timing_list": [
            {
                "name": "个股择时_CCIQ",
                "factor_list": [
                    ('CCI', True, 40, 1),
                    ('N日最高收盘价', True, 250, 1),
                    ('N日最低收盘价', True, 250, 1),
                ],
                "params": 40,
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

    cci_col = stock_timing.factor_list[0].col_name
    max_col = stock_timing.factor_list[1].col_name
    min_col = stock_timing.factor_list[2].col_name

    # --- 0. 参数解包 ---
    # 尝试解包参数，如果用户只传了一个数字，则使用默认值
    rank_window = stock_timing.params

    # --- 2. 计算 CCI 的 Rank (动量强度) ---
    # 使用 pandas 原生 rolling rank 优化速度
    # pct=True 直接得到 0~1 的百分位
    cci_rank = stock_df[cci_col].rolling(rank_window).rank(pct=True)

    # 0 代表最低，1 代表最高
    price_pos = (stock_df['收盘价_复权'] - stock_df[min_col]) / (stock_df[max_col] - stock_df[min_col] + 1e-8)

    # --- 生成信号 ---
    # 初始化信号为 NaN
    signal = pd.Series(np.nan, index=stock_df.index)

    # 【做空/清仓逻辑】：
    # 动量过热 (Rank > 0.9) 且 股价处于长线高位 (Pos > 0.9)
    sell_condition = (cci_rank > 0.9) & (price_pos > 0.9)

    # 【做多/开仓逻辑】：
    # 动量超跌 (Rank < 0.1) 且 股价处于长线低位 (Pos < 0.1)
    buy_condition = (cci_rank < 0.1) & (price_pos < 0.1)

    # 赋值信号
    # 注意：这里 sell 赋值为 0，代表空仓；如果你想做反向开空，可以改为 -1
    signal.loc[buy_condition] = 1
    signal.loc[sell_condition] = 0

    # --- 5. 填充持仓状态 ---
    # ffill 实现持仓延续
    signal = signal.ffill().fillna(0)

    return signal
