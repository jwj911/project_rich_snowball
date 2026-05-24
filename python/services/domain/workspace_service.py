"""工作区聚合领域服务。

将用户工作区的多维度数据聚合逻辑从路由层下沉到 Service，
使路由仅保留 HTTP 协议转换职责。
"""

from sqlalchemy.orm import Session

from models import UserDB
from schemas import CommentResponse, PriceLevelResponse, WatchlistResponse, WorkspaceSummary
from services.domain.repositories.comment_repository import CommentRepository
from services.domain.repositories.price_level_repository import PriceLevelRepository
from services.domain.repositories.watchlist_repository import WatchlistRepository


class WorkspaceService:
    """工作区聚合服务。

    通过构造函数接收 Repository，支持在单元测试中注入 MockRepository
    以脱离真实数据库进行测试。
    """

    def __init__(
        self,
        db: Session,
        price_level_repo: PriceLevelRepository | None = None,
        watchlist_repo: WatchlistRepository | None = None,
        comment_repo: CommentRepository | None = None,
    ):
        self._db = db
        self._price_level_repo = price_level_repo or PriceLevelRepository(db)
        self._watchlist_repo = watchlist_repo or WatchlistRepository(db)
        self._comment_repo = comment_repo or CommentRepository(db)

    def get_workspace_summary(self, user: UserDB) -> WorkspaceSummary:
        """聚合当前用户的价位标注、自选和最近评论。"""
        user_id = user.id

        price_levels_rows = self._price_level_repo.list_by_user(
            user_id, skip=0, limit=100
        )
        price_levels = [
            PriceLevelResponse(
                id=pl.id,
                user_id=pl.user_id,
                variety_id=pl.variety_id,
                variety_symbol=pl.variety.symbol if pl.variety else None,
                variety_name=pl.variety.name if pl.variety else None,
                type=pl.type,
                price=pl.price,
                note=pl.note,
                source=pl.source,
                created_at=pl.created_at,
                updated_at=pl.updated_at,
            )
            for pl in price_levels_rows
        ]

        watchlist_rows = self._watchlist_repo.list_by_user(user_id, skip=0, limit=100)
        watchlists = [
            WatchlistResponse(
                id=w.id,
                user_id=w.user_id,
                variety_id=w.variety_id,
                variety_symbol=w.variety.symbol if w.variety else "",
                variety_name=w.variety.name if w.variety else "",
                notes=w.notes,
                is_notified=w.is_notified,
                created_at=w.created_at,
            )
            for w in watchlist_rows
        ]

        comments_rows = self._comment_repo.list_by_user(user_id, skip=0, limit=20)
        recent_comments = [
            CommentResponse(
                id=c.id,
                product_id=c.product_id,
                product_symbol=c.product.symbol if c.product else None,
                product_name=c.product.name if c.product else None,
                user_id=c.user_id,
                username=user.username,
                content=c.content,
                price_level_id=c.price_level_id,
                created_at=c.created_at,
            )
            for c in comments_rows
        ]

        return WorkspaceSummary(
            price_levels=price_levels,
            watchlists=watchlists,
            recent_comments=recent_comments,
        )
