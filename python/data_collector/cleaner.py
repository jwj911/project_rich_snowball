import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger("data.cleaner")


def clean_realtime(raw: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    try:
        current = float(raw.get("current_price") or 0)
        open_p = float(raw.get("open_price") or 0)
        high = float(raw.get("high") or 0)
        low = float(raw.get("low") or 0)
        volume = int(raw.get("volume") or 0)

        if current <= 0 or high < low or volume < 0:
            logger.warning(f"[skip] invalid realtime data for {symbol}: {raw}")
            return None

        return {
            "symbol": symbol,
            "current_price": round(current, 2),
            "open_price": round(open_p, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "volume": volume,
            "change_percent": round(float(raw.get("change_percent") or 0), 2),
            "open_interest": int(raw.get("open_interest") or 0),
            "updated_at": raw.get("updated_at") or datetime.now(),
        }
    except Exception as e:
        logger.error(f"clean_realtime failed for {symbol}: {e}")
        return None


def clean_kline(raw_list: List[Dict[str, Any]], symbol: str) -> List[Dict[str, Any]]:
    cleaned = []
    seen = set()
    for raw in raw_list:
        try:
            ts = raw.get("trading_time")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            key = (symbol, ts)
            if key in seen:
                continue
            seen.add(key)

            open_p = float(raw.get("open_price", 0))
            high = float(raw.get("high_price", 0))
            low = float(raw.get("low_price", 0))
            close = float(raw.get("close_price", 0))
            volume = int(raw.get("volume", 0))

            if high < low or close <= 0 or volume < 0:
                continue

            cleaned.append({
                "symbol": symbol,
                "trading_time": ts,
                "open_price": round(open_p, 2),
                "high_price": round(high, 2),
                "low_price": round(low, 2),
                "close_price": round(close, 2),
                "volume": volume,
                "open_interest": int(raw.get("open_interest") or 0),
            })
        except Exception as e:
            logger.warning(f"skip invalid kline row: {e}")
            continue
    return cleaned
