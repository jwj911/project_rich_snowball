"""API 版本治理中间件。

将 ``/api/v1/*`` 请求透明地映射到 ``/api/*``，使前端可以逐步迁移到带版本号的路径，
同时保持现有 ``/api/*`` 路径完全兼容。

未来废弃 ``/api/`` 时，只需调整各 router 的 ``prefix`` 为 ``/api/v1`` 并移除此中间件。
"""

from starlette.types import ASGIApp, Receive, Scope, Send


class ApiVersionMiddleware:
    """ASGI 中间件：为所有 ``/api`` 路由提供 ``/api/v1`` 版本别名。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/api/v1/"):
            scope["path"] = "/api" + scope["path"][len("/api/v1") :]
            raw_path = scope.get("raw_path")
            if raw_path and raw_path.startswith(b"/api/v1/"):
                scope["raw_path"] = b"/api" + raw_path[len(b"/api/v1") :]
        await self.app(scope, receive, send)
