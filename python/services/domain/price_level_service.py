"""价位标注（Price Level）领域服务。"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import PriceLevelDB, VarietyDB
from schemas import PriceLevelBatchCreate, PriceLevelCreate, PriceLevelUpdate
from services.domain.exceptions import ConflictError, ForbiddenError, NotFoundError


class PriceLevelService:
    """价位标注业务逻辑封装。"""

    @staticmethod
    def list_price_levels(
        db: Session, user_id: int, variety_id: int | None = None, type: str | None = None,
        skip: int = 0, limit: int = 100,
    ) -> list[PriceLevelDB]:
        query = db.query(PriceLevelDB).filter(PriceLevelDB.user_id == user_id)
        if variety_id:
            query = query.filter(PriceLevelDB.variety_id == variety_id)
        if type:
            query = query.filter(PriceLevelDB.type == type)
        return query.order_by(PriceLevelDB.created_at.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def _get_and_check_owner(db: Session, user_id: int, price_level_id: int) -> PriceLevelDB:
        pl = db.query(PriceLevelDB).filter(PriceLevelDB.id == price_level_id).first()
        if not pl:
            raise NotFoundError("价位标注不存在")
        if pl.user_id != user_id:
            raise ForbiddenError("无权操作")
        return pl

    @staticmethod
    def _check_duplicate(
        db: Session, user_id: int, variety_id: int, type: str, price, exclude_id: int | None = None
    ) -> bool:
        query = db.query(PriceLevelDB).filter(
            PriceLevelDB.user_id == user_id,
            PriceLevelDB.variety_id == variety_id,
            PriceLevelDB.type == type,
            PriceLevelDB.price == price,
        )
        if exclude_id is not None:
            query = query.filter(PriceLevelDB.id != exclude_id)
        return query.first() is not None

    @staticmethod
    def create_price_level(db: Session, user_id: int, item: PriceLevelCreate) -> PriceLevelDB:
        variety = db.query(VarietyDB).filter(VarietyDB.id == item.variety_id).first()
        if not variety:
            raise NotFoundError("品种不存在")

        pl = PriceLevelDB(
            user_id=user_id,
            variety_id=item.variety_id,
            type=item.type,
            price=item.price,
            note=item.note,
            source="manual",
        )
        db.add(pl)
        try:
            db.commit()
            db.refresh(pl)
        except IntegrityError:
            db.rollback()
            raise ConflictError("该价位标注已存在")
        return pl

    @staticmethod
    def update_price_level(
        db: Session, user_id: int, price_level_id: int, item: PriceLevelUpdate
    ) -> PriceLevelDB:
        pl = PriceLevelService._get_and_check_owner(db, user_id, price_level_id)

        if item.price is not None:
            if PriceLevelService._check_duplicate(
                db, user_id, pl.variety_id, pl.type, item.price, exclude_id=price_level_id
            ):
                raise ConflictError("该价位标注已存在")
            pl.price = item.price
        if item.note is not None:
            pl.note = item.note

        try:
            db.commit()
            db.refresh(pl)
        except IntegrityError:
            db.rollback()
            raise ConflictError("该价位标注已存在")
        return pl

    @staticmethod
    def delete_price_level(db: Session, user_id: int, price_level_id: int) -> None:
        pl = PriceLevelService._get_and_check_owner(db, user_id, price_level_id)
        db.delete(pl)
        db.commit()

    @staticmethod
    def create_price_levels_batch(
        db: Session, user_id: int, body: PriceLevelBatchCreate
    ) -> tuple[list[PriceLevelDB], list[dict]]:
        """批量导入价位标注。

        返回 (success_orm_list, failed_reason_list)。
        批量冲突时 fallback 到逐条处理，精确定位失败项。
        """
        success: list[PriceLevelDB] = []
        failed: list[dict] = []

        variety_ids = {item.variety_id for item in body.items}
        varieties = {
            v.id: v
            for v in db.query(VarietyDB).filter(VarietyDB.id.in_(variety_ids)).all()
        }
        existing_keys = {
            (pl.variety_id, pl.type, float(pl.price))
            for pl in db.query(PriceLevelDB).filter(
                PriceLevelDB.user_id == user_id,
                PriceLevelDB.variety_id.in_(variety_ids),
            ).all()
        }

        pending: list[PriceLevelDB] = []
        for idx, item in enumerate(body.items):
            if item.variety_id not in varieties:
                failed.append({"index": idx, "reason": "品种不存在"})
                continue

            key = (item.variety_id, item.type, float(item.price))
            if key in existing_keys:
                failed.append({"index": idx, "reason": "该价位标注已存在"})
                continue
            existing_keys.add(key)

            pl = PriceLevelDB(
                user_id=user_id,
                variety_id=item.variety_id,
                type=item.type,
                price=item.price,
                note=item.note,
                source="manual",
            )
            db.add(pl)
            pending.append(pl)

        try:
            db.commit()
            for pl in pending:
                db.refresh(pl)
                success.append(pl)
        except IntegrityError:
            db.rollback()
            success = []
            for idx, item in enumerate(body.items):
                if item.variety_id not in varieties:
                    continue
                pl = PriceLevelDB(
                    user_id=user_id,
                    variety_id=item.variety_id,
                    type=item.type,
                    price=item.price,
                    note=item.note,
                    source="manual",
                )
                db.add(pl)
                try:
                    db.commit()
                    db.refresh(pl)
                    success.append(pl)
                except IntegrityError:
                    db.rollback()
                    if {"index": idx, "reason": "该价位标注已存在"} not in failed:
                        failed.append({"index": idx, "reason": "该价位标注已存在"})

        return success, failed
