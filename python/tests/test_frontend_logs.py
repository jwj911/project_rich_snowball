"""前端监控日志接收端点测试。"""

import json

import pytest
from sqlalchemy import text

from models import FrontendLogDB


@pytest.fixture
def db_session_with_logs(db_session):
    """确保测试前后清理 frontend_logs 表。"""
    db_session.execute(text("DELETE FROM frontend_logs"))
    db_session.commit()
    yield db_session
    db_session.execute(text("DELETE FROM frontend_logs"))
    db_session.commit()


def test_create_frontend_log_accepted(client, db_session_with_logs):
    """正常接收前端日志，返回 202。"""
    payload = {
        "type": "exception",
        "payload": {"error": "TestError", "message": "something went wrong"},
        "level": "error",
        "meta": {
            "url": "http://localhost:3200/products/AU",
            "ua": "Mozilla/5.0",
            "release": "v1.0.0",
            "environment": "test",
            "timestamp": "2026-05-28T12:00:00Z",
        },
    }
    r = client.post("/api/log/frontend", json=payload)
    assert r.status_code == 202
    assert r.json()["ok"] is True

    # 验证数据库写入
    logs = db_session_with_logs.query(FrontendLogDB).all()
    assert len(logs) == 1
    log = logs[0]
    assert log.log_type == "exception"
    assert log.level == "error"
    assert log.url == "http://localhost:3200/products/AU"
    assert log.release == "v1.0.0"
    assert log.environment == "test"
    assert "TestError" in log.payload_json


def test_create_frontend_log_web_vitals(client, db_session_with_logs):
    """接收 Web Vitals 数据。"""
    payload = {
        "type": "web-vitals",
        "payload": {"name": "LCP", "value": 1.2, "id": "v1-123", "route": "/products/AU"},
        "meta": {
            "url": "http://localhost:3200/products/AU",
            "ua": "Mozilla/5.0",
            "release": "v1.0.0",
            "environment": "test",
        },
    }
    r = client.post("/api/log/frontend", json=payload)
    assert r.status_code == 202

    logs = db_session_with_logs.query(FrontendLogDB).all()
    assert len(logs) == 1
    assert logs[0].log_type == "web-vitals"
    payload_data = json.loads(logs[0].payload_json)
    assert payload_data["name"] == "LCP"


def test_create_frontend_log_no_meta(client, db_session_with_logs):
    """meta 为空时也能正常接收。"""
    payload = {
        "type": "message",
        "payload": {"message": "hello"},
        "level": "info",
    }
    r = client.post("/api/log/frontend", json=payload)
    assert r.status_code == 202

    logs = db_session_with_logs.query(FrontendLogDB).all()
    assert len(logs) == 1
    assert logs[0].url is None
    assert logs[0].user_agent is None


def test_create_frontend_log_rate_limited(client):
    """写入端点应被全局限流中间件覆盖。"""
    # 快速发送超过限流阈值的请求（默认 60 秒 100 请求）
    # 这里只发少量请求验证端点可达即可，真实限流测试在 test_rate_limit_middleware.py
    payload = {"type": "message", "payload": {}}
    r = client.post("/api/log/frontend", json=payload)
    assert r.status_code == 202
