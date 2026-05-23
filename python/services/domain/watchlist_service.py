"""自选（Watchlist）领域服务。"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from models import VarietyDB, WatchlistDB
from schemas import WatchlistCreate, WatchlistUpdate
from services.domain.exceptions import ConflictError, ForbiddenError, NotFoundError


class WatchlistService:
    """自选业务逻辑封装。路由层仅保留 HTTP 协议转换。"""

    @staticmethod
    def list_watchlists(
        db: Session, user_id: int, variety_id: int | None = None,
        skip: int = 0, limit: int = 100,
    ) -> list[WatchlistDB]:
        query = (
            db.query(WatchlistDB)
            .options(joinedload(WatchlistDB.variety))
            .filter(WatchlistDB.user_id == user_id)
        )
        if variety_id:
            query = query.filter(WatchlistDB.variety_id == variety_id)
        return query.order_by(WatchlistDB.created_at.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def create_watchlist(db: Session, user_id: int, item: WatchlistCreate) -> WatchlistDB:
        variety = db.query(VarietyDB).filter(VarietyDB.id == item.variety_id).first()
        if not variety:
            raise NotFoundError("品种不存在")

        w = WatchlistDB(
            user_id=user_id,
            variety_id=item.variety_id,
            notes=item.notes,
            is_notified=False,
        )
        db.add(w)
        try:
            db.commit()
            db.refresh(w)
        except IntegrityError:
            db.rollback()
            raise ConflictError("该品种已在自选列表中")

        return w

    @staticmethod
    def _get_and_check_owner(db: Session, user_id: int, watchlist_id: int) -> WatchlistDB:
        """获取自选记录并校验所有权。内部复用方法。"""
        w = db.query(WatchlistDB).filter(WatchlistDB.id == watchlist_id).first()
        if not w:
            raise NotFoundError("自选记录不存在")
        if w.user_id != user_id:
            raise ForbiddenError("无权操作")
        return w

    @staticmethod
    def update_watchlist(
        db: Session, user_id: int, watchlist_id: int, item: WatchlistUpdate
    ) -> WatchlistDB:
        w = WatchlistService._get_and_check_owner(db, user_id, watchlist_id)

        if item.notes is not None:
            w.notes = item.notes
        if item.is_notified is not None:
            w.is_notified = item.is_notified

        db.commit()
        db.refresh(w)
        return w

    @staticmethod
    def delete_watchlist(db: Session, user_id: int, watchlist_id: int) -> None:
        w = WatchlistService._get_and_check_owner(db, user_id, watchlist_id)
        db.delete(w)
        db.commit()
