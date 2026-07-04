"""市场状态识别模块。

基于纯 numpy/pandas 计算，无 LLM 依赖。
识别当前市场处于什么状态（趋势/震荡/高波/低波等），
为策略生成提供上下文约束，也为后续退化检测提供基准。

核心指标：
- ADX (Average Directional Index) — 趋势强度
- MA 斜率 — 趋势方向
- ATR/Close 百分位 — 波动率水平
- Bollinger 带宽 — 区间化程度
- Hurst 指数 — 趋势持续性
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class MarketRegime:
    """市场状态识别结果。"""

    regime: str
    """trending_up / trending_down / range_bound / high_volatility / low_volatility / breakout"""

    confidence: float
    """0-1，状态判定的置信度"""

    metrics: dict[str, Any]
    """详细指标值，用于调试和报告"""


def _compute_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """计算 Average Directional Index (ADX)。

    基于 Wilder 平滑（EMA alpha=1/period），不是简单移动平均。
    """
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = high.diff()
    down_move = low.diff().abs() * -1
    plus_dm = np.where((up_move > 0) & (up_move > -down_move), up_move, 0)
    minus_dm = np.where((-down_move > 0) & (-down_move > up_move), -down_move, 0)

    atr = tr.ewm(alpha=1 / period, adjust=False).mean()

    smoothed_plus_dm = pd.Series(plus_dm).ewm(alpha=1 / period, adjust=False).mean()
    smoothed_minus_dm = pd.Series(minus_dm).ewm(alpha=1 / period, adjust=False).mean()

    plus_di = 100 * smoothed_plus_dm / atr.replace(0, np.nan)
    minus_di = 100 * smoothed_minus_dm / atr.replace(0, np.nan)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()

    return adx


def _linear_slope(series: pd.Series, lookback: int = 5) -> float:
    """对最近 lookback 个值做线性回归，返回斜率标准化值。"""
    recent = series.dropna().tail(lookback)
    if len(recent) < 3:
        return 0.0
    x = np.arange(len(recent))
    y = recent.values
    slope = np.polyfit(x, y, 1)[0]
    # 用序列均值做标准化
    mean_val = np.mean(np.abs(y)) if np.mean(np.abs(y)) > 0 else 1.0
    return float(slope / mean_val)


def _compute_hurst(series: pd.Series, max_lag: int = 20) -> float:
    """用重标极差 (R/S) 方法估计 Hurst 指数。

    H > 0.5: 趋势持续（有记忆性）
    H ≈ 0.5: 随机游走
    H < 0.5: 均值回归
    """
    recent = series.dropna().tail(252).values
    if len(recent) < max_lag * 2:
        return 0.5

    lags = range(2, min(max_lag + 1, len(recent) // 2))
    rs_values = []
    for lag in lags:
        chunks = len(recent) // lag
        if chunks < 2:
            break
        rs_chunk = []
        for i in range(chunks):
            chunk = recent[i * lag : (i + 1) * lag]
            if len(chunk) < 2:
                continue
            mean = chunk.mean()
            deviations = chunk - mean
            cum_dev = np.cumsum(deviations)
            r = cum_dev.max() - cum_dev.min()
            s = np.std(chunk)
            if s > 1e-12 and r > 0:
                rs_chunk.append(r / s)
        if rs_chunk:
            rs_values.append((np.log(lag), np.log(np.mean(rs_chunk))))

    if len(rs_values) < 3:
        return 0.5

    x = np.array([v[0] for v in rs_values])
    y = np.array([v[1] for v in rs_values])
    hurst = float(np.polyfit(x, y, 1)[0])
    return max(0.1, min(0.95, hurst))


def detect_regime(df: pd.DataFrame) -> MarketRegime:
    """识别当前市场状态。

    Args:
        df: OHLCV DataFrame，需包含 open/high/low/close/volume 列，按时间升序排列。

    Returns:
        MarketRegime 对象。

    Raises:
        ValueError: 数据不足时（至少需要 30 根 K 线）。
    """
    if len(df) < 30:
        raise ValueError(f"市场状态识别至少需要 30 根 K 线，当前仅 {len(df)} 根")

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    # --- 1. 趋势强度：ADX ---
    adx_series = _compute_adx(high, low, close, period=14)
    adx_current = float(adx_series.iloc[-1]) if not adx_series.dropna().empty else 20.0

    # --- 2. 趋势方向：MA 斜率 ---
    ma20 = close.rolling(20, min_periods=20).mean()
    ma60 = close.rolling(60, min_periods=20).mean()
    ma20_slope = _linear_slope(ma20, lookback=5)
    ma60_slope = _linear_slope(ma60, lookback=10)

    # --- 3. 波动率水平：ATR/Close 百分位 ---
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = tr.rolling(14, min_periods=14).mean()
    atr_pct = atr14 / close
    vol_percentile = float(atr_pct.rank(pct=True).iloc[-1]) if not atr_pct.dropna().empty else 0.5

    # --- 4. 区间化程度：Bollinger 带宽 ---
    bb_mid = close.rolling(20, min_periods=20).mean()
    bb_std = close.rolling(20, min_periods=20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_width = (bb_upper - bb_lower) / bb_mid.replace(0, np.nan)
    bb_percentile = float(bb_width.rank(pct=True).iloc[-1]) if not bb_width.dropna().empty else 0.5

    # --- 5. Hurst 指数 ---
    hurst = _compute_hurst(close, max_lag=20)

    # --- 综合判断 ---
    metrics = {
        "adx": round(adx_current, 2),
        "ma20_slope": round(ma20_slope, 6),
        "ma60_slope": round(ma60_slope, 6),
        "vol_percentile": round(vol_percentile, 3),
        "bb_width_percentile": round(bb_percentile, 3),
        "hurst": round(hurst, 3),
        "close_last": float(close.iloc[-1]),
        "bars": len(df),
    }

    # 判定逻辑
    is_strong_trend = adx_current > 35
    is_volatile = vol_percentile > 0.7
    is_low_vol = vol_percentile < 0.3

    if is_strong_trend and ma20_slope > 0.001 and ma60_slope > 0:
        regime = "trending_up"
        # 置信度：ADX 越强 + 方向越一致 → 越高
        direction_agree = 1 if (ma20_slope > 0 and ma60_slope > 0) else 0.5
        confidence = min(adx_current / 60 + direction_agree * 0.3, 0.95)

    elif is_strong_trend and ma20_slope < -0.001 and ma60_slope < 0:
        regime = "trending_down"
        direction_agree = 1 if (ma20_slope < 0 and ma60_slope < 0) else 0.5
        confidence = min(adx_current / 60 + direction_agree * 0.3, 0.95)

    elif is_low_vol and bb_percentile < 0.3 and adx_current < 20:
        # 低波动 + 窄带宽 + 低 ADX → 可能即将突破
        regime = "low_volatility"
        confidence = 0.6 + (0.3 - vol_percentile)

    elif is_volatile and adx_current > 20:
        regime = "high_volatility"
        confidence = 0.5 + vol_percentile * 0.3

    elif adx_current < 20 and 0.3 < bb_percentile < 0.7:
        regime = "range_bound"
        confidence = 0.5 + (20 - adx_current) * 0.02

    elif hurst < 0.4 and adx_current < 22:
        regime = "range_bound"
        confidence = 0.5 + (0.5 - hurst)

    else:
        # 默认：看最近的突破信号
        close_last = float(close.iloc[-1])
        high_20 = float(high.tail(20).max())
        low_20 = float(low.tail(20).min())

        if close_last >= high_20 * 0.99 and ma20_slope > 0:
            regime = "trending_up"
            confidence = 0.55
        elif close_last <= low_20 * 1.01 and ma20_slope < 0:
            regime = "trending_down"
            confidence = 0.55
        else:
            regime = "range_bound"
            confidence = 0.50

    return MarketRegime(regime=regime, confidence=round(confidence, 3), metrics=metrics)
