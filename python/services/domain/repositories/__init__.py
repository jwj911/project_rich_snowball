"""领域服务层 Repository（数据访问抽象）。

将 SQLAlchemy 查询逻辑从 Service 中分离，使 Service 可脱离真实数据库进行单元测试。
"""

from services.domain.repositories.comment_repository import CommentRepository
from services.domain.repositories.price_level_repository import PriceLevelRepository
from services.domain.repositories.product_repository import ProductRepository
from services.domain.repositories.watchlist_repository import WatchlistRepository

__all__ = [
    "CommentRepository",
    "PriceLevelRepository",
    "ProductRepository",
    "WatchlistRepository",
]
