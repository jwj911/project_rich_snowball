"""领域服务层通用异常。"""


class ServiceError(Exception):
    """业务逻辑错误基类。"""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(ServiceError):
    """资源不存在。"""

    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, 404)


class ForbiddenError(ServiceError):
    """无权操作。"""

    def __init__(self, message: str = "无权操作"):
        super().__init__(message, 403)


class ConflictError(ServiceError):
    """资源冲突（重复、唯一约束等）。"""

    def __init__(self, message: str = "资源已存在"):
        super().__init__(message, 409)
