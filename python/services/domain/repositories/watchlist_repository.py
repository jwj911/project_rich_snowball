"""Watchlist 数据访问层。"""

from sqlalchemy.orm import Session, joinedload

from models import WatchlistDB


class WatchlistRepository:
    """自选相关的数据库操作，供 WatchlistService 使用。"""

    def __init__(self, db: Session):
        self._db = db

    def list_by_user(
        self,
        user_id: int,
        variety_id: int | None = None,
        skip: int = 0,
        limit: int = 100,
        with_variety: bool = True,
    ) -> list[WatchlistDB]:
        query = self._db.query(WatchlistDB).filter(WatchlistDB.user_id == user_id)
        if with_variety:
            query = query.options(joinedload(WatchlistDB.variety))
        if variety_id is not None:
            query = query.filter(WatchlistDB.variety_id == variety_id)
        return query.order_by(WatchlistDB.created_at.desc()).offset(skip).limit(limit).all()

    def get_by_id(self, watchlist_id: int) -> WatchlistDB | None:
        return self._db.query(WatchlistDB).filter(WatchlistDB.id == watchlist_id).first()

    def create(
        self,
        user_id: int,
        variety_id: int,
        notes: str | None,
    ) -> WatchlistDB:
        w = WatchlistDB(
            user_id=user_id,
            variety_id=variety_id,
            notes=notes,
            is_notified=False,
        )
        self._db.add(w)
        self._db.commit()
        self._db.refresh(w)
        return w

    def update(self, watchlist: WatchlistDB) -> WatchlistDB:
        self._db.commit()
        self._db.refresh(watchlist)
        return watchlist

    def delete(self, watchlist: WatchlistDB) -> None:
        self._db.delete(watchlist)
        self._db.commit()
