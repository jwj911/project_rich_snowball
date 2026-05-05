"""Map external market data rows to the internal collector schema."""
from datetime import datetime, timezone
from typing import Any


def map_akshare_realtime(row: dict[str, Any], symbol: str) -> dict[str, Any]:
    close = _to_float(_first(row, "\u6700\u65b0\u4ef7", "current_price", "close", "last_price"))
    pre_settlement = _to_float(_first(row, "\u6628\u7ed3\u7b97", "\u6628\u7ed3\u7b97\u4ef7", "pre_settlement"))
    change_percent = _to_float(_first(row, "\u6da8\u8dcc\u5e45", "change_percent"))
    if change_percent is None and close is not None and pre_settlement and pre_settlement > 0:
        change_percent = round((close - pre_settlement) / pre_settlement * 100, 2)
    return {
        "symbol": symbol or row.get("symbol"),
        "current_price": close,
        "pre_settlement": pre_settlement,
        "open_price": _to_float(_first(row, "\u5f00\u76d8\u4ef7", "open_price", "open")),
        "high": _to_float(_first(row, "\u6700\u9ad8\u4ef7", "high")),
        "low": _to_float(_first(row, "\u6700\u4f4e\u4ef7", "low")),
        "volume": _to_int(_first(row, "\u6210\u4ea4\u91cf", "volume", "vol")),
        "open_interest": _to_int(_first(row, "\u6301\u4ed3\u91cf", "open_interest", "hold")),
        "bid1": _to_float(_first(row, "\u4e70\u4e00\u4ef7", "bid1")),
        "ask1": _to_float(_first(row, "\u5356\u4e00\u4ef7", "ask1")),
        "change_percent": change_percent,
        "updated_at": _parse_datetime(_first(row, "\u66f4\u65b0\u65f6\u95f4", "time", "updated_at"))
        or datetime.now(timezone.utc),
    }


def map_akshare_kline(row: dict[str, Any], contract_code: str, period: str) -> dict[str, Any]:
    return {
        "contract_code": contract_code or row.get("contract_code"),
        "symbol": row.get("symbol") or _symbol_from_contract(contract_code),
        "period": period or row.get("period"),
        "trading_time": _parse_datetime(_first(row, "\u65f6\u95f4", "datetime", "trading_time")),
        "open_price": _to_float(_first(row, "\u5f00\u76d8", "open", "open_price")),
        "high_price": _to_float(_first(row, "\u6700\u9ad8", "high", "high_price")),
        "low_price": _to_float(_first(row, "\u6700\u4f4e", "low", "low_price")),
        "close_price": _to_float(_first(row, "\u6536\u76d8", "close", "close_price")),
        "volume": _to_int(_first(row, "\u6210\u4ea4\u91cf", "volume", "vol")),
        "open_interest": _to_int(_first(row, "\u6301\u4ed3\u91cf", "\u6301\u4ed3", "open_interest", "oi")),
    }


def map_tushare_realtime(raw: dict[str, Any], symbol: str = None) -> dict[str, Any]:
    close = _to_float(raw.get("close"))
    open_p = _to_float(raw.get("open"))
    pre_close = _to_float(raw.get("pre_close") or raw.get("pre_settle"))
    if pre_close and pre_close > 0 and close is not None:
        change_percent = round((close - pre_close) / pre_close * 100, 2)
    elif open_p and open_p > 0 and close is not None:
        change_percent = round((close - open_p) / open_p * 100, 2)
    else:
        change_percent = 0.0
    return {
        "symbol": symbol or raw.get("symbol") or _symbol_from_contract(raw.get("ts_code")),
        "current_price": close,
        "pre_settlement": pre_close,
        "open_price": open_p,
        "high": _to_float(raw.get("high")),
        "low": _to_float(raw.get("low")),
        "volume": _to_int(raw.get("vol")),
        "open_interest": _to_int(raw.get("oi")),
        "change_percent": change_percent,
        "updated_at": _parse_datetime(raw.get("trade_time") or raw.get("trade_date")) or datetime.now(timezone.utc),
    }


def map_tushare_kline(raw: dict[str, Any], contract_code: str = None, period: str = None) -> dict[str, Any]:
    return {
        "contract_code": contract_code or raw.get("contract_code"),
        "symbol": raw.get("symbol") or _symbol_from_contract(contract_code or raw.get("ts_code")),
        "period": period or raw.get("period"),
        "trading_time": _parse_datetime(raw.get("trade_time") or raw.get("trade_date") or raw.get("end_date")),
        "open_price": _to_float(raw.get("open")),
        "high_price": _to_float(raw.get("high")),
        "low_price": _to_float(raw.get("low")),
        "close_price": _to_float(raw.get("close")),
        "volume": _to_int(raw.get("vol")),
        "open_interest": _to_int(raw.get("oi")),
    }


def map_mock_realtime(raw: dict[str, Any], symbol: str = None) -> dict[str, Any]:
    return {
        "symbol": raw.get("symbol") or symbol,
        "current_price": _to_float(raw.get("current_price")),
        "pre_settlement": _to_float(raw.get("pre_settlement")),
        "open_price": _to_float(raw.get("open_price")),
        "high": _to_float(raw.get("high")),
        "low": _to_float(raw.get("low")),
        "volume": _to_int(raw.get("volume")),
        "open_interest": _to_int(raw.get("open_interest")),
        "change_percent": _to_float(raw.get("change_percent")),
        "updated_at": raw.get("updated_at") or datetime.now(timezone.utc),
    }


def map_mock_kline(raw: dict[str, Any], contract_code: str = None, period: str = None) -> dict[str, Any]:
    return {
        "contract_code": raw.get("contract_code") or contract_code,
        "symbol": raw.get("symbol") or _symbol_from_contract(contract_code),
        "period": raw.get("period") or period,
        "trading_time": raw.get("trading_time"),
        "open_price": _to_float(raw.get("open_price")),
        "high_price": _to_float(raw.get("high_price")),
        "low_price": _to_float(raw.get("low_price")),
        "close_price": _to_float(raw.get("close_price")),
        "volume": _to_int(raw.get("volume")),
        "open_interest": _to_int(raw.get("open_interest")),
    }


def map_tushare_fut_daily(raw: dict[str, Any], variety_id: int, period: str = "D") -> dict[str, Any]:
    return {
        "variety_id": variety_id,
        "ts_code": raw.get("ts_code"),
        "trade_date": _parse_datetime(raw.get("trade_date") or raw.get("end_date")),
        "pre_close": _to_float(raw.get("pre_close")),
        "pre_settle": _to_float(raw.get("pre_settle")),
        "open_price": _to_float(raw.get("open")),
        "high_price": _to_float(raw.get("high")),
        "low_price": _to_float(raw.get("low")),
        "close_price": _to_float(raw.get("close")),
        "settle": _to_float(raw.get("settle")),
        "change1": _to_float(raw.get("change1")),
        "change2": _to_float(raw.get("change2")),
        "volume": _to_int(raw.get("vol")),
        "amount": _to_float(raw.get("amount")),
        "open_interest": _to_int(raw.get("oi")),
        "oi_chg": _to_int(raw.get("oi_chg")),
        "period": period,
    }


def map_tushare_fut_settle(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts_code": raw.get("ts_code"),
        "trade_date": _parse_datetime(raw.get("trade_date")),
        "settle": _to_float(raw.get("settle")),
        "trading_fee_rate": _to_float(raw.get("trading_fee_rate")),
        "trading_fee": _to_float(raw.get("trading_fee")),
        "delivery_fee": _to_float(raw.get("delivery_fee")),
        "b_hedging_margin_rate": _to_float(raw.get("b_hedging_margin_rate")),
        "s_hedging_margin_rate": _to_float(raw.get("s_hedging_margin_rate")),
        "long_margin_rate": _to_float(raw.get("long_margin_rate")),
        "short_margin_rate": _to_float(raw.get("short_margin_rate")),
        "offset_today_fee": _to_float(raw.get("offset_today_fee")),
        "exchange": raw.get("exchange"),
    }


def map_tushare_fut_weekly_detail(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "exchange": raw.get("exchange"),
        "prd": raw.get("prd"),
        "name": raw.get("name"),
        "vol": _to_float(raw.get("vol")),
        "vol_yoy": _to_float(raw.get("vol_yoy")),
        "amount": _to_float(raw.get("amount")),
        "amout_yoy": _to_float(raw.get("amout_yoy") or raw.get("amount_yoy")),
        "cumvol": _to_float(raw.get("cumvol")),
        "cumvol_yoy": _to_float(raw.get("cumvol_yoy")),
        "cumamt": _to_float(raw.get("cumamt")),
        "cumamt_yoy": _to_float(raw.get("cumamt_yoy")),
        "open_interest": _to_float(raw.get("open_interest")),
        "interest_wow": _to_float(raw.get("interest_wow")),
        "mc_close": _to_float(raw.get("mc_close")),
        "close_wow": _to_float(raw.get("close_wow")),
        "week": raw.get("week"),
        "week_date": _parse_datetime(raw.get("week_date")),
    }


def map_tushare_fut_wsr(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": _parse_datetime(raw.get("trade_date")),
        "symbol": raw.get("symbol"),
        "fut_name": raw.get("fut_name"),
        "warehouse": raw.get("warehouse"),
        "wh_id": raw.get("wh_id"),
        "pre_vol": _to_int(raw.get("pre_vol")),
        "vol": _to_int(raw.get("vol")),
        "vol_chg": _to_int(raw.get("vol_chg")),
        "area": raw.get("area"),
        "year": raw.get("year"),
        "grade": raw.get("grade"),
        "brand": raw.get("brand"),
        "place": raw.get("place"),
        "pd": _to_int(raw.get("pd")),
        "is_ct": raw.get("is_ct"),
        "unit": raw.get("unit"),
        "exchange": raw.get("exchange"),
    }


def map_tushare_fut_holding(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": _parse_datetime(raw.get("trade_date")),
        "symbol": raw.get("symbol"),
        "broker": raw.get("broker"),
        "vol": _to_int(raw.get("vol")),
        "vol_chg": _to_int(raw.get("vol_chg")),
        "long_hld": _to_int(raw.get("long_hld")),
        "long_chg": _to_int(raw.get("long_chg")),
        "short_hld": _to_int(raw.get("short_hld")),
        "short_chg": _to_int(raw.get("short_chg")),
        "exchange": raw.get("exchange"),
    }


def map_tushare_ft_limit(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts_code": raw.get("ts_code"),
        "trade_date": _parse_datetime(raw.get("trade_date")),
        "up_limit": _to_float(raw.get("up_limit")),
        "down_limit": _to_float(raw.get("down_limit")),
        "exchange": raw.get("exchange"),
    }


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, "-", "", "None"):
            return row[key]
    return None


def _to_float(val: Any) -> float | None:
    if val in (None, "-", "", "None"):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _to_int(val: Any) -> int | None:
    if val in (None, "-", "", "None"):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _parse_datetime(val: Any):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    for fmt in [
        "%Y-%m-%d %H:%M:%S",
        "%Y%m%d %H:%M:%S",
        "%Y%m%d%H%M%S",
        "%Y-%m-%d",
        "%Y%m%d",
    ]:
        try:
            return datetime.strptime(str(val), fmt)
        except ValueError:
            continue
    return None


def _symbol_from_contract(contract_code: str | None) -> str | None:
    if not contract_code:
        return None
    base = contract_code.split(".")[0]
    letters = []
    for char in base:
        if char.isalpha():
            letters.append(char)
        else:
            break
    return "".join(letters).upper() or None
