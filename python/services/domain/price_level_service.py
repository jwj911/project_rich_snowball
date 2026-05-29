"""价位标注（Price Level）领域服务。"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import FutContractDB, PriceLevelDB, VarietyDB
from schemas import PriceLevelBatchCreate, PriceLevelCreate, PriceLevelUpdate
from services.domain.exceptions import ConflictError, ForbiddenError, NotFoundError
from services.domain.repositories.price_level_repository import PriceLevelRepository


class PriceLevelService:
    """价位标注业务逻辑封装。

    通过构造函数接收 Repository，支持在单元测试中注入 MockRepository
    以脱离真实数据库进行测试。
    """

    def __init__(self, db: Session, repository: PriceLevelRepository | None = None):
        self._db = db
        self._repo = repository or PriceLevelRepository(db)

    def list_price_levels(
        self,
        user_id: int,
        variety_id: int | None = None,
        type: str | None = None,
        scope: str | None = None,
        contract_id: int | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[PriceLevelDB]:
        return self._repo.list_by_user(user_id, variety_id, type, scope, contract_id, skip, limit)

    def _get_and_check_owner(self, user_id: int, price_level_id: int) -> PriceLevelDB:
        pl = self._repo.get_by_id(price_level_id)
        if not pl:
            raise NotFoundError("价位标注不存在")
        if pl.user_id != user_id:
            raise ForbiddenError("无权操作")
        return pl

    def _check_duplicate(
        self, user_id: int, variety_id: int, type: str, price,
        scope: str = "continuous", contract_id: int | None = None, exclude_id: int | None = None
    ) -> bool:
        return self._repo.check_duplicate(user_id, variety_id, type, price, scope, contract_id, exclude_id)

    def _verify_contract(self, contract_id: int | None) -> None:
        """校验 contract_id 指向的合约是否存在。"""
        if contract_id is not None:
            exists = self._db.query(FutContractDB.id).filter(FutContractDB.id == contract_id).first()
            if not exists:
                raise NotFoundError("关联合约不存在")

    def create_price_level(self, user_id: int, item: PriceLevelCreate) -> PriceLevelDB:
        variety = self._db.query(VarietyDB).filter(VarietyDB.id == item.variety_id).first()
        if not variety:
            raise NotFoundError("品种不存在")

        self._verify_contract(item.contract_id)

        if self._check_duplicate(
            user_id, item.variety_id, item.type, item.price,
            item.scope, item.contract_id
        ):
            raise ConflictError("该价位标注已存在")

        try:
            return self._repo.create(
                user_id=user_id,
                variety_id=item.variety_id,
                type=item.type,
                price=item.price,
                note=item.note,
                scope=item.scope,
                contract_id=item.contract_id,
            )
        except IntegrityError as err:
            self._db.rollback()
            raise ConflictError("该价位标注已存在") from err

    def update_price_level(
        self, user_id: int, price_level_id: int, item: PriceLevelUpdate
    ) -> PriceLevelDB:
        pl = self._get_and_check_owner(user_id, price_level_id)

        if item.price is not None:
            if self._check_duplicate(
                user_id, pl.variety_id, pl.type, item.price,
                pl.scope, pl.contract_id, exclude_id=price_level_id
            ):
                raise ConflictError("该价位标注已存在")
            pl.price = item.price
        if item.note is not None:
            pl.note = item.note

        try:
            return self._repo.update(pl)
        except IntegrityError as err:
            self._db.rollback()
            raise ConflictError("该价位标注已存在") from err

    def delete_price_level(self, user_id: int, price_level_id: int) -> None:
        pl = self._get_and_check_owner(user_id, price_level_id)
        self._repo.delete(pl)

    def create_price_levels_batch(
        self, user_id: int, body: PriceLevelBatchCreate
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
            for v in self._db.query(VarietyDB).filter(VarietyDB.id.in_(variety_ids)).all()
        }

        contract_ids = {item.contract_id for item in body.items if item.contract_id is not None}
        valid_contracts = set()
        if contract_ids:
            valid_contracts = {
                c.id for c in self._db.query(FutContractDB.id).filter(FutContractDB.id.in_(contract_ids)).all()
            }

        existing_keys = {
            (pl.variety_id, pl.type, float(pl.price), pl.scope, pl.contract_id)
            for pl in self._repo.list_by_user_and_varieties(user_id, variety_ids)
        }

        pending: list[PriceLevelDB] = []
        for idx, item in enumerate(body.items):
            if item.variety_id not in varieties:
                failed.append({"index": idx, "reason": "品种不存在"})
                continue

            # contract scope 必须指定 contract_id
            if item.scope == "contract" and item.contract_id is None:
                failed.append({"index": idx, "reason": "contract scope 必须指定 contract_id"})
                continue

            # continuous/main scope 的 contract_id 应规范化为 None
            if item.scope in ("continuous", "main") and item.contract_id is not None:
                item.contract_id = None

            if item.contract_id is not None and item.contract_id not in valid_contracts:
                failed.append({"index": idx, "reason": "关联合约不存在"})
                continue

            key = (item.variety_id, item.type, float(item.price), item.scope, item.contract_id)
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
                scope=item.scope,
                contract_id=item.contract_id,
                source="manual",
            )
            self._db.add(pl)
            pending.append(pl)

        try:
            self._db.commit()
            for pl in pending:
                self._db.refresh(pl)
                success.append(pl)
        except IntegrityError:
            self._db.rollback()
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
                    scope=item.scope,
                    contract_id=item.contract_id,
                    source="manual",
                )
                self._db.add(pl)
                try:
                    self._db.commit()
                    self._db.refresh(pl)
                    success.append(pl)
                except IntegrityError:
                    self._db.rollback()
                    if {"index": idx, "reason": "该价位标注已存在"} not in failed:
                        failed.append({"index": idx, "reason": "该价位标注已存在"})

        return success, failed
