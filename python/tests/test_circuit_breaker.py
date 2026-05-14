"""熔断器测试。"""
import pytest
from services.circuit_breaker import (
    is_circuit_open,
    record_failure,
    record_success,
    get_circuit_status,
    CIRCUIT_THRESHOLD,
)


@pytest.fixture(autouse=True)
def reset_circuits():
    """每个测试前重置熔断器状态。"""
    import services.circuit_breaker as cb
    with cb._LOCK:
        cb._FAILURE_COUNTS.clear()
        cb._LAST_FAILURE_TIME.clear()
    yield
    with cb._LOCK:
        cb._FAILURE_COUNTS.clear()
        cb._LAST_FAILURE_TIME.clear()


def test_circuit_closed_by_default():
    assert is_circuit_open("tushare") is False


def test_circuit_opens_after_threshold():
    for _ in range(CIRCUIT_THRESHOLD):
        record_failure("tushare")
    assert is_circuit_open("tushare") is True


def test_circuit_closes_after_success():
    for _ in range(CIRCUIT_THRESHOLD):
        record_failure("tushare")
    assert is_circuit_open("tushare") is True

    record_success("tushare")
    assert is_circuit_open("tushare") is False


def test_different_sources_isolated():
    for _ in range(CIRCUIT_THRESHOLD):
        record_failure("tushare")
    assert is_circuit_open("tushare") is True
    assert is_circuit_open("akshare") is False


def test_get_circuit_status():
    record_failure("tushare")
    status = get_circuit_status("tushare")
    assert status["source"] == "tushare"
    assert status["failure_count"] == 1
    assert status["is_open"] is False
    assert status["threshold"] == CIRCUIT_THRESHOLD


def test_get_circuit_status_all():
    record_failure("tushare")
    record_failure("akshare")
    all_status = get_circuit_status()
    assert "tushare" in all_status
    assert "akshare" in all_status
