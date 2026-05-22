"""Validation and normalization for internal market-data rows."""
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def clean_realtime(data: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    """Clean one realtime quote row. Return None when the row is unusable."""
    if not data or not isinstance(data, dict):
        return None

    required = ["current_price", "high", "low", "volume"]
    if any(data.get(k) is None for k in required):
        logger.debug("[%s] Missing realtime required fields: %s", symbol, data)
        return None

    current_price = data["current_price"]
    if current_price <= 0:
        logger.debug("[%s] Invalid price: %s", symbol, current_price)
        return None

    volume = data.get("volume")
    if volume is None or (isinstance(volume, (int, float)) and volume < 0):
        logger.debug("[%s] Invalid volume: %s", symbol, volume)
        return None

    ohlc = {
        "open_price": data.get("open_price", current_price),
        "high_price": data["high"],
        "low_price": data["low"],
        "close_price": current_price,
    }
    if not _valid_ohlc(ohlc):
        logger.warning("[%s] OHLC inconsistency: %s", symbol, data)
        return None

    change_percent = data.get("change_percent")
    pre_settlement = data.get("pre_settlement")
    if change_percent is None and pre_settlement and pre_settlement > 0:
        change_percent = round((current_price - pre_settlement) / pre_settlement * 100, 4)

    return {
        "symbol": symbol,
        "current_price": float(current_price),
        "pre_settlement": float(pre_settlement) if pre_settlement is not None else None,
        "change_percent": float(change_percent) if change_percent is not None else 0.0,
        "open_price": float(ohlc["open_price"]),
        "high": float(data["high"]),
        "low": float(data["low"]),
        "volume": int(data["volume"]),
        "open_interest": int(data["open_interest"]) if data.get("open_interest") is not None else None,
        "bid1": float(data["bid1"]) if data.get("bid1") is not None else None,
        "ask1": float(data["ask1"]) if data.get("ask1") is not None else None,
        "updated_at": data.get("updated_at") or datetime.now(timezone.utc),
    }


def clean_kline(rows: list[dict[str, Any]], contract_code: str) -> list[dict[str, Any]]:
    """Clean kline rows, dedupe by time/period, and sort ascending."""
    seen = set()
    cleaned = []

    for row in rows:
        required = ["period", "trading_time", "volume"]
        if any(row.get(k) is None for k in required):
            logger.debug("[%s] Skipping kline row with missing fields: %s", contract_code, row)
            continue

        volume = row.get("volume")
        if isinstance(volume, (int, float)) and volume < 0:
            logger.debug("[%s] Skipping kline row with negative volume: %s", contract_code, row)
            continue

        if not _valid_ohlc(row):
            logger.debug("[%s] Skipping invalid OHLC row: %s", contract_code, row)
            continue

        key = (row.get("trading_time"), row.get("period"))
        if key in seen:
            continue
        seen.add(key)

        cleaned.append(
            {
                "contract_code": contract_code,
                "symbol": row.get("symbol"),
                "period": row["period"],
                "trading_time": row["trading_time"],
                "open_price": float(row["open_price"]),
                "high_price": float(row["high_price"]),
                "low_price": float(row["low_price"]),
                "close_price": float(row["close_price"]),
                "volume": int(row["volume"]),
                "open_interest": int(row["open_interest"]) if row.get("open_interest") is not None else None,
            }
        )

    cleaned.sort(key=lambda x: x["trading_time"])
    return cleaned


def _valid_ohlc(row: dict[str, Any]) -> bool:
    open_p = row.get("open_price") if row.get("open_price") is not None else row.get("open")
    high = row.get("high_price") if row.get("high_price") is not None else row.get("high")
    low = row.get("low_price") if row.get("low_price") is not None else row.get("low")
    close = row.get("close_price") if row.get("close_price") is not None else row.get("close")

    if any(v is None for v in [open_p, high, low, close]):
        return False

    try:
        open_p = float(open_p)
        high = float(high)
        low = float(low)
        close = float(close)
    except (TypeError, ValueError):
        return False

    if any(v < 0 for v in [open_p, high, low, close]):
        return False
    if high < low:
        return False
    if high < max(open_p, close):
        return False
    if low > min(open_p, close):
        return False

    return True
