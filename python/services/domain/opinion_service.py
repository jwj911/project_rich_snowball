"""交易观点领域服务。"""

from datetime import UTC, datetime

from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from models import OpinionDB, VarietyDB
from schemas import OpinionCreate, OpinionUpdate
from services.domain.exceptions import ForbiddenError, NotFoundError


class OpinionService:
    """交易观点业务逻辑层。

    将 router 中的 CRUD 逻辑下沉到 service，使 router 只负责 HTTP 契约转换。
    """

    def __init__(self, db: Session):
        self._db = db

    def _to_response(self, opinion: OpinionDB) -> dict:
        """将 ORM 对象转换为字典（供 router 包装为 Pydantic 响应）。"""
        variety = opinion.variety
        return {
            "id": opinion.id,
            "user_id": opinion.user_id,
            "variety_id": opinion.variety_id,
            "variety_symbol": variety.symbol if variety else "",
            "variety_name": variety.name if variety else "",
            "type": opinion.type,
            "reason": opinion.reason,
            "target_price": opinion.target_price,
            "stop_loss": opinion.stop_loss,
            "status": opinion.status,
            "actual_outcome": opinion.actual_outcome,
            "created_at": opinion.created_at,
            "closed_at": opinion.closed_at,
        }

    def list_opinions(
        self,
        variety_id: int | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        """查询交易观点列表（公开）。"""
        q = self._db.query(OpinionDB).options(joinedload(OpinionDB.variety))
        if variety_id:
            q = q.filter(OpinionDB.variety_id == variety_id)
        if status:
            q = q.filter(OpinionDB.status == status)
        opinions = q.order_by(desc(OpinionDB.created_at)).offset(skip).limit(limit).all()
        return [self._to_response(o) for o in opinions]

    def list_my_opinions(
        self,
        user_id: int,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        """查询当前用户的交易观点时间线。"""
        q = self._db.query(OpinionDB).options(joinedload(OpinionDB.variety)).filter(OpinionDB.user_id == user_id)
        if status:
            q = q.filter(OpinionDB.status == status)
        opinions = q.order_by(desc(OpinionDB.created_at)).offset(skip).limit(limit).all()
        return [self._to_response(o) for o in opinions]

    def get_opinion(self, opinion_id: int) -> dict:
        """获取单条观点详情。"""
        opinion = (
            self._db.query(OpinionDB).options(joinedload(OpinionDB.variety)).filter(OpinionDB.id == opinion_id).first()
        )
        if not opinion:
            raise NotFoundError("观点不存在")
        return self._to_response(opinion)

    def create_opinion(self, user_id: int, data: OpinionCreate) -> dict:
        """创建交易观点。"""
        variety = self._db.get(VarietyDB, data.variety_id)
        if not variety:
            raise NotFoundError("品种不存在")

        opinion = OpinionDB(
            user_id=user_id,
            variety_id=data.variety_id,
            type=data.type,
            reason=data.reason,
            target_price=data.target_price,
            stop_loss=data.stop_loss,
            status="open",
        )
        self._db.add(opinion)
        self._db.commit()
        self._db.refresh(opinion)
        opinion.variety = variety
        return self._to_response(opinion)

    def update_opinion(self, user_id: int, opinion_id: int, data: OpinionUpdate) -> dict:
        """更新交易观点（仅 owner）。"""
        opinion = self._db.get(OpinionDB, opinion_id)
        if not opinion:
            raise NotFoundError("观点不存在")
        if opinion.user_id != user_id:
            raise ForbiddenError("无权修改他人观点")

        if data.reason is not None:
            opinion.reason = data.reason
        if data.target_price is not None:
            opinion.target_price = data.target_price
        if data.stop_loss is not None:
            opinion.stop_loss = data.stop_loss
        if data.status is not None:
            opinion.status = data.status
            if data.status != "open" and opinion.closed_at is None:
                opinion.closed_at = datetime.now(UTC)
        if data.actual_outcome is not None:
            opinion.actual_outcome = data.actual_outcome

        self._db.commit()
        self._db.refresh(opinion)
        if opinion.variety is None:
            opinion.variety = self._db.get(VarietyDB, opinion.variety_id)
        return self._to_response(opinion)

    def delete_opinion(self, user_id: int, opinion_id: int) -> None:
        """删除交易观点（仅 owner）。"""
        opinion = self._db.get(OpinionDB, opinion_id)
        if not opinion:
            raise NotFoundError("观点不存在")
        if opinion.user_id != user_id:
            raise ForbiddenError("无权删除他人观点")
        self._db.delete(opinion)
        self._db.commit()
