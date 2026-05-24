"""PriceLevel 数据访问层。"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from models import PriceLevelDB


class PriceLevelRepository:
    """价位标注相关的数据库操作，供 PriceLevelService 使用。"""

    def __init__(self, db: Session):
        self._db = db

    def list_by_user(
        self,
        user_id: int,
        variety_id: int | None = None,
        type: str | None = None,
        skip: int = 0,
        limit: int = 100,
        with_variety: bool = True,
    ) -> list[PriceLevelDB]:
        query = self._db.query(PriceLevelDB).filter(PriceLevelDB.user_id == user_id)
        if with_variety:
            query = query.options(joinedload(PriceLevelDB.variety))
        if variety_id is not None:
            query = query.filter(PriceLevelDB.variety_id == variety_id)
        if type is not None:
            query = query.filter(PriceLevelDB.type == type)
        return query.order_by(PriceLevelDB.created_at.desc()).offset(skip).limit(limit).all()

    def get_by_id(self, price_level_id: int) -> PriceLevelDB | None:
        return self._db.query(PriceLevelDB).filter(PriceLevelDB.id == price_level_id).first()

    def check_duplicate(
        self,
        user_id: int,
        variety_id: int,
        type: str,
        price,
        exclude_id: int | None = None,
    ) -> bool:
        query = self._db.query(PriceLevelDB).filter(
            PriceLevelDB.user_id == user_id,
            PriceLevelDB.variety_id == variety_id,
            PriceLevelDB.type == type,
            PriceLevelDB.price == price,
        )
        if exclude_id is not None:
            query = query.filter(PriceLevelDB.id != exclude_id)
        return query.first() is not None

    def create(
        self,
        user_id: int,
        variety_id: int,
        type: str,
        price,
        note: str | None,
    ) -> PriceLevelDB:
        pl = PriceLevelDB(
            user_id=user_id,
            variety_id=variety_id,
            type=type,
            price=price,
            note=note,
            source="manual",
        )
        self._db.add(pl)
        self._db.commit()
        self._db.refresh(pl)
        return pl

    def update(self, price_level: PriceLevelDB) -> PriceLevelDB:
        self._db.commit()
        self._db.refresh(price_level)
        return price_level

    def delete(self, price_level: PriceLevelDB) -> None:
        self._db.delete(price_level)
        self._db.commit()

    def list_by_user_and_varieties(
        self, user_id: int, variety_ids: set[int]
    ) -> list[PriceLevelDB]:
        return (
            self._db.query(PriceLevelDB)
            .filter(
                PriceLevelDB.user_id == user_id,
                PriceLevelDB.variety_id.in_(variety_ids),
            )
            .all()
        )
