"""中国期货市场交易日历服务。

数据来源：
    - 主数据源：内置 JSON（由 AKShare 上交所交易日历导出）
    - Fallback：周六周日 + 内置主要法定节假日

适用说明：
    中国各期货交易所（SHFE/DCE/ZCE/INE/CFFEX/GFEX）的交易日历
    与 A 股交易日历基本一致，仅有少数品种夜盘差异不影响日线级判断。
"""

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# 东八区时区常量（中国标准时间）
_CN_TZ = timezone(timedelta(hours=8))


def _cn_now() -> datetime:
    """返回东八区当前时间（aware datetime）。"""
    return datetime.now(_CN_TZ)


def _cn_date() -> date:
    """返回东八区当前日期。"""
    return _cn_now().date()

# 内置真正固定不变的法定节假日（公历日期）
# 格式：MM-DD。年份由调用方动态组装。
# 注意：清明、劳动节、端午、中秋等浮动假期已移至 _FLOATING_HOLIDAYS 按年份精确维护
_BUILTIN_HOLIDAYS = {
    "01-01",   # 元旦
    "10-01", "10-02", "10-03",  # 国庆节法定假日（10/4-7 为调休，已在 FLOATING 中维护）
}

# 浮动假期的年份-日期映射（按国务院办公厅公布的年度节假日安排）
# 数据来源：国务院发布的年度节假日安排通知 + 期货交易所实际休市公告
# 后续可通过 scripts/update_trading_calendar.py 从 AKShare 拉取更新 JSON 文件
_FLOATING_HOLIDAYS = {
    # ===== 2024年（已结束，仅作 fallback 备用）=====
    2024: [
        "02-09", "02-10", "02-11", "02-12", "02-13", "02-14", "02-15", "02-16", "02-17",  # 春节（国务院 2/10-2/17，交易所含除夕）
        "04-04", "04-05", "04-06",  # 清明
        "05-01", "05-02", "05-03", "05-04", "05-05",  # 劳动节
        "06-10",  # 端午
        "09-15", "09-16", "09-17",  # 中秋
        "10-01", "10-02", "10-03", "10-04", "10-05", "10-06", "10-07",  # 国庆
    ],
    # ===== 2025年 =====
    2025: [
        "01-28", "01-29", "01-30", "01-31", "02-01", "02-02", "02-03", "02-04",  # 春节（8天）
        "04-04", "04-05", "04-06",  # 清明
        "05-01", "05-02", "05-03", "05-04", "05-05",  # 劳动节
        "05-31", "06-01", "06-02",  # 端午
        "10-01", "10-02", "10-03", "10-04", "10-05", "10-06", "10-07", "10-08",  # 国庆+中秋（8天）
    ],
    # ===== 2026年（修正：原硬编码春节 02-17~02-24 错误，实际为 02-15~02-23）=====
    2026: [
        "02-15", "02-16", "02-17", "02-18", "02-19", "02-20", "02-21", "02-22", "02-23",  # 春节（9天，除夕 2/15 逢周五）
        "04-04", "04-05", "04-06",  # 清明
        "05-01", "05-02", "05-03", "05-04", "05-05",  # 劳动节
        "06-19", "06-20", "06-21",  # 端午（修正：原硬编码 06-10 错误）
        "09-25", "09-26", "09-27",  # 中秋（修正：原硬编码 09-15~09-17 错误）
        "10-01", "10-02", "10-03", "10-04", "10-05", "10-06", "10-07",  # 国庆
    ],
    # ===== 2027年（预测，待国务院正式公布后更新）=====
    2027: [
        "02-05", "02-06", "02-07", "02-08", "02-09", "02-10", "02-11", "02-12", "02-13",  # 春节（9天，除夕 2/5 逢周五）
        "04-03", "04-04", "04-05",  # 清明（预测：清明 4/5 周一，连上周末）
        "05-01", "05-02", "05-03", "05-04", "05-05",  # 劳动节
        "06-09",  # 端午（预测：6/9 周三，按规则仅当天放假）
        "09-15", "09-16", "09-17", "09-18",  # 中秋（预测，待确认）
        "10-01", "10-02", "10-03", "10-04", "10-05", "10-06", "10-07",  # 国庆
    ],
    # ===== 2028年（预测，国庆节与中秋节合并放假 8 天）=====
    2028: [
        "01-25", "01-26", "01-27", "01-28", "01-29", "01-30", "01-31", "02-01",  # 春节（8天，除夕 1/25 周二）
        "04-04", "04-05", "04-06",  # 清明（预测）
        "05-01", "05-02", "05-03", "05-04", "05-05",  # 劳动节
        "05-31", "06-01", "06-02",  # 端午（预测）
        "10-01", "10-02", "10-03", "10-04", "10-05", "10-06", "10-07", "10-08",  # 国庆+中秋（8天）
    ],
    # ===== 2029年（预测）=====
    2029: [
        "02-12", "02-13", "02-14", "02-15", "02-16", "02-17", "02-18", "02-19",  # 春节（8天，除夕 2/12 周一）
        "04-04", "04-05", "04-06",  # 清明（预测）
        "05-01", "05-02", "05-03", "05-04", "05-05",  # 劳动节
        "06-07", "06-08", "06-09",  # 端午（预测：6/9 周六）
        "09-15", "09-16", "09-17",  # 中秋（预测）
        "10-01", "10-02", "10-03", "10-04", "10-05", "10-06", "10-07",  # 国庆
    ],
    # ===== 2030年（预测）=====
    2030: [
        "02-02", "02-03", "02-04", "02-05", "02-06", "02-07", "02-08", "02-09",  # 春节（8天，除夕 2/2 周六）
        "04-05", "04-06", "04-07",  # 清明（预测：清明 4/5 周六，连上周末）
        "05-01", "05-02", "05-03", "05-04", "05-05",  # 劳动节
        "06-05", "06-06", "06-07",  # 端午（预测）
        "10-01", "10-02", "10-03", "10-04", "10-05", "10-06", "10-07", "10-08",  # 国庆+中秋（8天，预测）
    ],
}


class TradingCalendar:
    """交易日历，基于内置 JSON 或 fallback 规则。"""

    _instance: Optional["TradingCalendar"] = None
    _trading_days: set[date]
    _min_date: date
    _max_date: date

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        """加载交易日历。"""
        json_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "trading_calendar.json"
        )
        if os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as f:
                dates_str = json.load(f)
            self._trading_days = {datetime.strptime(d, "%Y-%m-%d").date() for d in dates_str}
            self._min_date = min(self._trading_days)
            self._max_date = max(self._trading_days)
            logger.info("Loaded trading calendar: %s dates, range %s ~ %s",
                        len(self._trading_days), self._min_date, self._max_date)
        else:
            logger.warning("Trading calendar JSON not found at %s, using fallback", json_path)
            self._trading_days = set()
            self._min_date = date(1900, 1, 1)
            self._max_date = date(2100, 12, 31)

    def is_trading_day(self, d: date | datetime | str) -> bool:
        """判断某日是否为期货交易日。

        支持 date、datetime、'YYYY-MM-DD' 字符串。
        """
        if isinstance(d, str):
            d = datetime.strptime(d, "%Y-%m-%d").date()
        elif isinstance(d, datetime):
            d = d.date()

        # JSON 覆盖范围内直接使用
        if self._min_date <= d <= self._max_date:
            return d in self._trading_days

        # 范围外使用 fallback
        return self._fallback_is_trading_day(d)

    def get_trading_days(self, start: date | datetime | str, end: date | datetime | str) -> list[date]:
        """返回 [start, end] 区间内的所有期货交易日（升序）。"""
        if isinstance(start, str):
            start = datetime.strptime(start, "%Y-%m-%d").date()
        elif isinstance(start, datetime):
            start = start.date()

        if isinstance(end, str):
            end = datetime.strptime(end, "%Y-%m-%d").date()
        elif isinstance(end, datetime):
            end = end.date()

        if start > end:
            return []

        # JSON 覆盖范围内直接使用集合交集
        if self._min_date <= start and end <= self._max_date:
            return sorted([d for d in self._trading_days if start <= d <= end])

        # 混合或超范围：逐日 fallback
        result = []
        d = start
        while d <= end:
            if self.is_trading_day(d):
                result.append(d)
            d += timedelta(days=1)
        return result

    def trading_days_between(self, start: date | datetime | str, end: date | datetime | str) -> int:
        """返回 [start, end] 区间内的交易日数量。"""
        return len(self.get_trading_days(start, end))

    def get_expected_kline_dates(self, start: date | datetime | str, end: date | datetime | str, period: str = "D") -> list[date]:
        """返回某周期下预期应有 K 线的日期列表。

        日线(D)：每个交易日一条。
        周线(W)：每个自然周五（若周五非交易日则前移）一条。简化实现：每个周五。
        月线(M)：每个自然月最后一条。简化实现：每月最后一个交易日。
        """
        trading_days = self.get_trading_days(start, end)
        if period == "D":
            return trading_days
        if period == "W":
            # 每周五（或该周最后一个交易日）
            weeks = {}
            for d in trading_days:
                iso = d.isocalendar()
                key = (iso.year, iso.week)
                weeks[key] = d
            return sorted(weeks.values())
        if period == "M":
            months = {}
            for d in trading_days:
                key = (d.year, d.month)
                months[key] = d
            return sorted(months.values())
        # 分钟/小时周期：日内连续，不做缺失判断
        return []

    @staticmethod
    def _fallback_is_trading_day(d: date) -> bool:
        """基于规则的 fallback：周六周日 + 内置节假日。"""
        # 周末不交易
        if d.weekday() >= 5:  # 5=周六, 6=周日
            return False

        # 固定节假日
        md = d.strftime("%m-%d")
        if md in _BUILTIN_HOLIDAYS:
            return False

        # 浮动节假日（春节等）
        year_holidays = _FLOATING_HOLIDAYS.get(d.year, [])
        if md in year_holidays:
            return False

        return True


# 模块级便捷函数（无需显式实例化）
_is_trading_day = None
_get_trading_days = None
_trading_days_between = None
_get_expected_kline_dates = None


def _ensure_funcs():
    global _is_trading_day, _get_trading_days, _trading_days_between, _get_expected_kline_dates
    if _is_trading_day is None:
        cal = TradingCalendar()
        _is_trading_day = cal.is_trading_day
        _get_trading_days = cal.get_trading_days
        _trading_days_between = cal.trading_days_between
        _get_expected_kline_dates = cal.get_expected_kline_dates


def is_trading_day(d: date | datetime | str) -> bool:
    _ensure_funcs()
    return _is_trading_day(d)


def get_trading_days(start: date | datetime | str, end: date | datetime | str) -> list[date]:
    _ensure_funcs()
    return _get_trading_days(start, end)


def trading_days_between(start: date | datetime | str, end: date | datetime | str) -> int:
    _ensure_funcs()
    return _trading_days_between(start, end)


def get_expected_kline_dates(start: date | datetime | str, end: date | datetime | str, period: str = "D") -> list[date]:
    _ensure_funcs()
    return _get_expected_kline_dates(start, end, period)


def to_trading_date(dt: datetime) -> date:
    """将实际时间戳映射到中国期货交易日。

    规则（基于交易所普遍口径）：
    - 夜盘开始时间（20:00 及以后）的数据归属到下一自然日。
      例如 1 月 15 日 21:00 的夜盘数据 → 交易日 1 月 16 日。
    - 凌晨（00:00 - 03:59）的数据属于夜盘延续，归属到当前自然日
      （因为当前自然日已经是夜盘对应的交易日）。
      例如 1 月 16 日 00:30 的数据 → 交易日 1 月 16 日。
    - 白天数据（04:00 - 19:59）归属到当前自然日。

    注意：本函数仅做时间到自然日的映射，不验证该自然日是否为实际交易日
    （是否为节假日由 is_trading_day 判断）。
    """
    if dt.tzinfo is None:
        # naive datetime 视为 UTC，向后兼容
        dt = dt.replace(tzinfo=timezone.utc)
    cn_dt = dt.astimezone(_CN_TZ)
    if cn_dt.hour >= 20:
        return (cn_dt + timedelta(days=1)).date()
    return cn_dt.date()
