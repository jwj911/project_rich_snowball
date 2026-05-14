"""Scheduler 健康检查与任务状态测试。"""
import pytest
from datetime import datetime, timezone, timedelta

from models import DataIngestionRunDB


def test_scheduler_check_returns_enabled_state(client, db_session):
    resp = client.get("/health/scheduler")
    assert resp.status_code == 200
    data = resp.json()
    assert "scheduler_enabled" in data
    assert "scheduler_running" in data
    assert "recent_runs" in data
    assert "runs" in data
    assert "circuit_breakers" in data
    assert "timestamp" in data


def test_scheduler_check_recent_runs_stats(client, db_session):
    # 插入一些测试数据
    now = datetime.now(timezone.utc)
    for i in range(3):
        run = DataIngestionRunDB(
            job_name="refresh_realtime_quotes",
            source="MockCollector",
            started_at=now - timedelta(minutes=i * 10),
            finished_at=now - timedelta(minutes=i * 10) + timedelta(seconds=5),
            duration_ms=5000,
            status="success",
            success_count=10,
            failed_count=0,
            skipped_count=0,
        )
        db_session.add(run)
    db_session.commit()

    resp = client.get("/health/scheduler")
    assert resp.status_code == 200
    data = resp.json()
    recent = data["recent_runs"]
    assert recent["total"] == 3
    assert recent["success"] == 3
    assert recent["failed"] == 0
    assert recent["success_rate"] == 1.0
    assert recent["last_success"] is not None
    assert recent["avg_duration_ms"] == 5000


def test_scheduler_check_with_failed_runs(client, db_session):
    now = datetime.now(timezone.utc)
    run = DataIngestionRunDB(
        job_name="sync_kline_1d",
        source="TushareCollector",
        started_at=now - timedelta(minutes=5),
        finished_at=now - timedelta(minutes=5) + timedelta(seconds=2),
        duration_ms=2000,
        status="failed",
        success_count=0,
        failed_count=5,
        skipped_count=0,
        error_message="quota exceeded",
        error_sample="quota exceeded",
    )
    db_session.add(run)
    db_session.commit()

    resp = client.get("/health/scheduler")
    assert resp.status_code == 200
    data = resp.json()
    recent = data["recent_runs"]
    assert recent["total"] == 1
    assert recent["success"] == 0
    assert recent["failed"] == 1
    assert recent["success_rate"] == 0.0
    assert recent["last_success"] is None


def test_scheduler_check_runs_list_limited(client, db_session):
    now = datetime.now(timezone.utc)
    for i in range(15):
        run = DataIngestionRunDB(
            job_name="refresh_realtime_quotes",
            source="MockCollector",
            started_at=now - timedelta(minutes=i),
            finished_at=now - timedelta(minutes=i) + timedelta(seconds=1),
            duration_ms=1000,
            status="success",
            success_count=1,
            failed_count=0,
            skipped_count=0,
        )
        db_session.add(run)
    db_session.commit()

    resp = client.get("/health/scheduler")
    assert resp.status_code == 200
    data = resp.json()
    # runs 列表限制为最近 10 条
    assert len(data["runs"]) == 10
    # recent_runs 统计基于最近 20 条
    assert data["recent_runs"]["total"] == 15
