import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

from .base import BaseCollector

logger = logging.getLogger("data.tushare")

_EXCHANGE_SUFFIX_MAP = {
    "SHFE": ".SHF",
    "DCE": ".DCE",
    "ZCE": ".ZCE",
    "CZCE": ".ZCE",
    "INE": ".INE",
    "CFFEX": ".CFX",
    "GFEX": ".GFE",
}

_TUSHARE_EXCHANGE_MAP = {
    "SHFE": "SHFE",
    "DCE": "DCE",
    "ZCE": "CZCE",
    "CZCE": "CZCE",
    "INE": "INE",
    "CFFEX": "CFFEX",
    "GFEX": "GFEX",
}

_MINUTE_FREQ_MAP = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "60min",
    "60m": "60min",
}


def _extract_symbol(contract_code: str) -> str:
    match = re.match(r"^([A-Za-z]+)", contract_code or "")
    if not match:
        raise ValueError(f"Cannot extract symbol from contract_code: {contract_code}")
    return match.group(1).upper()


def _exchange_suffix(exchange: str) -> str:
    suffix = _EXCHANGE_SUFFIX_MAP.get(exchange)
    if not suffix:
        raise ValueError(f"Unsupported exchange for tushare: {exchange}")
    return suffix


def _to_continuous_ts_code(contract_code: str, exchange: str) -> str:
    """Build Tushare continuous/main-contract code, for example AU.SHF."""
    return f"{_extract_symbol(contract_code)}{_exchange_suffix(exchange)}"


def _to_contract_ts_code(contract_code: str, exchange: str) -> str:
    """Build Tushare concrete contract code, for example AU2506.SHF."""
    return f"{contract_code.upper()}{_exchange_suffix(exchange)}"


def _to_tushare_exchange(exchange: str) -> str:
    mapped = _TUSHARE_EXCHANGE_MAP.get(exchange)
    if not mapped:
        raise ValueError(f"Unsupported exchange for tushare: {exchange}")
    return mapped


def _calc_start_datetime(period: str, limit: int) -> datetime:
    freq_minutes = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "60m": 60,
        "1d": 1440,
        "1w": 10080,
    }
    minutes = freq_minutes.get(period, 60)
    return datetime.now() - timedelta(minutes=int(minutes * limit * 2))


def _date_to_week(value: str | None) -> str | None:
    if not value:
        return None
    if re.match(r"^\d{6}$", value):
        return value
    dt = datetime.strptime(value, "%Y%m%d")
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}{iso_week:02d}"


def _sort_by_time(df):
    for column in ("trade_time", "trade_date", "end_date"):
        if column in df.columns:
            return df.sort_values(column)
    return df


class TushareCollector(BaseCollector):
    """Tushare Pro futures collector.

    The collector returns Tushare-shaped raw rows. Field normalization is kept
    in adapters.py so fallback collectors can share the same pipeline.
    """

    def __init__(self):
        from config import TUSHARE_TOKEN

        if not TUSHARE_TOKEN or TUSHARE_TOKEN == "your-tushare-token-here":
            raise ValueError("TUSHARE_TOKEN is not configured")
        try:
            import tushare as ts

            ts.set_token(TUSHARE_TOKEN)
            self.pro = ts.pro_api()
            self.ts = ts
        except ImportError:
            raise ImportError("tushare is not installed. Run: pip install tushare")

    def _retry(self, func, max_retries=3):
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                wait = 2**attempt
                logger.warning("[retry %s/%s] %s, waiting %ss", attempt + 1, max_retries, e, wait)
                if attempt < max_retries - 1:
                    time.sleep(wait)
                else:
                    logger.error("Max retries exceeded: %s", e)
                    raise

    def _query_variety(self, symbol: str = None, contract_code: str = None):
        from models import SessionLocal, VarietyDB

        db = SessionLocal()
        try:
            if symbol:
                v = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
            elif contract_code:
                v = db.query(VarietyDB).filter(VarietyDB.contract_code == contract_code).first()
            else:
                return None
            if not v:
                return None
            return {"symbol": v.symbol, "contract_code": v.contract_code, "exchange": v.exchange}
        finally:
            db.close()

    def fetch_realtime(self, symbol: str) -> Dict[str, Any] | None:
        info = self._query_variety(symbol=symbol)
        if not info:
            logger.warning("Variety not found for symbol: %s", symbol)
            return None

        rows = self.fetch_kline(info["contract_code"], "1m", limit=1)
        if rows:
            rows[-1]["symbol"] = symbol
            return rows[-1]

        ts_code = _to_contract_ts_code(info["contract_code"], info["exchange"])
        today = datetime.now().strftime("%Y%m%d")

        def _do():
            df = self.pro.fut_daily(ts_code=ts_code, start_date=today, end_date=today)
            if df is None or df.empty:
                continuous_code = _to_continuous_ts_code(info["contract_code"], info["exchange"])
                df = self.pro.fut_daily(ts_code=continuous_code, start_date=today, end_date=today)
            if df is None or df.empty:
                return None
            row = _sort_by_time(df).iloc[-1].to_dict()
            row["symbol"] = symbol
            return row

        return self._retry(_do)

    def fetch_kline(self, contract_code: str, period: str, limit: int = 100) -> List[Dict[str, Any]]:
        info = self._query_variety(contract_code=contract_code)
        if not info:
            logger.warning("Variety not found for contract: %s", contract_code)
            return []

        if period in _MINUTE_FREQ_MAP:
            return self._fetch_ft_mins(info, period, limit)
        if period in ("1d", "D"):
            return self._fetch_fut_daily_for_kline(info, limit)
        if period in ("1w", "W"):
            return self.fetch_weekly(_to_contract_ts_code(contract_code, info["exchange"]), "", "")[-limit:]
        if period in ("1M", "M", "1mo"):
            return self.fetch_monthly(_to_contract_ts_code(contract_code, info["exchange"]), "", "")[-limit:]
        raise ValueError(f"Unsupported Tushare kline period: {period}")

    def _fetch_ft_mins(self, info: dict[str, Any], period: str, limit: int) -> List[Dict[str, Any]]:
        ts_code = _to_contract_ts_code(info["contract_code"], info["exchange"])
        start = _calc_start_datetime(period, limit).strftime("%Y-%m-%d %H:%M:%S")
        end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        def _do():
            df = self.pro.ft_mins(
                ts_code=ts_code,
                freq=_MINUTE_FREQ_MAP[period],
                start_date=start,
                end_date=end,
            )
            if df is None or df.empty:
                return []
            return self._market_df_to_records(df, ts_code, info, limit=limit)

        return self._retry(_do)

    def _fetch_fut_daily_for_kline(self, info: dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        ts_code = _to_contract_ts_code(info["contract_code"], info["exchange"])
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=max(limit * 2, 30))).strftime("%Y%m%d")

        def _do():
            df = self.pro.fut_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if df is None or df.empty:
                continuous_code = _to_continuous_ts_code(info["contract_code"], info["exchange"])
                df = self.pro.fut_daily(ts_code=continuous_code, start_date=start_date, end_date=end_date)
                ts = continuous_code
            else:
                ts = ts_code
            if df is None or df.empty:
                return []
            return self._market_df_to_records(df, ts, info, limit=limit)

        return self._retry(_do)

    def fetch_daily(self, ts_code: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        def _do():
            df = self.pro.fut_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            if df is None or df.empty:
                return []
            return self._market_df_to_records(df, ts_code)

        return self._retry(_do)

    def fetch_weekly(self, ts_code: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        return self._fetch_weekly_monthly(ts_code, start_date, end_date, freq="week")

    def fetch_monthly(self, ts_code: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        return self._fetch_weekly_monthly(ts_code, start_date, end_date, freq="month")

    def _fetch_weekly_monthly(self, ts_code: str, start_date: str, end_date: str, freq: str) -> List[Dict[str, Any]]:
        def _do():
            kwargs = {"ts_code": ts_code, "freq": freq}
            if start_date:
                kwargs["start_date"] = start_date
            if end_date:
                kwargs["end_date"] = end_date
            df = self.pro.fut_weekly_monthly(**kwargs)
            if df is None or df.empty:
                return []
            return self._market_df_to_records(df, ts_code)

        return self._retry(_do)

    def _market_df_to_records(
        self,
        df,
        ts_code: str,
        info: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> List[Dict[str, Any]]:
        rows = _sort_by_time(df)
        if limit:
            rows = rows.tail(limit)
        records = []
        for _, row in rows.iterrows():
            item = row.to_dict()
            item.setdefault("ts_code", ts_code)
            if info:
                item["contract_code"] = info["contract_code"]
                item["symbol"] = info["symbol"]
            records.append(item)
        return records

    def fetch_basic(
        self,
        exchange: str,
        fut_type: str = "1",
        fut_code: str = None,
        list_date: str = None,
    ) -> List[Dict[str, Any]]:
        tushare_exchange = _to_tushare_exchange(exchange)

        def _do():
            kwargs = {"exchange": tushare_exchange, "fut_type": fut_type}
            if fut_code:
                kwargs["fut_code"] = fut_code.upper()
            if list_date:
                kwargs["list_date"] = list_date
            df = self.pro.fut_basic(**kwargs)
            if df is None or df.empty:
                return []
            return df.to_dict("records")

        return self._retry(_do)

    def fetch_mapping(self, ts_code: str = None, trade_date: str = None) -> List[Dict[str, Any]]:
        def _do():
            kwargs = {}
            if ts_code:
                kwargs["ts_code"] = ts_code
            if trade_date:
                kwargs["trade_date"] = trade_date
            df = self.pro.fut_mapping(**kwargs)
            if df is None or df.empty:
                return []
            return df.to_dict("records")

        return self._retry(_do)

    def fetch_settle(self, trade_date: str, exchange: str = None) -> List[Dict[str, Any]]:
        def _do():
            kwargs = {"trade_date": trade_date}
            if exchange:
                kwargs["exchange"] = _to_tushare_exchange(exchange)
            df = self.pro.fut_settle(**kwargs)
            if df is None or df.empty:
                return []
            return df.to_dict("records")

        return self._retry(_do)

    def fetch_weekly_detail(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        def _do():
            kwargs = {}
            start_week = _date_to_week(start_date)
            end_week = _date_to_week(end_date)
            if start_week:
                kwargs["start_week"] = start_week
            if end_week:
                kwargs["end_week"] = end_week
            df = self.pro.fut_weekly_detail(**kwargs)
            if df is None or df.empty:
                return []
            return df.to_dict("records")

        return self._retry(_do)

    def fetch_wsr(self, trade_date: str, symbol: str = None) -> List[Dict[str, Any]]:
        def _do():
            kwargs = {"trade_date": trade_date}
            if symbol:
                kwargs["symbol"] = symbol.upper()
            df = self.pro.fut_wsr(**kwargs)
            if df is None or df.empty:
                return []
            return df.to_dict("records")

        return self._retry(_do)

    def fetch_holding(self, trade_date: str, symbol: str = None, exchange: str = None) -> List[Dict[str, Any]]:
        def _do():
            kwargs = {"trade_date": trade_date}
            if symbol:
                kwargs["symbol"] = symbol.upper()
            if exchange:
                kwargs["exchange"] = _to_tushare_exchange(exchange)
            df = self.pro.fut_holding(**kwargs)
            if df is None or df.empty:
                return []
            return df.to_dict("records")

        return self._retry(_do)

    def fetch_limit(self, trade_date: str = None, ts_code: str = None) -> List[Dict[str, Any]]:
        def _do():
            kwargs = {}
            if trade_date:
                kwargs["trade_date"] = trade_date
            if ts_code:
                kwargs["ts_code"] = ts_code
            df = self.pro.ft_limit(**kwargs)
            if df is None or df.empty:
                return []
            return df.to_dict("records")

        return self._retry(_do)
