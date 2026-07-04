"""后端技术指标计算库。

基于纯 numpy/pandas 实现，无需 talib 依赖。
输入为 pandas DataFrame，列名：open, high, low, close, volume。
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
