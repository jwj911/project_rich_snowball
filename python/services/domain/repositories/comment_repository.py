"""Comment 数据访问层。"""

from sqlalchemy.orm import Session, joinedload

from models import CommentDB, PriceLevelDB, UserDB, VarietyDB


class CommentRepository:
    """Comment 相关的数据库操作，供 CommentService 使用。

    通过抽取 Repository，CommentService 可在单元测试中注入 MockRepository，
    无需依赖真实数据库会话。
    """

    def __init__(self, db: Session):
        self._db = db

    def get_variety(self, variety_id: int) -> VarietyDB | None:
        return self._db.query(VarietyDB).filter(VarietyDB.id == variety_id).first()

    def get_price_level(self, price_level_id: int, user_id: int) -> PriceLevelDB | None:
        return (
            self._db.query(PriceLevelDB)
            .filter(
                PriceLevelDB.id == price_level_id,
                PriceLevelDB.user_id == user_id,
            )
            .first()
        )

    def create(
        self,
        variety_id: int,
        product_id: int | None,
        user_id: int,
        price_level_id: int | None,
        content: str,
    ) -> CommentDB:
        db_comment = CommentDB(
            variety_id=variety_id,
            product_id=product_id,
            user_id=user_id,
            price_level_id=price_level_id,
            content=content,
        )
        self._db.add(db_comment)
        self._db.commit()
        self._db.refresh(db_comment)
        return db_comment

    def list_by_user(self, user_id: int, skip: int, limit: int) -> list[CommentDB]:
        return (
            self._db.query(CommentDB)
            .options(joinedload(CommentDB.variety))
            .filter(CommentDB.user_id == user_id)
            .order_by(CommentDB.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_user(self, username: str) -> UserDB | None:
        return self._db.query(UserDB).filter(UserDB.username == username).first()
