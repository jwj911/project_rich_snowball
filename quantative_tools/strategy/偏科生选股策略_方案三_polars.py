"""
邢不行™️选股框架
Python股票量化投资课程

版权所有 ©️ 邢不行
微信: xbx8662

未经授权，不得复制、修改、或使用本代码的全部或部分内容。仅限个人学习用途，禁止商业用途。

Author: 邢不行
"""

import pandas as pd
import polars as pl
from core.model.strategy_config import StrategyConfig
import numpy as np
import config as cfg

# 策略相关信息
STG_INTRO = {
    '策略直播': ['https://www.quantclass.cn/online-player/69c35903f174fd21cf1b8b3d'],
    '论坛帖子': [],
    '相关船队': ['https://bbs.quantclass.cn/category/180?search_ids=180'],
    '策略说明': """
    将因子分为5组，每组根据每个周期内各因子的ICIR值对因子进行加权，最后得到5个ICIR加权因子后等权选5只
    每个基础因子的权重参数代表该因子被分配到第几组，例如：
        G161被分配到第1组，则设置为'组合1'；
        PriceVol被分配到第2组，则设置为'组合2'；
        M日内N日新高次数被分配到第1组和第2组，则写两遍，例如：
            ("M日内N日新高次数", True, (30, 120), '组合1'),
            ("M日内N日新高次数", True, (30, 120), '组合2'),
    【未来收益】的权重参数是算ICIR均值的滚动周期数，例如：
        滚动50个周期计算ICIR均值，则填50
    【未来收益】的最后一个参数是换仓时间点，例如：
        如果是open换仓，则填'0930';
        如果是0955-0955换仓，则填'0955';
    """,
    '使用案例':
        {
            'name': '偏科生选股策略_方案三_polars',
            'hold_period': '5D',
            'offset_list': [0, 1, 2, 3, 4],
            'select_num': 5,
            'cap_weight': 1,
            'rebalance_time': 'open',
            'factor_list': [
                ("波动.G161", True, "", '组合1'),
                ("成长.营业收入单季同比增速", False, "", '组合1'),
                ("长期反转.M日内N日新高次数", True, (30, 120), '组合1'),
                ("短期反转.MaDisplaced", True, 20, '组合1'),
                ("估值.EP", False, "单季", '组合1'),
                ("规模.资金流买入占比", False, "非机构", '组合1'),

                ("波动.PriceVol", True, 20, '组合2'),
                ("成长.毛利率季度增加", False, "", '组合2'),
                ("长期反转.M日内N日新高次数", True, (30, 120), '组合2'),
                ("短期反转.MtmHcm", True, 20, '组合2'),
                ("估值.SP", False, "", '组合2'),
                ("规模.成交额Std", True, 5, '组合2'),

                ("波动.G167", True, "", '组合3'),
                ("成长.归母净利润同比增速", False, 60, '组合3'),
                ("长期反转.Mm", True, 20, '组合3'),
                ("短期反转.CoppAtr", True, 20, '组合3'),
                ("估值.捡烟蒂因子", True, "", '组合3'),
                ("规模.资金流买入占比", False, "非机构", '组合3'),

                ("波动.G187", True, "", '组合4'),
                ("成长.净利润单季同比", False, "", '组合4'),
                ("长期反转.Wc", True, 20, '组合4'),
                ("短期反转.MakV2", True, "", '组合4'),
                ("估值.企业价值倍数", True, "ttm", '组合4'),
                ("规模.Alpha95V2", True, 10, '组合4'),

                ("波动.G189", True, "", '组合5'),
                ("成长.归母净利润同比", False, "", '组合5'),
                ("长期反转.Trv", True, 20, '组合5'),
                ("短期反转.Ax10", True, (20, ""), '组合5'),
                ("估值.HML因子", False, "", '组合5'),
                ("规模.G144", False, "", '组合5'),

                ("未来收益", True, 5, 50, "0930")
            ],
            'filter_list': [
                ("近期停牌天数", 5, "val:==0", True),
                ("异常涨跌停状态", 5, "val:==0", True)
            ]
        }
}


def calc_select_factor(df, strategy: StrategyConfig) -> pd.DataFrame:
    """
    计算复合选股因子
    :param df: 整理好的数据，包含因子信息，并做过周期转换
    :param strategy: 策略配置
    :return: 返回过滤后的数据

    ### df 列说明
    包含基础列：  ['交易日期', '股票代码', '股票名称', '周频起始日', '月频起始日', '上市至今交易天数', '复权因子', '开盘价', '最高价',
                '最低价', '收盘价', '成交额', '是否交易', '流通市值', '总市值', '下日_开盘涨停', '下日_是否ST', '下日_是否交易',
                '下日_是否退市']
    以及config中配置好的，因子计算的结果列。

    ### strategy 数据说明
    - strategy.name: 策略名称
    - strategy.hold_period: 持仓周期
    - strategy.select_num: 选股数量
    - strategy.factor_name: 复合因子名称
    - strategy.factor_list: 选股因子列表
    - strategy.filter_list: 过滤因子列表
    - strategy.factor_columns: 选股+过滤因子的列名
    """

    # 获取因子的信息
    factor_info = {}  # 返回因子名和排序方式 {'波动.G167': True, '成长.营业收入单季同比增速': False, ……}
    group_factor_cols_dict = {}  # 返回分组信息，{'组合1': ['波动.G167', '成长.营业收入单季同比增速', ……]}
    for factor in strategy.factor_list:
        if '未来收益' not in factor.col_name:
            # 记录下config中的因子排序方式
            factor_info[factor.col_name] = factor.is_sort_asc
            # 记录该因子属于哪一组，将因子按config配置分组，factor.args 返回组合编号
            if factor.args not in group_factor_cols_dict:
                group_factor_cols_dict[factor.args] = []  # 按组合编号，新建一个列表
            group_factor_cols_dict[factor.args].append(factor.col_name)  # 将因子列名添加到dict中对应的组合列表中

    # 找到未来收益因子 ("未来收益", True, 5, 50, "0930"), param=5, args=50
    fret_factor = [fa for fa in strategy.factor_list if '未来收益' in fa.col_name][0]

    # =================================== polars处理代码 ==========================================
    # 转为polars格式
    pl_df = pl.from_pandas(df)

    # 计算全样本ICIR
    pl_df = cal_rank_ic_ir_polars(pl_df, factor_info, fret_factor, recall=fret_factor.args)

    # 按照IC对因子进行加权排名：每个因子用 排名分位 * ICIR
    for factor in factor_info.keys():
        pl_df = pl_df.with_columns([
            (pl.col(factor + '_排名') * pl.col(factor + '_RankICIR')).alias(factor + '_带权排名')
        ])

    # 计算每组的偏科生因子
    for group_num, group_factor_cols in group_factor_cols_dict.items():
        # 找到 _带权排名 的列名，并将其_带权排名 后缀去掉 后 判断是否再 group_factor_cols 中 group_factor_cols是原始列名
        weight_factor_cols = [col for col in pl_df.columns if
                              '_带权排名' in col and col.replace('_带权排名', '') in group_factor_cols]
        # 模拟pandas的min_count=1，当所有列都为null时，返回null
        has_valid = pl.sum_horizontal([pl.col(col).is_not_null() for col in weight_factor_cols]) > 0
        pl_df = pl_df.with_columns([
            pl.when(has_valid)
            .then(pl.sum_horizontal(weight_factor_cols, ignore_nulls=True))
            .otherwise(None)
            .alias(f'ICIR加权因子_{group_num}')
        ])

    # 找到所有 ICIR加权因子_组合5 等因子 并相加作为复合因子
    pianke_factor_cols = [col for col in pl_df.columns if 'ICIR加权因子' in col]
    # 模拟pandas的min_count=1，当所有列都为null时，返回null
    has_valid = pl.sum_horizontal([pl.col(col).is_not_null() for col in pianke_factor_cols]) > 0
    pl_df = pl_df.with_columns([
        pl.when(has_valid)
        .then(pl.sum_horizontal(pianke_factor_cols, ignore_nulls=True))
        .otherwise(None)
        .alias('复合因子')
    ])

    # 输出pandas格式
    df = pl_df.to_pandas()

    return df


def cal_rank_ic_ir_polars(all_data, factor_info, fret_factor, recall=50):
    """
    计算全样本ICIR - Polars实现
    """

    # 1. 对所有股票未来收益排名，模拟 Pandas 的 default (average) + pct=True
    all_data = all_data.with_columns([
        pl.when(pl.len().over("交易日期") > 0)  # 只要有数据就算
        .then(
            # 统一使用pandas的计算分位数排名: rank / count（非空值数量），且pandas默认method="average"
            pl.col(fret_factor.col_name).rank(method="average", descending=True).over("交易日期") / pl.col(fret_factor.col_name).count().over("交易日期")
        )
        .otherwise(None)
        .alias("未来收益_排名")
    ])

    # 2. 计算所有因子的排名，模拟 Pandas 的 default (average) + pct=True
    for factor, ascending in factor_info.items():
        all_data = all_data.with_columns([
            pl.when(pl.len().over("交易日期") > 0)  # 只要有数据就算
            .then(
                # 统一使用pandas的计算分位数排名: rank / count（非空值数量），且pandas默认method="average"
                pl.col(factor).rank(method="average", descending=not ascending).over("交易日期") / pl.col(factor).count().over("交易日期")
            )
            .otherwise(None)
            .alias(factor + '_排名')
        ])

    # 3. 按日期分组计算IC [*将列表展开，变成单独的表达式]，
    # 备注：最后4天corr为nan，因为未来数据数据都为1，但pandas会赋最小值，不会是nan
    ic_ir = (
        all_data
        .group_by("交易日期")  # Polars用 group_by 每个日期为一组，【如果用over，保持原始行数不变】
        .agg([
            *[pl.corr(
                pl.col(factor + '_排名'),
                pl.col("未来收益_排名"),
            ).alias(factor + '_RankIC')
              for factor in factor_info.keys()]
        ]).sort("交易日期")  # 添加这行来按日期排序，否则polars计算agg后顺序会混乱
    )

    # 4. 计算ICIR
    for factor in factor_info.keys():
        ic_ir = ic_ir.with_columns([
            # 滚动平均，剔除np.nan，在polars中，np.nan和None是有区别的，np.nan在计算中不会被忽略，导致与pandas的结果不一致
            pl.col(factor + '_RankIC').fill_nan(None)
            .rolling_mean(window_size=recall, min_periods=int(1 / 2 * recall))
            .alias(factor + '_RankIC_mean'),
            # 滚动标准差，剔除np.nan，在polars中，np.nan和None是有区别的，np.nan在计算中不会被忽略，导致与pandas的结果不一致
            pl.col(factor + '_RankIC').fill_nan(None)
            .rolling_std(window_size=recall, min_periods=int(1 / 2 * recall))
            .alias(factor + '_RankIC_std')
        ])

        # 计算ICIR
        ic_ir = ic_ir.with_columns([
            (pl.col(factor + '_RankIC_mean') /
             # 当std为0，用极小值替代，否则就用原始数据
             pl.when(pl.col(factor + '_RankIC_std') == 0).then(1e-8).otherwise(pl.col(factor + '_RankIC_std')))
            .alias(factor + '_RankICIR')
        ])

    # 4. 清理中间列
    ic_ir = ic_ir.drop([col for col in ic_ir.columns if '_RankIC_' in col])
    ic_ir = ic_ir.drop([col for col in ic_ir.columns if col.endswith('_RankIC')])
    ic_cols = [col for col in ic_ir.columns if 'IC' in col]

    # 5. 移动ICIR（避免未来函数）
    for col in ic_cols:
        ic_ir = ic_ir.with_columns([
            pl.col(col)
            .shift(fret_factor.param)
            .alias(col)  # 建议添加，语义更明确，实际效果相同，polars核心是不可变性，绝大多数场景需添加alias
        ])

    # 6. 合并回原数据
    result = all_data.join(ic_ir, on="交易日期", how="left")

    return result
