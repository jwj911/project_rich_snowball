"""
领域服务层（Domain Service Layer）。

将路由中的业务编排、数据持久化逻辑下沉到 Service，使路由仅保留 HTTP 协议转换职责。
"""

from services.domain.comment_service import CommentService
from services.domain.price_level_service import PriceLevelService
from services.domain.product_service import ProductService
from services.domain.watchlist_service import WatchlistService
from services.domain.workspace_service import WorkspaceService
from services.domain.repositories import (
    CommentRepository,
    PriceLevelRepository,
    ProductRepository,
    WatchlistRepository,
)

__all__ = [
    "CommentRepository",
    "CommentService",
    "PriceLevelRepository",
    "PriceLevelService",
    "ProductRepository",
    "ProductService",
    "WatchlistRepository",
    "WatchlistService",
    "WorkspaceService",
]
