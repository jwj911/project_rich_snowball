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


# ========== 鉴权归属加固测试 ==========


def test_create_frontend_log_with_token_ignores_client_user_id(
    client, db_session_with_logs, auth_headers
):
    """携带有效 token 时，忽略客户端传入的 user_id，使用 token 中的用户。"""
    payload = {
        "type": "exception",
        "payload": {"error": "FakeError"},
        "user_id": 99999,  # 伪造的 user_id
    }
    r = client.post("/api/log/frontend", json=payload, headers=auth_headers)
    assert r.status_code == 202

    logs = db_session_with_logs.query(FrontendLogDB).all()
    assert len(logs) == 1
    # token 对应的是 integration_tester，不是 99999
    assert logs[0].user_id is not None
    assert logs[0].user_id != 99999


def test_create_frontend_log_without_token_is_anonymous(
    client, db_session_with_logs
):
    """未携带 token 时，日志匿名入库，user_id 为 None。"""
    payload = {
        "type": "exception",
        "payload": {"error": "AnonymousError"},
        "user_id": 88888,  # 伪造的 user_id，应被忽略
    }
    r = client.post("/api/log/frontend", json=payload)
    assert r.status_code == 202

    logs = db_session_with_logs.query(FrontendLogDB).all()
    assert len(logs) == 1
    assert logs[0].user_id is None


# ========== Payload 限制测试 ==========


def test_create_frontend_log_oversized_payload_rejected(client, db_session_with_logs):
    """payload + meta 超过 8KB 时返回 422。"""
    payload = {
        "type": "exception",
        "payload": {"large_text": "x" * (9 * 1024)},
    }
    r = client.post("/api/log/frontend", json=payload)
    assert r.status_code == 422

    # 数据库不应写入
    logs = db_session_with_logs.query(FrontendLogDB).all()
    assert len(logs) == 0


def test_create_frontend_log_deep_nested_payload_rejected(client, db_session_with_logs):
    """payload 嵌套深度超过 3 层时返回 422。"""
    payload = {
        "type": "exception",
        "payload": {
            "l1": {
                "l2": {
                    "l3": {
                        "l4": "too deep",
                    },
                },
            },
        },
    }
    r = client.post("/api/log/frontend", json=payload)
    assert r.status_code == 422

    logs = db_session_with_logs.query(FrontendLogDB).all()
    assert len(logs) == 0


def test_create_frontend_log_too_many_keys_rejected(client, db_session_with_logs):
    """payload 键数量超过 20 个时返回 422。"""
    payload = {
        "type": "exception",
        "payload": {f"key_{i}": i for i in range(21)},
    }
    r = client.post("/api/log/frontend", json=payload)
    assert r.status_code == 422

    logs = db_session_with_logs.query(FrontendLogDB).all()
    assert len(logs) == 0


def test_create_frontend_log_exactly_max_depth_accepted(client, db_session_with_logs):
    """payload 嵌套深度恰好为 3 层时应被接受。"""
    payload = {
        "type": "exception",
        "payload": {
            "l1": {
                "l2": {
                    "l3": "exactly 3 levels",
                },
            },
        },
    }
    r = client.post("/api/log/frontend", json=payload)
    assert r.status_code == 202

    logs = db_session_with_logs.query(FrontendLogDB).all()
    assert len(logs) == 1


def test_create_frontend_log_exactly_max_keys_accepted(client, db_session_with_logs):
    """payload 键数量恰好为 20 个时应被接受。"""
    payload = {
        "type": "exception",
        "payload": {f"key_{i}": i for i in range(20)},
    }
    r = client.post("/api/log/frontend", json=payload)
    assert r.status_code == 202

    logs = db_session_with_logs.query(FrontendLogDB).all()
    assert len(logs) == 1
