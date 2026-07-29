"""Realtime quotes 跨进程更新标记与 Redis 降级回归测试。"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from data_collector import scheduler as market_scheduler
from routers import realtime as realtime_router
from services import redis_client
from services import realtime_state


class FakeRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.read_error: Exception | None = None
        self.write_error: Exception | None = None

    def set(self, key: str, value: str) -> None:
        if self.write_error is not None:
            raise self.write_error
        self.values[key] = value

    def get(self, key: str) -> str | None:
        if self.read_error is not None:
            raise self.read_error
        return self.values.get(key)


@pytest.fixture(autouse=True)
def reset_realtime_state(monkeypatch):
    monkeypatch.setattr(realtime_state, "_last_update_time", datetime.min.replace(tzinfo=UTC))
    monkeypatch.setattr(realtime_state, "_shared_marker_degraded", False)
    monkeypatch.setattr(redis_client, "_redis_client", None)
    monkeypatch.setattr(redis_client, "_redis_available", None)
    monkeypatch.setattr(redis_client, "_redis_last_check", 0)


def _use_fake_redis(monkeypatch, fake_redis: FakeRedis) -> None:
    monkeypatch.setattr(realtime_state, "is_redis_available", lambda: True)
    monkeypatch.setattr(realtime_state, "get_redis_client", lambda: fake_redis)


def _load_isolated_realtime_state(module_name: str) -> ModuleType:
    module_path = Path(realtime_state.__file__)
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_successful_refresh_updates_local_and_shared_timestamp_only(monkeypatch):
    fake_redis = FakeRedis()
    update_time = datetime(2026, 7, 29, 15, 30, 45, 123456, tzinfo=UTC)
    _use_fake_redis(monkeypatch, fake_redis)
    monkeypatch.setattr(realtime_state, "_utc_now", lambda: update_time)

    realtime_state.mark_realtime_updated()

    marker = fake_redis.values[realtime_state.REALTIME_UPDATE_MARKER_KEY]
    assert realtime_state._last_update_time == update_time
    assert marker == update_time.isoformat()
    assert set(fake_redis.values) == {realtime_state.REALTIME_UPDATE_MARKER_KEY}
    assert "price" not in marker
    assert "quote" not in marker


def test_redis_write_failure_preserves_local_timestamp(monkeypatch, caplog):
    fake_redis = FakeRedis()
    update_time = datetime(2026, 7, 29, 15, 30, 45, tzinfo=UTC)
    fake_redis.write_error = RuntimeError("redis://:secret@private-host:6379/0")
    _use_fake_redis(monkeypatch, fake_redis)
    monkeypatch.setattr(realtime_state, "_utc_now", lambda: update_time)
    mark_unavailable = Mock()
    monkeypatch.setattr(realtime_state, "mark_redis_unavailable", mark_unavailable)

    with caplog.at_level(logging.WARNING, logger=realtime_state.__name__):
        realtime_state.mark_realtime_updated()

    assert realtime_state._last_update_time == update_time
    assert fake_redis.values == {}
    mark_unavailable.assert_called_once_with()
    assert "redis_write_failed" in caplog.text
    assert "secret" not in caplog.text
    assert "private-host" not in caplog.text


def test_api_process_reads_worker_marker_with_independent_module_state(monkeypatch):
    fake_redis = FakeRedis()
    worker_update_time = datetime(2026, 7, 29, 15, 31, tzinfo=UTC)
    worker_state = _load_isolated_realtime_state("_test_worker_realtime_state")
    api_state = _load_isolated_realtime_state("_test_api_realtime_state")
    try:
        for isolated_state in (worker_state, api_state):
            monkeypatch.setattr(isolated_state, "is_redis_available", lambda: True)
            monkeypatch.setattr(isolated_state, "get_redis_client", lambda: fake_redis)
        monkeypatch.setattr(worker_state, "_utc_now", lambda: worker_update_time)

        worker_state.mark_realtime_updated()
        state = api_state.get_realtime_update_state()

        assert worker_state._last_update_time == worker_update_time
        assert api_state._last_update_time == datetime.min.replace(tzinfo=UTC)
        assert state.last_update_time == worker_update_time
        assert state.shared_available is True
        assert state.force_refresh is False
    finally:
        sys.modules.pop(worker_state.__name__, None)
        sys.modules.pop(api_state.__name__, None)


def test_redis_degradation_preserves_local_state_and_forces_refresh_at_sixty_seconds(
    monkeypatch,
    caplog,
):
    local_update_time = datetime(2026, 7, 29, 15, 30, tzinfo=UTC)
    monkeypatch.setattr(realtime_state, "_last_update_time", local_update_time)
    monkeypatch.setattr(realtime_state, "is_redis_available", lambda: False)

    with caplog.at_level(logging.WARNING, logger=realtime_state.__name__):
        before_deadline = realtime_state.get_realtime_update_state(59.9)
        at_deadline = realtime_state.get_realtime_update_state(60)

    assert before_deadline.last_update_time == local_update_time
    assert before_deadline.shared_available is False
    assert before_deadline.force_refresh is False
    assert at_deadline.force_refresh is True
    assert caplog.text.count("realtime_update_marker_degraded") == 1
    assert "fallback_refresh_seconds=60" in caplog.text


def test_unconfigured_redis_uses_bounded_refresh_fallback(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(realtime_state, "is_redis_available", redis_client.is_redis_available)
    monkeypatch.setattr(realtime_state, "get_redis_client", redis_client.get_redis_client)
    monkeypatch.setattr(realtime_state, "mark_redis_unavailable", redis_client.mark_redis_unavailable)

    state = realtime_state.get_realtime_update_state(60)

    assert state.shared_available is False
    assert state.force_refresh is True
    assert redis_client.get_redis_client() is None


def test_runtime_redis_failure_logs_no_connection_details_and_recovers_after_retry(monkeypatch, caplog):
    disconnected_redis = FakeRedis()
    recovered_redis = FakeRedis()
    shared_update_time = datetime(2026, 7, 29, 15, 32, tzinfo=UTC)
    disconnected_redis.read_error = RuntimeError("redis://:secret@private-host:6379/0")
    recovered_redis.values[realtime_state.REALTIME_UPDATE_MARKER_KEY] = shared_update_time.isoformat()
    clock = [100.0]
    reconnect = Mock(return_value=recovered_redis)
    monkeypatch.setattr(redis_client, "_redis_client", disconnected_redis)
    monkeypatch.setattr(redis_client, "_redis_available", True)
    monkeypatch.setattr(redis_client.time, "time", lambda: clock[0])
    monkeypatch.setattr(redis_client, "_create_redis_client", reconnect)
    monkeypatch.setattr(realtime_state, "is_redis_available", redis_client.is_redis_available)
    monkeypatch.setattr(realtime_state, "get_redis_client", redis_client.get_redis_client)
    monkeypatch.setattr(realtime_state, "mark_redis_unavailable", redis_client.mark_redis_unavailable)

    with caplog.at_level(logging.INFO, logger=realtime_state.__name__):
        degraded = realtime_state.get_realtime_update_state(60)
        clock[0] += redis_client._redis_check_interval - 0.1
        still_degraded = realtime_state.get_realtime_update_state(60)
        clock[0] += 0.2
        recovered = realtime_state.get_realtime_update_state(0)

    assert degraded.shared_available is False
    assert degraded.force_refresh is True
    assert still_degraded.shared_available is False
    assert recovered.shared_available is True
    assert recovered.last_update_time == shared_update_time
    reconnect.assert_called_once_with()
    assert "redis_read_failed" in caplog.text
    assert "realtime_update_marker_redis_recovered" in caplog.text
    assert "secret" not in caplog.text
    assert "private-host" not in caplog.text


def test_redis_connection_failure_log_omits_connection_details(monkeypatch, caplog):
    import redis

    monkeypatch.setenv("REDIS_URL", "redis://:secret@private-host:6379/0")
    monkeypatch.setattr(
        redis,
        "from_url",
        Mock(side_effect=RuntimeError("redis://:secret@private-host:6379/0")),
    )

    with caplog.at_level(logging.WARNING, logger=redis_client.__name__):
        client = redis_client._create_redis_client()

    assert client is None
    assert "Redis connection failed, fallback to in-memory" in caplog.text
    assert "secret" not in caplog.text
    assert "private-host" not in caplog.text


class FakeSession:
    def close(self) -> None:
        pass


def _configure_scheduler_refresh(monkeypatch, pipeline) -> Mock:
    mark_updated = Mock()
    monkeypatch.setattr(market_scheduler, "_cn_date", lambda: date(2026, 7, 29))
    monkeypatch.setattr(market_scheduler, "is_trading_day", lambda value: True)
    monkeypatch.setattr(market_scheduler, "_pipeline", lambda name: pipeline)
    monkeypatch.setattr(market_scheduler, "SessionLocal", FakeSession)
    monkeypatch.setattr(
        market_scheduler,
        "_get_active_varieties",
        lambda db: [SimpleNamespace(symbol="AU")],
    )
    monkeypatch.setattr(market_scheduler, "_check_price_alerts", lambda db: None)
    monkeypatch.setattr(market_scheduler.MarketDataService, "invalidate_realtime_cache", lambda: None)
    monkeypatch.setattr(market_scheduler, "mark_realtime_updated", mark_updated)
    return mark_updated


def test_scheduler_publishes_marker_after_successful_refresh(monkeypatch):
    pipeline = SimpleNamespace(run_realtime=Mock(return_value={"processed": 1}))
    mark_updated = _configure_scheduler_refresh(monkeypatch, pipeline)

    market_scheduler.refresh_realtime_quotes()

    pipeline.run_realtime.assert_called_once_with(["AU"])
    mark_updated.assert_called_once_with()


def test_scheduler_does_not_publish_marker_after_failed_refresh(monkeypatch):
    pipeline = SimpleNamespace(run_realtime=Mock(side_effect=OSError("provider unavailable")))
    mark_updated = _configure_scheduler_refresh(monkeypatch, pipeline)

    with pytest.raises(OSError, match="provider unavailable"):
        market_scheduler.refresh_realtime_quotes()

    mark_updated.assert_not_called()


@pytest.mark.parametrize(
    "stats",
    [
        {"processed": 0, "failed": 1, "skipped": 0},
        {"processed": 0, "failed": 0, "skipped": 1, "circuit_open": True},
        {"processed": 0, "failed": 0, "skipped": 1},
    ],
)
def test_scheduler_does_not_publish_marker_for_incomplete_refresh(monkeypatch, stats):
    pipeline = SimpleNamespace(run_realtime=Mock(return_value=stats))
    mark_updated = _configure_scheduler_refresh(monkeypatch, pipeline)

    market_scheduler.refresh_realtime_quotes()

    mark_updated.assert_not_called()


def test_sse_generator_pushes_again_when_shared_marker_changes(monkeypatch):
    first_update = datetime(2026, 7, 29, 15, 30, tzinfo=UTC)
    second_update = datetime(2026, 7, 29, 15, 31, tzinfo=UTC)
    states = iter(
        [
            realtime_state.RealtimeUpdateState(first_update, True, False),
            realtime_state.RealtimeUpdateState(second_update, True, False),
        ]
    )
    fetch_realtime = Mock(
        side_effect=[
            (SimpleNamespace(id=7), [{"symbol": "AU", "current_price": 450}], []),
            (SimpleNamespace(id=7), [{"symbol": "AU", "current_price": 451}], []),
        ]
    )

    monkeypatch.setattr(realtime_router, "get_realtime_update_state", lambda elapsed: next(states))
    monkeypatch.setattr(realtime_router, "_sse_fetch_once", fetch_realtime)
    monkeypatch.setattr(realtime_router, "_sse_test_mode", lambda: False)

    async def no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(realtime_router.asyncio, "sleep", no_sleep)

    async def consume_two_updates() -> tuple[str, str]:
        generator = realtime_router._sse_realtime_generator(["AU"], "test-token", 7)
        try:
            return await generator.__anext__(), await generator.__anext__()
        finally:
            await generator.aclose()

    first_event, second_event = asyncio.run(consume_two_updates())

    assert '"current_price": 450' in first_event
    assert '"current_price": 451' in second_event
    assert fetch_realtime.call_count == 2


def test_sse_generator_force_refreshes_when_redis_is_degraded(monkeypatch):
    update_time = datetime(2026, 7, 29, 15, 30, tzinfo=UTC)
    states = iter(
        [
            realtime_state.RealtimeUpdateState(update_time, False, False),
            realtime_state.RealtimeUpdateState(update_time, False, True),
        ]
    )
    fetch_realtime = Mock(
        side_effect=[
            (SimpleNamespace(id=8), [{"symbol": "AU", "current_price": 450}], []),
            (SimpleNamespace(id=8), [{"symbol": "AU", "current_price": 452}], []),
        ]
    )

    monkeypatch.setattr(realtime_router, "get_realtime_update_state", lambda elapsed: next(states))
    monkeypatch.setattr(realtime_router, "_sse_fetch_once", fetch_realtime)
    monkeypatch.setattr(realtime_router, "_sse_test_mode", lambda: False)

    async def no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(realtime_router.asyncio, "sleep", no_sleep)

    async def consume_two_updates() -> tuple[str, str]:
        generator = realtime_router._sse_realtime_generator(["AU"], "test-token", 8)
        try:
            return await generator.__anext__(), await generator.__anext__()
        finally:
            await generator.aclose()

    first_event, second_event = asyncio.run(consume_two_updates())

    assert '"current_price": 450' in first_event
    assert '"current_price": 452' in second_event
    assert fetch_realtime.call_count == 2


def test_sse_generator_refreshes_once_when_redis_recovers_without_marker_change(monkeypatch):
    update_time = datetime(2026, 7, 29, 15, 30, tzinfo=UTC)
    states = iter(
        [
            realtime_state.RealtimeUpdateState(update_time, False, False),
            realtime_state.RealtimeUpdateState(update_time, True, False),
        ]
    )
    fetch_realtime = Mock(
        side_effect=[
            (SimpleNamespace(id=9), [{"symbol": "AU", "current_price": 450}], []),
            (SimpleNamespace(id=9), [{"symbol": "AU", "current_price": 453}], []),
        ]
    )

    monkeypatch.setattr(realtime_router, "get_realtime_update_state", lambda elapsed: next(states))
    monkeypatch.setattr(realtime_router, "_sse_fetch_once", fetch_realtime)
    monkeypatch.setattr(realtime_router, "_sse_test_mode", lambda: False)

    async def no_sleep(seconds: float) -> None:
        return None

    monkeypatch.setattr(realtime_router.asyncio, "sleep", no_sleep)

    async def consume_two_updates() -> tuple[str, str]:
        generator = realtime_router._sse_realtime_generator(["AU"], "test-token", 9)
        try:
            return await generator.__anext__(), await generator.__anext__()
        finally:
            await generator.aclose()

    first_event, second_event = asyncio.run(consume_two_updates())

    assert '"current_price": 450' in first_event
    assert '"current_price": 453' in second_event
    assert fetch_realtime.call_count == 2


def test_sse_generator_preserves_newer_connection_registration_during_old_cleanup(monkeypatch):
    update_time = datetime(2026, 7, 29, 15, 30, tzinfo=UTC)
    monkeypatch.setattr(
        realtime_router,
        "get_realtime_update_state",
        lambda elapsed: realtime_state.RealtimeUpdateState(update_time, True, False),
    )
    monkeypatch.setattr(
        realtime_router,
        "_sse_fetch_once",
        lambda symbols, token: (SimpleNamespace(id=10), [], []),
    )
    monkeypatch.setattr(realtime_router, "_sse_test_mode", lambda: False)

    async def exercise_cleanup() -> None:
        connection_store: dict[int, asyncio.Task] = {}
        monkeypatch.setattr(realtime_router, "_sse_connections", connection_store)
        monkeypatch.setattr(realtime_router, "_sse_connections_lock", asyncio.Lock())
        old_task = asyncio.create_task(asyncio.sleep(3600))
        replacement_task = asyncio.create_task(asyncio.sleep(3600))
        try:
            connection_store[10] = replacement_task
            old_generator = realtime_router._sse_realtime_generator(["AU"], "test-token", 10, old_task)
            await old_generator.__anext__()
            await old_generator.aclose()
            assert connection_store[10] is replacement_task

            connection_store[10] = old_task
            active_generator = realtime_router._sse_realtime_generator(["AU"], "test-token", 10, old_task)
            await active_generator.__anext__()
            await active_generator.aclose()
            assert 10 not in connection_store
        finally:
            old_task.cancel()
            replacement_task.cancel()
            await asyncio.gather(old_task, replacement_task, return_exceptions=True)

    asyncio.run(exercise_cleanup())


def test_sse_generator_keeps_heartbeat_contract(monkeypatch):
    monkeypatch.setattr(realtime_router, "SSE_HEARTBEAT_INTERVAL", 0)

    async def read_heartbeat() -> str:
        generator = realtime_router._sse_realtime_generator(["AU"], "test-token", 11)
        try:
            return await generator.__anext__()
        finally:
            await generator.aclose()

    assert asyncio.run(read_heartbeat()) == ":heartbeat\n\n"
