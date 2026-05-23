"""Tests for to_trading_date night-session mapping."""
from datetime import date, datetime, timedelta, timezone

import pytest

from services.trading_calendar import to_trading_date

CN_TZ = timezone(timedelta(hours=8))
UTC = timezone.utc


class TestToTradingDate:
    """期货交易日归属规则验证。"""

    def test_daytime_belongs_to_same_day(self):
        """白天数据归属到当前自然日。"""
        dt = datetime(2024, 1, 15, 14, 30, tzinfo=CN_TZ)
        assert to_trading_date(dt) == date(2024, 1, 15)

    def test_night_session_start_belongs_to_next_day(self):
        """夜盘开始（21:00）归属到下一自然日。"""
        dt = datetime(2024, 1, 15, 21, 0, tzinfo=CN_TZ)
        assert to_trading_date(dt) == date(2024, 1, 16)

    def test_night_session_late_belongs_to_next_day(self):
        """夜盘深夜（23:00）归属到下一自然日。"""
        dt = datetime(2024, 1, 15, 23, 0, tzinfo=CN_TZ)
        assert to_trading_date(dt) == date(2024, 1, 16)

    def test_early_morning_belongs_to_same_day(self):
        """凌晨夜盘延续（00:30）归属到当前自然日（已是下一交易日）。"""
        dt = datetime(2024, 1, 16, 0, 30, tzinfo=CN_TZ)
        assert to_trading_date(dt) == date(2024, 1, 16)

    def test_night_session_end_belongs_to_same_day(self):
        """凌晨接近夜盘结束（02:30）归属到当前自然日。"""
        dt = datetime(2024, 1, 16, 2, 30, tzinfo=CN_TZ)
        assert to_trading_date(dt) == date(2024, 1, 16)

    def test_20_hour_boundary(self):
        """20:00 是夜盘归属的临界点。"""
        dt = datetime(2024, 1, 15, 19, 59, tzinfo=CN_TZ)
        assert to_trading_date(dt) == date(2024, 1, 15)

        dt = datetime(2024, 1, 15, 20, 0, tzinfo=CN_TZ)
        assert to_trading_date(dt) == date(2024, 1, 16)

    def test_utc_input(self):
        """UTC 输入能正确转换到东八区规则。"""
        # 2024-01-15 13:00 UTC = 2024-01-15 21:00 CST (night session)
        dt = datetime(2024, 1, 15, 13, 0, tzinfo=UTC)
        assert to_trading_date(dt) == date(2024, 1, 16)

    def test_naive_input_treated_as_utc(self):
        """naive datetime 视为 UTC 向后兼容。"""
        # 14:30 UTC = 22:30 CST (night session) -> next day
        dt = datetime(2024, 1, 15, 14, 30)  # naive
        assert to_trading_date(dt) == date(2024, 1, 16)

    def test_weekend_night_session(self):
        """周五夜盘归属到周六自然日（是否交易日由 is_trading_day 判断）。"""
        dt = datetime(2024, 1, 12, 21, 30, tzinfo=CN_TZ)  # Friday night
        assert to_trading_date(dt) == date(2024, 1, 13)
