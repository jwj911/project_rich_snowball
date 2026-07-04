"""Comment domain service."""

from models import UserDB
from schemas import CommentCreate, CommentResponse
from services.domain.exceptions import NotFoundError
from services.domain.repositories.comment_repository import CommentRepository


class CommentService:
    """评论领域服务。

    通过构造函数接收 Repository，支持在单元测试中注入 MockRepository
    以脱离真实数据库进行测试。
    """

    def __init__(self, db, repository: CommentRepository | None = None):
        self._db = db
        self._repo = repository or CommentRepository(db)

    def create_comment(
        self,
        user: UserDB,
        comment: CommentCreate,
    ) -> CommentResponse:
        variety = self._repo.get_variety(comment.variety_id)
        if not variety:
            raise NotFoundError("品种不存在")

        if comment.price_level_id:
            pl = self._repo.get_price_level(comment.price_level_id, user.id)
            if not pl:
                raise NotFoundError("关联的价位标注不存在")

        db_comment = self._repo.create(
            variety_id=comment.variety_id,
            user_id=user.id,
            price_level_id=comment.price_level_id,
            content=comment.content,
            sentiment=comment.sentiment,
        )

        return CommentResponse(
            id=db_comment.id,
            variety_id=db_comment.variety_id,
            product_symbol=variety.symbol if variety else None,
            product_name=variety.name if variety else None,
            variety_symbol=variety.symbol if variety else None,
            variety_name=variety.name if variety else None,
            user_id=db_comment.user_id,
            username=user.username,
            content=db_comment.content,
            sentiment=db_comment.sentiment,
            price_level_id=db_comment.price_level_id,
            created_at=db_comment.created_at,
        )

    def get_user_comments(
        self,
        username: str,
        skip: int,
        limit: int,
    ) -> list[CommentResponse]:
        user = self._repo.get_user(username)
        if not user:
            raise NotFoundError("用户不存在")

        comments = self._repo.list_by_user(user.id, skip, limit)

        return [
            CommentResponse(
                id=c.id,
                variety_id=c.variety_id,
                product_symbol=c.variety.symbol if c.variety else None,
                product_name=c.variety.name if c.variety else None,
                variety_symbol=c.variety.symbol if c.variety else None,
                variety_name=c.variety.name if c.variety else None,
                user_id=c.user_id,
                username=user.username,
                content=c.content,
                sentiment=c.sentiment,
                price_level_id=c.price_level_id,
                created_at=c.created_at,
            )
            for c in comments
        ]
