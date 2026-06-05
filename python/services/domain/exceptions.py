"""领域服务层通用异常。"""

from errors import ErrorCode


class ServiceError(Exception):
    """业务逻辑错误基类。

    支持传入稳定的业务错误码（ErrorCode），若未提供则按异常类名推导。
    """

    _default_code = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        code: ErrorCode | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.code = code or self._default_code
        super().__init__(message)


class NotFoundError(ServiceError):
    """资源不存在。"""

    _default_code = ErrorCode.NOT_FOUND

    def __init__(self, message: str = "资源不存在", code: ErrorCode | None = None):
        super().__init__(message, 404, code)


class ForbiddenError(ServiceError):
    """无权操作。"""

    _default_code = ErrorCode.FORBIDDEN

    def __init__(self, message: str = "无权操作", code: ErrorCode | None = None):
        super().__init__(message, 403, code)


class ConflictError(ServiceError):
    """资源冲突（重复、唯一约束等）。"""

    _default_code = ErrorCode.CONFLICT

    def __init__(self, message: str = "资源已存在", code: ErrorCode | None = None):
        super().__init__(message, 409, code)


class UnauthorizedError(ServiceError):
    """未认证或认证无效。"""

    _default_code = ErrorCode.UNAUTHORIZED

    def __init__(self, message: str = "未登录或 token 无效", code: ErrorCode | None = None):
        super().__init__(message, 401, code)


class ValidationError(ServiceError):
    """业务校验失败（区别于 Pydantic 的 RequestValidationError）。"""

    _default_code = ErrorCode.VALIDATION_ERROR

    def __init__(self, message: str = "校验失败", code: ErrorCode | None = None):
        super().__init__(message, 400, code)
