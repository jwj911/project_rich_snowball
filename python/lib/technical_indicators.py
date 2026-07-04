"""后端技术指标计算库。

基于纯 numpy/pandas 实现，无需 talib 依赖。
输入为 pandas DataFrame，列名：open, high, low, close, volume, amount。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    """简单移动平均线。"""
    return series.rolling(window=window, min_periods=1).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    """指数移动平均线。"""
    return series.ewm(span=window, adjust=False, min_periods=1).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """相对强弱指数 (RSI)。"""
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain, index=series.index).rolling(window=window, min_periods=1).mean()
    avg_loss = pd.Series(loss, index=series.index).rolling(window=window, min_periods=1).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    rsi_val = 100 - (100 / (1 + rs))
    return pd.Series(rsi_val, index=series.index)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD 指标。返回 DIF, DEA, MACD 柱状线。"""
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    dif = ema_fast - ema_slow
    dea = ema(dif, signal)
    macd_bar = (dif - dea) * 2
    return pd.DataFrame({
        "dif": dif,
        "dea": dea,
        "macd": macd_bar,
    }, index=series.index)


def bollinger(series: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """布林带 (BOLL)。返回 中轨, 上轨, 下轨。"""
    mid = sma(series, window)
    std = series.rolling(window=window, min_periods=1).std(ddof=0)
    upper = mid + num_std * std
    lower = mid - num_std * std
    return pd.DataFrame({
        "mid": mid,
        "upper": upper,
        "lower": lower,
    }, index=series.index)


def kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """KDJ 随机指标。输入需含 high, low, close。"""
    low_list = df["low"].rolling(window=n, min_periods=1).min()
    high_list = df["high"].rolling(window=n, min_periods=1).max()
    rsv = (df["close"] - low_list) / (high_list - low_list + 1e-10) * 100

    k = rsv.ewm(alpha=1/m1, adjust=False, min_periods=1).mean()
    d = k.ewm(alpha=1/m2, adjust=False, min_periods=1).mean()
    j = 3 * k - 2 * d

    return pd.DataFrame({
        "k": k,
        "d": d,
        "j": j,
    }, index=df.index)


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """平均真实波幅 (ATR)。输入需含 high, low, close。"""
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=window, min_periods=1).mean()


def cci(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """顺势指标 (CCI)。输入需含 high, low, close。"""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(window=window, min_periods=1).mean()
    md = tp.rolling(window=window, min_periods=1).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    cci_val = (tp - sma_tp) / (0.015 * md + 1e-10)
    return pd.Series(cci_val, index=df.index)


def obv(df: pd.DataFrame) -> pd.Series:
    """能量潮 (OBV)。输入需含 close, volume。"""
    direction = np.where(df["close"] > df["close"].shift(1), 1, -1)
    direction[0] = 0
    volume = df["volume"].fillna(0).values
    obv_val = np.cumsum(direction * volume)
    return pd.Series(obv_val, index=df.index)


def adx_dmi(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """平均趋向指数 (ADX) + DMI。输入需含 high, low, close。"""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr_val = tr.rolling(window=window, min_periods=1).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(window=window, min_periods=1).mean() / (atr_val + 1e-10)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(window=window, min_periods=1).mean() / (atr_val + 1e-10)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    adx = dx.rolling(window=window, min_periods=1).mean()

    return pd.DataFrame({
        "plus_di": plus_di,
        "minus_di": minus_di,
        "adx": adx,
    }, index=df.index)


def volume_ratio(df: pd.DataFrame, short: int = 5, long: int = 20) -> pd.Series:
    """成交量比率：短期均量 / 长期均量。输入需含 volume。"""
    short_vol = df["volume"].rolling(window=short, min_periods=1).mean()
    long_vol = df["volume"].rolling(window=long, min_periods=1).mean()
    return short_vol / (long_vol + 1e-10)


def williams_r(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """威廉指标 (WR)。输入需含 high, low, close。"""
    highest_high = df["high"].rolling(window=window, min_periods=1).max()
    lowest_low = df["low"].rolling(window=window, min_periods=1).min()
    wr = (highest_high - df["close"]) / (highest_high - lowest_low + 1e-10) * -100
    return pd.Series(wr, index=df.index)


def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算所有技术指标，返回合并后的 DataFrame。"""
    close = df["close"]

    # 均线
    for w in [5, 10, 20, 60, 120, 250]:
        df[f"sma{w}"] = sma(close, w)
        df[f"ema{w}"] = ema(close, w)

    # RSI
    df["rsi6"] = rsi(close, 6)
    df["rsi12"] = rsi(close, 12)
    df["rsi24"] = rsi(close, 24)

    # MACD
    macd_df = macd(close)
    df["macd_dif"] = macd_df["dif"]
    df["macd_dea"] = macd_df["dea"]
    df["macd_bar"] = macd_df["macd"]

    # BOLL
    boll_df = bollinger(close)
    df["boll_mid"] = boll_df["mid"]
    df["boll_upper"] = boll_df["upper"]
    df["boll_lower"] = boll_df["lower"]

    # KDJ
    kdj_df = kdj(df)
    df["kdj_k"] = kdj_df["k"]
    df["kdj_d"] = kdj_df["d"]
    df["kdj_j"] = kdj_df["j"]

    # ATR
    df["atr14"] = atr(df, 14)

    # CCI
    df["cci14"] = cci(df, 14)

    # OBV
    df["obv"] = obv(df)

    # ADX/DMI
    adx_df = adx_dmi(df, 14)
    df["dmi_plus"] = adx_df["plus_di"]
    df["dmi_minus"] = adx_df["minus_di"]
    df["adx14"] = adx_df["adx"]

    # Volume ratio
    df["vol_ratio"] = volume_ratio(df)

    # WR
    df["wr14"] = williams_r(df, 14)

    return df


# ========== 万因子·歌者计划 精选27因子（A股万因子适配期货） ==========


def factor_ts_mean_return_div_open(df: pd.DataFrame, window: int = 43) -> pd.Series:
    """资金动量因子 | AM_ts_mean_return_div_open_d4085de9

    万因子·歌者计划精选因子（Rank 1）。
    原始公式: ts_mean_return(div(open, amount), 43)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 open, amount。
        window: 主窗口参数，默认 43。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 正向（高值预示上涨）
    Q值: 0.9487 | test_rankicir: 0.5679 | monotonicity: 0.9 | ls_sharpe: 1.1712
    """
    open_ = df["open"]
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    _t0 = open_ / amount.replace(0, np.nan)
    _t1 = (np.sign(_t0) * (_t0 - _t0.shift(1)) / _t0.abs().replace(0, np.nan)).rolling(window=window, min_periods=1).mean()
    return pd.Series(_t1, index=df.index)


def factor_add_open_delta(df: pd.DataFrame, window: int = 90) -> pd.Series:
    """量能基础因子 | AM_add_open_delta_c1a4ac91

    万因子·歌者计划精选因子（Rank 2）。
    原始公式: add(open, delta(ts_sum(volume, 90)))

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 open, volume。
        window: 主窗口参数，默认 90。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.941 | test_rankicir: -0.5749 | monotonicity: -0.8 | ls_sharpe: -1.3281
    """
    open_ = df["open"]
    volume = df["volume"]
    _t0 = volume.rolling(window=window, min_periods=1).sum()
    _t1 = _t0.diff()
    _t2 = open_ + _t1
    return pd.Series(_t2, index=df.index)


def factor_mul_ts_sum_amount(df: pd.DataFrame, window: int = 23) -> pd.Series:
    """资金基础因子 | AM_mul_ts_sum_amount_bf8b6da1

    万因子·歌者计划精选因子（Rank 3）。
    原始公式: mul(ts_sum(amount, 23), signed_power(intraday_range, exponent=3.0))

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount, close, high, low。
        window: 主窗口参数，默认 23。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.932 | test_rankicir: -0.5157 | monotonicity: -1.0 | ls_sharpe: -0.981
    """
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    intraday_range = (df["high"] - df["low"]) / df["close"].replace(0, np.nan)
    _t0 = amount.rolling(window=window, min_periods=1).sum()
    _t1 = np.sign(intraday_range) * np.abs(intraday_range) ** 3.0
    _t2 = _t0 * _t1
    return pd.Series(_t2, index=df.index)


def factor_neg_ts_pct_change_abs(df: pd.DataFrame, window: int = 71) -> pd.Series:
    """量能动量因子 | AM_neg_ts_pct_change_abs_ee1bb069

    万因子·歌者计划精选因子（Rank 4）。
    原始公式: neg(ts_pct_change(abs(volume), 71))

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 volume。
        window: 主窗口参数，默认 71。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 正向（高值预示上涨）
    Q值: 0.9211 | test_rankicir: 0.5111 | monotonicity: 1.0 | ls_sharpe: 1.1636
    """
    volume = df["volume"]
    _t0 = volume.abs()
    _t1 = np.sign(_t0) * (_t0 - _t0.shift(window)) / _t0.abs().replace(0, np.nan)
    _t2 = -(_t1)
    return pd.Series(_t2, index=df.index)


def factor_mul_signed_power_amplitude(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """资金基础因子 | AM_mul_signed_power_amplitude_758209a4

    万因子·歌者计划精选因子（Rank 5）。
    原始公式: mul(signed_power(amplitude, exponent=1.5), amount)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount, high, low。
        window: 保留参数，默认 10（原始因子无时序窗口）。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.9178 | test_rankicir: -0.5015 | monotonicity: -1.0 | ls_sharpe: -1.2863
    """
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    amplitude = (df["high"] - df["low"]) / df["close"].shift(1).replace(0, np.nan)
    _t0 = np.sign(amplitude) * np.abs(amplitude) ** 1.5
    _t1 = _t0 * amount
    return pd.Series(_t1, index=df.index)


def factor_mul_amount_ts_std(df: pd.DataFrame, window: int = 77) -> pd.Series:
    """资金动量因子 | AM_mul_amount_ts_std_0910cc9f

    万因子·歌者计划精选因子（Rank 6）。
    原始公式: mul(amount, ts_std(abs(intraday_range), 77))

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount, close, high, low。
        window: 主窗口参数，默认 77。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.9134 | test_rankicir: -0.5205 | monotonicity: -1.0 | ls_sharpe: -1.1801
    """
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    intraday_range = (df["high"] - df["low"]) / df["close"].replace(0, np.nan)
    _t0 = intraday_range.abs()
    _t1 = _t0.rolling(window=window, min_periods=1).std()
    _t2 = amount * _t1
    return pd.Series(_t2, index=df.index)


def factor_signed_power_ts_maxmin_volume(df: pd.DataFrame, window: int = 84) -> pd.Series:
    """量能动量因子 | AM_signed_power_ts_maxmin_volume_3abae467

    万因子·歌者计划精选因子（Rank 7）。
    原始公式: signed_power(ts_maxmin(volume, 84), exponent=2.0)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 volume。
        window: 主窗口参数，默认 84。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.9212 | test_rankicir: -0.4887 | monotonicity: -1.0 | ls_sharpe: -1.2647
    """
    volume = df["volume"]
    vmin = volume.rolling(window=window, min_periods=1).min()
    vmax = volume.rolling(window=window, min_periods=1).max()
    _t0 = (volume - vmin) / (vmax - vmin).replace(0, np.nan)
    _t1 = np.sign(_t0) * np.abs(_t0) ** 2.0
    return pd.Series(_t1, index=df.index)


def factor_ts_maxmin_signed_power_volume(df: pd.DataFrame, window: int = 111) -> pd.Series:
    """量能动量因子 | AM_ts_maxmin_signed_power_volume_8af03928

    万因子·歌者计划精选因子（Rank 8）。
    原始公式: ts_maxmin(signed_power(volume, exponent=1.5), 111)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 volume。
        window: 主窗口参数，默认 111。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.9054 | test_rankicir: -0.5232 | monotonicity: -0.9 | ls_sharpe: -1.377
    """
    volume = df["volume"]
    _t0 = np.sign(volume) * np.abs(volume) ** 1.5
    vmin = _t0.rolling(window=window, min_periods=1).min()
    vmax = _t0.rolling(window=window, min_periods=1).max()
    _t1 = (_t0 - vmin) / (vmax - vmin).replace(0, np.nan)
    return pd.Series(_t1, index=df.index)


def factor_mul_abs_amount(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """资金基础因子 | AM_mul_abs_amount_3779853f

    万因子·歌者计划精选因子（Rank 9）。
    原始公式: mul(abs(amount), intraday_range)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount, close, high, low。
        window: 保留参数，默认 10（原始因子无时序窗口）。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.9047 | test_rankicir: -0.4988 | monotonicity: -1.0 | ls_sharpe: -1.2683
    """
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    intraday_range = (df["high"] - df["low"]) / df["close"].replace(0, np.nan)
    _t0 = amount.abs()
    _t1 = _t0 * intraday_range
    return pd.Series(_t1, index=df.index)


def factor_abs_mul_amount(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """资金基础因子 | AM_abs_mul_amount_a1dda97d

    万因子·歌者计划精选因子（Rank 10）。
    原始公式: abs(mul(amount, amplitude))

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount, high, low。
        window: 保留参数，默认 10（原始因子无时序窗口）。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.9012 | test_rankicir: -0.4899 | monotonicity: -1.0 | ls_sharpe: -1.364
    """
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    amplitude = (df["high"] - df["low"]) / df["close"].shift(1).replace(0, np.nan)
    _t0 = amount * amplitude
    _t1 = _t0.abs()
    return pd.Series(_t1, index=df.index)


def factor_sub_sign_ts_std(df: pd.DataFrame, window: int = 117) -> pd.Series:
    """资金动量因子 | AM_sub_sign_ts_std_dd8ee5e9

    万因子·歌者计划精选因子（Rank 11）。
    原始公式: sub(sign(ts_std(ts_skew(zscore(ret_5, 95), 80), 112)), ts_maxmin(neg(ts_max(amount, 6)), 117))

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount, close。
        window: 主窗口参数，默认 117。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.8951 | test_rankicir: -0.5067 | monotonicity: -0.9 | ls_sharpe: -1.6027
    """
    ret_5 = df["close"].pct_change(5, fill_method=None)
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    _t0 = (ret_5 - ret_5.rolling(window=95, min_periods=1).mean()) / ret_5.rolling(window=95, min_periods=1).std().replace(0, np.nan)
    _t1 = _t0.rolling(window=80, min_periods=1).skew()
    _t2 = _t1.rolling(window=112, min_periods=1).std()
    _t3 = np.sign(_t2)
    _t4 = amount.rolling(window=6, min_periods=1).max()
    _t5 = -(_t4)
    _t6_min = _t5.rolling(window=window, min_periods=1).min()
    _t6_max = _t5.rolling(window=window, min_periods=1).max()
    _t6 = (_t5 - _t6_min) / (_t6_max - _t6_min).replace(0, np.nan)
    _t7 = _t3 - _t6
    return pd.Series(_t7, index=df.index)


def factor_mul_amount_log(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """资金基础因子 | AM_mul_amount_log_ed73d532

    万因子·歌者计划精选因子（Rank 12）。
    原始公式: mul(amount, log(amplitude))

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount, high, low。
        window: 保留参数，默认 10（原始因子无时序窗口）。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.8994 | test_rankicir: -0.4889 | monotonicity: -1.0 | ls_sharpe: -1.3712
    """
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    amplitude = (df["high"] - df["low"]) / df["close"].shift(1).replace(0, np.nan)
    _t0 = np.sign(amplitude) * np.log1p(np.abs(amplitude))
    _t1 = amount * _t0
    return pd.Series(_t1, index=df.index)


def factor_ts_dema_mul_amount(df: pd.DataFrame, window: int = 13) -> pd.Series:
    """资金动量因子 | AM_ts_dema_mul_amount_f2ef68c3

    万因子·歌者计划精选因子（Rank 13）。
    原始公式: ts_dema(mul(amount, amplitude), 13)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount, high, low。
        window: 主窗口参数，默认 13。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.8963 | test_rankicir: -0.4882 | monotonicity: -1.0 | ls_sharpe: -1.3257
    """
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    amplitude = (df["high"] - df["low"]) / df["close"].shift(1).replace(0, np.nan)
    _t0 = amount * amplitude
    ema1 = _t0.ewm(span=window, adjust=False, min_periods=1).mean()
    ema2 = ema1.ewm(span=window, adjust=False, min_periods=1).mean()
    _t1 = 2.0 * ema1 - ema2
    return pd.Series(_t1, index=df.index)


def factor_neg_ts_maxmin_volume(df: pd.DataFrame, window: int = 79) -> pd.Series:
    """量能动量因子 | AM_neg_ts_maxmin_volume_b4c7097f

    万因子·歌者计划精选因子（Rank 14）。
    原始公式: neg(ts_maxmin(volume, 79))

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 volume。
        window: 主窗口参数，默认 79。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 正向（高值预示上涨）
    Q值: 0.9116 | test_rankicir: 0.4789 | monotonicity: 1.0 | ls_sharpe: 1.129
    """
    volume = df["volume"]
    vmin = volume.rolling(window=window, min_periods=1).min()
    vmax = volume.rolling(window=window, min_periods=1).max()
    _t0 = (volume - vmin) / (vmax - vmin).replace(0, np.nan)
    _t1 = -(_t0)
    return pd.Series(_t1, index=df.index)


def factor_mul_amount_mul(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """量能动量因子 | AM_mul_amount_mul_0992fa40

    万因子·歌者计划精选因子（Rank 15）。
    原始公式: mul(amount, mul(ts_dema(amplitude, 10), volume))

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount, high, low, volume。
        window: 主窗口参数，默认 10。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.8977 | test_rankicir: -0.4576 | monotonicity: -1.0 | ls_sharpe: -1.5235
    """
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    amplitude = (df["high"] - df["low"]) / df["close"].shift(1).replace(0, np.nan)
    volume = df["volume"]
    ema1 = amplitude.ewm(span=window, adjust=False, min_periods=1).mean()
    ema2 = ema1.ewm(span=window, adjust=False, min_periods=1).mean()
    _t0 = 2.0 * ema1 - ema2
    _t1 = _t0 * volume
    _t2 = amount * _t1
    return pd.Series(_t2, index=df.index)


def factor_ts_std_signed_power_amount(df: pd.DataFrame, window: int = 5) -> pd.Series:
    """资金动量因子 | AM_ts_std_signed_power_amount_888f7541

    万因子·歌者计划精选因子（Rank 16）。
    原始公式: ts_std(signed_power(amount, exponent=0.5), 5)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount。
        window: 主窗口参数，默认 5。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.8779 | test_rankicir: -0.486 | monotonicity: -1.0 | ls_sharpe: -1.5578
    """
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    _t0 = np.sign(amount) * np.abs(amount) ** 0.5
    _t1 = _t0.rolling(window=window, min_periods=1).std()
    return pd.Series(_t1, index=df.index)


def factor_ts_maxmin_abs_volume(df: pd.DataFrame, window: int = 91) -> pd.Series:
    """量能动量因子 | AM_ts_maxmin_abs_volume_22868f8f

    万因子·歌者计划精选因子（Rank 17）。
    原始公式: ts_maxmin(abs(volume), 91)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 volume。
        window: 主窗口参数，默认 91。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.9023 | test_rankicir: -0.4959 | monotonicity: -0.9 | ls_sharpe: -1.3781
    """
    volume = df["volume"]
    _t0 = volume.abs()
    vmin = _t0.rolling(window=window, min_periods=1).min()
    vmax = _t0.rolling(window=window, min_periods=1).max()
    _t1 = (_t0 - vmin) / (vmax - vmin).replace(0, np.nan)
    return pd.Series(_t1, index=df.index)


def factor_abs_ts_maxmin_sub(df: pd.DataFrame, window: int = 91) -> pd.Series:
    """量能动量因子 | AM_abs_ts_maxmin_sub_627088c0

    万因子·歌者计划精选因子（Rank 18）。
    原始公式: abs(ts_maxmin(sub(volume, -1.8931), 91))

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 volume。
        window: 主窗口参数，默认 91。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.9023 | test_rankicir: -0.4959 | monotonicity: -0.9 | ls_sharpe: -1.3781
    """
    volume = df["volume"]
    _t0 = volume - -1.893107054794875
    vmin = _t0.rolling(window=window, min_periods=1).min()
    vmax = _t0.rolling(window=window, min_periods=1).max()
    _t1 = (_t0 - vmin) / (vmax - vmin).replace(0, np.nan)
    _t2 = _t1.abs()
    return pd.Series(_t2, index=df.index)


def factor_ts_maxmin_add_volume(df: pd.DataFrame, window: int = 88) -> pd.Series:
    """量能动量因子 | AM_ts_maxmin_add_volume_bd3d9c28

    万因子·歌者计划精选因子（Rank 19）。
    原始公式: ts_maxmin(add(volume, gap), 88)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 close, open, volume。
        window: 主窗口参数，默认 88。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.9028 | test_rankicir: -0.4964 | monotonicity: -0.9 | ls_sharpe: -1.2977
    """
    volume = df["volume"]
    gap = df["open"] / df["close"].shift(1).replace(0, np.nan) - 1
    _t0 = volume + gap
    vmin = _t0.rolling(window=window, min_periods=1).min()
    vmax = _t0.rolling(window=window, min_periods=1).max()
    _t1 = (_t0 - vmin) / (vmax - vmin).replace(0, np.nan)
    return pd.Series(_t1, index=df.index)


def factor_signed_power_mul_amount(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """资金基础因子 | AM_signed_power_mul_amount_8ae7bd21

    万因子·歌者计划精选因子（Rank 20）。
    原始公式: signed_power(mul(amount, amplitude), exponent=0.5)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount, high, low。
        window: 保留参数，默认 10（原始因子无时序窗口）。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.8819 | test_rankicir: -0.4899 | monotonicity: -1.0 | ls_sharpe: -1.364
    """
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    amplitude = (df["high"] - df["low"]) / df["close"].shift(1).replace(0, np.nan)
    _t0 = amount * amplitude
    _t1 = np.sign(_t0) * np.abs(_t0) ** 0.5
    return pd.Series(_t1, index=df.index)


def factor_ts_pct_change_signed_power_mul(df: pd.DataFrame, window: int = 56) -> pd.Series:
    """量能动量因子 | AM_ts_pct_change_signed_power_mul_621cb807

    万因子·歌者计划精选因子（Rank 21）。
    原始公式: ts_pct_change(signed_power(mul(amount, ts_mean_return(add(low, volume), 56)), exponent=1.5), 43)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount, low, volume。
        window: 主窗口参数，默认 56。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.913 | test_rankicir: -0.5272 | monotonicity: -0.9 | ls_sharpe: -0.8146
    """
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    low = df["low"]
    volume = df["volume"]
    _t0 = low + volume
    _t1 = (np.sign(_t0) * (_t0 - _t0.shift(1)) / _t0.abs().replace(0, np.nan)).rolling(window=56, min_periods=1).mean()
    _t2 = amount * _t1
    _t3 = np.sign(_t2) * np.abs(_t2) ** 1.5
    _t4 = np.sign(_t3) * (_t3 - _t3.shift(43)) / _t3.abs().replace(0, np.nan)
    return pd.Series(_t4, index=df.index)


def factor_ts_inverse_cv_delta_amount(df: pd.DataFrame, window: int = 85) -> pd.Series:
    """资金动量因子 | AM_ts_inverse_cv_delta_amount_5166de46

    万因子·歌者计划精选因子（Rank 22）。
    原始公式: ts_inverse_cv(delta(amount), 85)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount。
        window: 主窗口参数，默认 85。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.901 | test_rankicir: -0.4893 | monotonicity: -0.9 | ls_sharpe: -1.3107
    """
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    _t0 = amount.diff()
    _t1 = _t0.rolling(window=window, min_periods=1).mean() / _t0.rolling(window=window, min_periods=1).std().replace(0, np.nan)
    return pd.Series(_t1, index=df.index)


def factor_ts_inverse_cv_div_delta(df: pd.DataFrame, window: int = 85) -> pd.Series:
    """资金动量因子 | AM_ts_inverse_cv_div_delta_a5e987bd

    万因子·歌者计划精选因子（Rank 23）。
    原始公式: ts_inverse_cv(div(delta(amount), 0.1643), 85)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount。
        window: 主窗口参数，默认 85。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.901 | test_rankicir: -0.4893 | monotonicity: -0.9 | ls_sharpe: -1.3107
    """
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    _t0 = amount.diff()
    _t1 = _t0 / 0.1643122401170105
    _t2 = _t1.rolling(window=window, min_periods=1).mean() / _t1.rolling(window=window, min_periods=1).std().replace(0, np.nan)
    return pd.Series(_t2, index=df.index)


def factor_log_mul_amplitude(df: pd.DataFrame, window: int = 10) -> pd.Series:
    """资金基础因子 | AM_log_mul_amplitude_79b9b6af

    万因子·歌者计划精选因子（Rank 24）。
    原始公式: log(mul(amplitude, amount))

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount, high, low。
        window: 保留参数，默认 10（原始因子无时序窗口）。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 负向（高值预示下跌）
    Q值: 0.8754 | test_rankicir: -0.4899 | monotonicity: -1.0 | ls_sharpe: -1.364
    """
    amplitude = (df["high"] - df["low"]) / df["close"].shift(1).replace(0, np.nan)
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    _t0 = amplitude * amount
    _t1 = np.sign(_t0) * np.log1p(np.abs(_t0))
    return pd.Series(_t1, index=df.index)


def factor_ema_ts_dema_delta(df: pd.DataFrame, window: int = 38) -> pd.Series:
    """波动振幅因子 | AM_ema_ts_dema_delta_8dc6d97c

    万因子·歌者计划精选因子（Rank 25）。
    原始公式: ema(ts_dema(delta(ts_inverse_cv(amplitude, 38)), 3), 103)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 high, low。
        window: 主窗口参数，默认 38。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 正向（高值预示上涨）
    Q值: 0.8826 | test_rankicir: 0.4554 | monotonicity: 1.0 | ls_sharpe: 1.5643
    """
    amplitude = (df["high"] - df["low"]) / df["close"].shift(1).replace(0, np.nan)
    _t0 = amplitude.rolling(window=38, min_periods=1).mean() / amplitude.rolling(window=38, min_periods=1).std().replace(0, np.nan)
    _t1 = _t0.diff()
    ema1 = _t1.ewm(span=3, adjust=False, min_periods=1).mean()
    ema2 = ema1.ewm(span=3, adjust=False, min_periods=1).mean()
    _t2 = 2.0 * ema1 - ema2
    _t3 = _t2.ewm(span=103, adjust=False, min_periods=1).mean()
    return pd.Series(_t3, index=df.index)


def factor_sub_ts_median_clip(df: pd.DataFrame, window: int = 65) -> pd.Series:
    """资金基础因子 | AM_sub_ts_median_clip_bff1a9fb

    万因子·歌者计划精选因子（Rank 26）。
    原始公式: sub(ts_median(clip(low, low=-3.0, high=3.0), 65), mul(amount, amplitude))

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount, high, low。
        window: 主窗口参数，默认 65。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 正向（高值预示上涨）
    Q值: 0.888 | test_rankicir: 0.4899 | monotonicity: 1.0 | ls_sharpe: 1.1315
    """
    low = df["low"]
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    amplitude = (df["high"] - df["low"]) / df["close"].shift(1).replace(0, np.nan)
    _t0 = low.clip(lower=-3.0, upper=3.0)
    _t1 = _t0.rolling(window=window, min_periods=1).median()
    _t2 = amount * amplitude
    _t3 = _t1 - _t2
    return pd.Series(_t3, index=df.index)


def factor_div_ts_inverse_cv_volume(df: pd.DataFrame, window: int = 5) -> pd.Series:
    """量能动量因子 | AM_div_ts_inverse_cv_volume_d69faf0f

    万因子·歌者计划精选因子（Rank 27）。
    原始公式: div(ts_inverse_cv(volume, 5), amount)

    Args:
        df: 包含OHLCV数据的DataFrame，列名需含 amount, volume。
        window: 主窗口参数，默认 5。

    Returns:
        pd.Series: 因子值序列，与输入行数一致。

    信号方向: 正向（高值预示上涨）
    Q值: 0.8717 | test_rankicir: 0.4689 | monotonicity: 1.0 | ls_sharpe: 1.523
    """
    volume = df["volume"]
    amount = df["amount"] if "amount" in df.columns else df["close"] * df["volume"]
    _t0 = volume.rolling(window=window, min_periods=1).mean() / volume.rolling(window=window, min_periods=1).std().replace(0, np.nan)
    _t1 = _t0 / amount.replace(0, np.nan)
    return pd.Series(_t1, index=df.index)


def calculate_all_factors(df: pd.DataFrame) -> pd.DataFrame:
    """计算全部27个万因子精选因子，返回宽表。

    参数:
        df: 包含 open/high/low/close/volume/amount 的 DataFrame。
            若缺少 amount 列，内部将使用 close * volume 近似。

    返回:
        新增27列因子值的 DataFrame
    """
    if "amount" not in df.columns:
        df = df.copy()
        df["amount"] = df["close"] * df["volume"]
    df["factor_ts_mean_return_div_open"] = factor_ts_mean_return_div_open(df)
    df["factor_add_open_delta"] = factor_add_open_delta(df)
    df["factor_mul_ts_sum_amount"] = factor_mul_ts_sum_amount(df)
    df["factor_neg_ts_pct_change_abs"] = factor_neg_ts_pct_change_abs(df)
    df["factor_mul_signed_power_amplitude"] = factor_mul_signed_power_amplitude(df)
    df["factor_mul_amount_ts_std"] = factor_mul_amount_ts_std(df)
    df["factor_signed_power_ts_maxmin_volume"] = factor_signed_power_ts_maxmin_volume(df)
    df["factor_ts_maxmin_signed_power_volume"] = factor_ts_maxmin_signed_power_volume(df)
    df["factor_mul_abs_amount"] = factor_mul_abs_amount(df)
    df["factor_abs_mul_amount"] = factor_abs_mul_amount(df)
    df["factor_sub_sign_ts_std"] = factor_sub_sign_ts_std(df)
    df["factor_mul_amount_log"] = factor_mul_amount_log(df)
    df["factor_ts_dema_mul_amount"] = factor_ts_dema_mul_amount(df)
    df["factor_neg_ts_maxmin_volume"] = factor_neg_ts_maxmin_volume(df)
    df["factor_mul_amount_mul"] = factor_mul_amount_mul(df)
    df["factor_ts_std_signed_power_amount"] = factor_ts_std_signed_power_amount(df)
    df["factor_ts_maxmin_abs_volume"] = factor_ts_maxmin_abs_volume(df)
    df["factor_abs_ts_maxmin_sub"] = factor_abs_ts_maxmin_sub(df)
    df["factor_ts_maxmin_add_volume"] = factor_ts_maxmin_add_volume(df)
    df["factor_signed_power_mul_amount"] = factor_signed_power_mul_amount(df)
    df["factor_ts_pct_change_signed_power_mul"] = factor_ts_pct_change_signed_power_mul(df)
    df["factor_ts_inverse_cv_delta_amount"] = factor_ts_inverse_cv_delta_amount(df)
    df["factor_ts_inverse_cv_div_delta"] = factor_ts_inverse_cv_div_delta(df)
    df["factor_log_mul_amplitude"] = factor_log_mul_amplitude(df)
    df["factor_ema_ts_dema_delta"] = factor_ema_ts_dema_delta(df)
    df["factor_sub_ts_median_clip"] = factor_sub_ts_median_clip(df)
    df["factor_div_ts_inverse_cv_volume"] = factor_div_ts_inverse_cv_volume(df)
    return df
