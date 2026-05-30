"""ServiceError 全局异常处理器测试
==============================
验证 main.py 中注册的 service_error_handler 能正确映射
ServiceError 及其子类到统一错误体。
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-service-error-handler")
os.environ["ENABLE_SCHEDULER"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import APIRouter

from main import app
from services.domain.exceptions import ConflictError, ForbiddenError, NotFoundError, ServiceError


# 临时注册测试路由，触发各类 ServiceError
_test_router = APIRouter(prefix="/__test_service_errors")


@_test_router.get("/not-found")
def _raise_not_found():
    raise NotFoundError("资源未找到")


@_test_router.get("/forbidden")
def _raise_forbidden():
    raise ForbiddenError("无权操作")


@_test_router.get("/conflict")
def _raise_conflict():
    raise ConflictError("资源冲突")


@_test_router.get("/generic")
def _raise_generic_service_error():
    raise ServiceError("通用业务错误", status_code=418)


app.include_router(_test_router)


class TestServiceErrorHandler:
    def test_not_found_error_returns_404(self, client, auth_headers):
        """NotFoundError 应返回 404 和统一错误体。"""
        r = client.get("/__test_service_errors/not-found", headers=auth_headers)
        assert r.status_code == 404
        data = r.json()
        assert data["code"] == "NOT_FOUND_ERROR"
        assert data["message"] == "资源未找到"
        assert "timestamp" in data

    def test_forbidden_error_returns_403(self, client, auth_headers):
        """ForbiddenError 应返回 403 和统一错误体。"""
        r = client.get("/__test_service_errors/forbidden", headers=auth_headers)
        assert r.status_code == 403
        data = r.json()
        assert data["code"] == "FORBIDDEN_ERROR"
        assert data["message"] == "无权操作"

    def test_conflict_error_returns_409(self, client, auth_headers):
        """ConflictError 应返回 409 和统一错误体。"""
        r = client.get("/__test_service_errors/conflict", headers=auth_headers)
        assert r.status_code == 409
        data = r.json()
        assert data["code"] == "CONFLICT_ERROR"
        assert data["message"] == "资源冲突"

    def test_generic_service_error_returns_custom_status(self, client, auth_headers):
        """自定义 status_code 的 ServiceError 应正确映射。"""
        r = client.get("/__test_service_errors/generic", headers=auth_headers)
        assert r.status_code == 418
        data = r.json()
        assert data["code"] == "SERVICE_ERROR"
        assert data["message"] == "通用业务错误"
