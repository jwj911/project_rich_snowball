"""自选（Watchlist）领域服务。"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import VarietyDB, WatchlistDB
from schemas import WatchlistCreate, WatchlistUpdate
from services.domain.exceptions import ConflictError, ForbiddenError, NotFoundError
from services.domain.repositories.watchlist_repository import WatchlistRepository


class WatchlistService:
    """自选业务逻辑封装。路由层仅保留 HTTP 协议转换。

    通过构造函数接收 Repository，支持在单元测试中注入 MockRepository
    以脱离真实数据库进行测试。
    """

    def __init__(self, db: Session, repository: WatchlistRepository | None = None):
        self._db = db
        self._repo = repository or WatchlistRepository(db)

    def list_watchlists(
        self,
        user_id: int,
        variety_id: int | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[WatchlistDB]:
        return self._repo.list_by_user(user_id, variety_id, skip, limit)

    def create_watchlist(self, user_id: int, item: WatchlistCreate) -> WatchlistDB:
        variety = self._db.query(VarietyDB).filter(VarietyDB.id == item.variety_id).first()
        if not variety:
            raise NotFoundError("品种不存在")

        try:
            return self._repo.create(
                user_id=user_id,
                variety_id=item.variety_id,
                notes=item.notes,
            )
        except IntegrityError:
            self._db.rollback()
            raise ConflictError("该品种已在自选列表中")

    def _get_and_check_owner(self, user_id: int, watchlist_id: int) -> WatchlistDB:
        """获取自选记录并校验所有权。内部复用方法。"""
        w = self._repo.get_by_id(watchlist_id)
        if not w:
            raise NotFoundError("自选记录不存在")
        if w.user_id != user_id:
            raise ForbiddenError("无权操作")
        return w

    def update_watchlist(
        self, user_id: int, watchlist_id: int, item: WatchlistUpdate
    ) -> WatchlistDB:
        w = self._get_and_check_owner(user_id, watchlist_id)

        if item.notes is not None:
            w.notes = item.notes
        if item.is_notified is not None:
            w.is_notified = item.is_notified

        return self._repo.update(w)

    def delete_watchlist(self, user_id: int, watchlist_id: int) -> None:
        w = self._get_and_check_owner(user_id, watchlist_id)
        self._repo.delete(w)
