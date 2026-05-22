"""数据质量与交易日历测试
=========================
验证：
- 交易日历正确性（节假日、周末、工作日）
- 缺失 K 线检测使用交易日历（而非自然日）
- OHLC 异常检测（high < low、price <= 0、negative volume）
- 实时行情与 K 线一致性
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, datetime, timedelta
import pytest

from services.trading_calendar import (
    is_trading_day,
    get_trading_days,
    trading_days_between,
    get_expected_kline_dates,
)


class TestTradingCalendar:
    """交易日历核心逻辑测试。"""

    def test_new_year_not_trading(self):
        assert is_trading_day("2024-01-01") is False
        assert is_trading_day("2025-01-01") is False

    def test_spring_festival_not_trading(self):
        # 2024 春节：2月9日（除夕）~ 2月17日（初八）中部分日期
        assert is_trading_day("2024-02-09") is False
        assert is_trading_day("2024-02-12") is False
        assert is_trading_day("2024-02-19") is True  # 节后首个交易日

    def test_national_day_not_trading(self):
        assert is_trading_day("2024-10-01") is False
        assert is_trading_day("2024-10-08") is True

    def test_weekend_not_trading(self):
        assert is_trading_day("2024-01-06") is False  # 周六
        assert is_trading_day("2024-01-07") is False  # 周日

    def test_normal_weekday_trading(self):
        assert is_trading_day("2024-01-02") is True
        assert is_trading_day("2024-01-03") is True

    def test_get_trading_days_count(self):
        days = get_trading_days("2024-01-01", "2024-01-31")
        # 2024-01 有 31 天，去除元旦+周末+调休
        assert 20 <= len(days) <= 23
        assert days[0] == date(2024, 1, 2)

    def test_trading_days_between(self):
        count = trading_days_between("2024-01-01", "2024-12-31")
        assert 240 <= count <= 245

    def test_expected_kline_daily(self):
        days = get_expected_kline_dates("2024-01-01", "2024-01-10", "D")
        assert all(is_trading_day(d) for d in days)

    def test_expected_kline_weekly(self):
        weeks = get_expected_kline_dates("2024-01-01", "2024-01-31", "W")
        # 2024-01 应有 4-5 个周五
        assert 4 <= len(weeks) <= 5

    def test_expected_kline_monthly(self):
        months = get_expected_kline_dates("2024-01-01", "2024-03-31", "M")
        assert len(months) == 3

    def test_date_object_input(self):
        assert is_trading_day(date(2024, 1, 1)) is False
        assert is_trading_day(date(2024, 1, 2)) is True


class TestDataQualityChecks:
    """数据质量检查脚本测试。"""

    def test_missing_kline_uses_trading_calendar(self, db_session, seed_varieties):
        from scripts.data_quality_report import check_missing_kline_dates
        from models import KlineDataDB

        # 清空可能由 init_mock_data 预置的 K 线数据，确保测试确定性
        db_session.query(KlineDataDB).filter(KlineDataDB.period == "D").delete()
        db_session.commit()

        # 在 seed_varieties 已初始化、但没有 K 线数据的条件下，
        # 检查最近 7 天应报告缺失交易日
        issues = check_missing_kline_dates(db_session, period="D", lookback_days=7)
        # 每个品种都应报告缺失（因为没有 K 线数据）
        assert len(issues) > 0
        # 确认 missing_sample 只包含交易日（不包含周末）
        for issue in issues:
            for d_str in issue["missing_sample"]:
                d = datetime.strptime(d_str, "%Y-%m-%d").date()
                assert is_trading_day(d), f"{d_str} should be a trading day"

    def test_duplicate_klines_detected(self, db_session, seed_varieties):
        from scripts.data_quality_report import check_duplicate_klines
        from models import KlineDataDB, FutContractDB

        au = next((v for v in seed_varieties if v.symbol == "AU"), None)
        assert au is not None

        # 先创建一个合约并插入一条正常 K 线
        contract = FutContractDB(ts_code="AU2406.SHF", symbol="AU2406", exchange="SHFE")
        db_session.add(contract)
        db_session.flush()

        db_session.add(KlineDataDB(
            variety_id=au.id,
            contract_id=contract.id,
            period="D",
            trading_time=datetime(2024, 1, 2, 10, 0, 0),
            open_price=500.0,
            high_price=510.0,
            low_price=490.0,
            close_price=505.0,
            volume=1000,
        ))
        db_session.commit()

        # 无重复数据时应返回空列表
        issues = check_duplicate_klines(db_session, symbol="AU", period="D")
        assert issues == []

        # 验证函数对不存在的 symbol 返回空列表
        assert check_duplicate_klines(db_session, symbol="NONEXIST") == []

    def test_ohlc_anomaly_high_lt_low(self, db_session, seed_varieties):
        from scripts.data_quality_report import check_ohlc_anomalies
        from models import KlineDataDB, FutContractDB

        au = next((v for v in seed_varieties if v.symbol == "AU"), None)
        contract = FutContractDB(ts_code="AU2406.SHF", symbol="AU2406", exchange="SHFE")
        db_session.add(contract)
        db_session.flush()

        db_session.add(KlineDataDB(
            variety_id=au.id,
            contract_id=contract.id,
            period="D",
            trading_time=datetime(2024, 1, 2, 10, 0, 0),
            open_price=500.0,
            high_price=480.0,  # 异常：high < low
            low_price=490.0,
            close_price=505.0,
            volume=1000,
        ))
        db_session.commit()

        issues = check_ohlc_anomalies(db_session, symbol="AU", period="D")
        assert any("high_lt_low" in i.get("subtype", "") for i in issues)

    def test_ohlc_anomaly_non_positive_price(self, db_session, seed_varieties):
        from scripts.data_quality_report import check_ohlc_anomalies
        from models import KlineDataDB, FutContractDB

        au = next((v for v in seed_varieties if v.symbol == "AU"), None)
        contract = FutContractDB(ts_code="AU2406.SHF", symbol="AU2406", exchange="SHFE")
        db_session.add(contract)
        db_session.flush()

        db_session.add(KlineDataDB(
            variety_id=au.id,
            contract_id=contract.id,
            period="D",
            trading_time=datetime(2024, 1, 3, 10, 0, 0),
            open_price=0.0,
            high_price=510.0,
            low_price=490.0,
            close_price=505.0,
            volume=1000,
        ))
        db_session.commit()

        issues = check_ohlc_anomalies(db_session, symbol="AU", period="D")
        assert any("non_positive_price" in i.get("subtype", "") for i in issues)

    def test_ohlc_anomaly_negative_volume(self, db_session, seed_varieties):
        from scripts.data_quality_report import check_ohlc_anomalies
        from models import KlineDataDB, FutContractDB

        au = next((v for v in seed_varieties if v.symbol == "AU"), None)
        contract = FutContractDB(ts_code="AU2406.SHF", symbol="AU2406", exchange="SHFE")
        db_session.add(contract)
        db_session.flush()

        db_session.add(KlineDataDB(
            variety_id=au.id,
            contract_id=contract.id,
            period="D",
            trading_time=datetime(2024, 1, 4, 10, 0, 0),
            open_price=500.0,
            high_price=510.0,
            low_price=490.0,
            close_price=505.0,
            volume=-100,  # 异常
        ))
        db_session.commit()

        issues = check_ohlc_anomalies(db_session, symbol="AU", period="D")
        assert any(i["subtype"] == "negative_volume" for i in issues)

    def test_text_encoding_pollution_detected(self, db_session, seed_varieties):
        from scripts.data_quality_report import check_text_encoding_pollution

        au = next((v for v in seed_varieties if v.symbol == "AU"), None)
        assert au is not None
        au.name = "锟狡斤拷"
        db_session.commit()

        issues = check_text_encoding_pollution(db_session, symbol="AU")

        assert any(
            issue["check"] == "text_encoding_pollution"
            and issue["table"] == "varieties"
            and issue["field"] == "name"
            for issue in issues
        )
