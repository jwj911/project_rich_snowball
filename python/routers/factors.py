"""因子管理路由。

提供因子 CRUD 接口，支持系统内置因子（万因子等）和用户自定义因子。
系统因子不可删除、不可修改；用户因子支持完整的创建/更新/删除/软删除流程。
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from errors import ErrorCode
from models import FactorDefinitionDB, UserDB
from schemas import FactorCreate, FactorResponse, FactorUpdate
from services.agent.factor_engine.dsl import validate_factor_formula
from services.domain.exceptions import ForbiddenError, NotFoundError, ServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/factors", tags=["因子"])


def _is_admin(user: UserDB) -> bool:
    """判断用户是否为管理员。"""
    return user.role == "admin"


def _generate_factor_id(name: str) -> str:
    """将名称转为 snake_case 并附加时间戳哈希，生成唯一 factor_id。

    Args:
        name: 用户输入的因子名称。

    Returns:
        形如 ``close_ma_5_a3f7b2d1`` 的唯一因子标识符。
    """
    base = re.sub(r"[^\w]+", "_", name.strip()).lower().strip("_")
    if not base:
        base = "factor"
    ts_hash = hashlib.md5(f"{name}_{time.time()}".encode()).hexdigest()[:8]
    return f"{base}_{ts_hash}"


def _check_factor_mutable(factor: FactorDefinitionDB, user: UserDB) -> None:
    """校验因子是否允许被当前用户修改/删除。

    系统内置因子（is_builtin=True）对任何用户都不可变更；
    用户自建因子仅 owner 或管理员可操作。

    Args:
        factor: 目标因子数据库对象。
        user: 当前登录用户。

    Raises:
        ForbiddenError: 因子为系统内置，或当前用户非 owner/管理员。
    """
    if factor.is_builtin:
        raise ForbiddenError("系统内置因子不可修改或删除")
    if factor.user_id != user.id and not _is_admin(user):
        raise ForbiddenError("无权操作该因子")


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------


@router.get("", response_model=list[FactorResponse])
def list_factors(
    db: Session = Depends(get_db),  # noqa: B008
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    skip: int = Query(0, ge=0, description="分页偏移"),
    limit: int = Query(20, ge=1, le=100, description="分页大小"),
    q: str | None = Query(None, max_length=100, description="名称/因子ID模糊搜索"),
    category: str | None = Query(None, max_length=50, description="按分类精确匹配"),
    source: str | None = Query(None, max_length=50, description="按来源精确匹配"),
    is_builtin: bool | None = Query(None, description="按是否系统内置筛选"),
) -> list[FactorDefinitionDB]:
    """获取因子列表。

    默认返回全部活跃因子（包括系统内置和用户自建），按 ``q_score`` 降序排列。
    支持通过 ``q`` 对 ``name`` 和 ``factor_id`` 进行模糊搜索。
    """
    query = db.query(FactorDefinitionDB).filter(FactorDefinitionDB.is_active.is_(True))
    if not _is_admin(current_user):
        query = query.filter(
            or_(
                FactorDefinitionDB.is_builtin.is_(True),
                FactorDefinitionDB.user_id == current_user.id,
            )
        )

    if q:
        like_pat = f"%{q}%"
        query = query.filter(
            or_(
                FactorDefinitionDB.name.ilike(like_pat),
                FactorDefinitionDB.factor_id.ilike(like_pat),
            )
        )
    if category:
        query = query.filter(FactorDefinitionDB.category == category)
    if source:
        query = query.filter(FactorDefinitionDB.source == source)
    if is_builtin is not None:
        query = query.filter(FactorDefinitionDB.is_builtin.is_(is_builtin))

    rows = (
        query.order_by(FactorDefinitionDB.q_score.desc().nullslast())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return rows


@router.post("", response_model=FactorResponse, status_code=status.HTTP_201_CREATED)
def create_factor(
    data: FactorCreate,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
) -> FactorDefinitionDB:
    """创建自定义因子。

    通过 ``dsl.validate_factor_formula()`` 对 ``source_expression`` 进行安全校验，
    校验失败返回 400 + ``VALIDATION_ERROR``。
    自动设置 ``user_id``、``is_builtin=False``、``package_id`` 和 ``conversion_status``。
    """
    try:
        validate_factor_formula(data.source_expression)
    except ValueError as exc:
        raise ServiceError(
            f"因子公式校验失败：{exc}", code=ErrorCode.VALIDATION_ERROR
        ) from exc

    factor = FactorDefinitionDB(
        user_id=current_user.id,
        is_builtin=False,
        package_id=f"user_{current_user.id}",
        factor_id=_generate_factor_id(data.name),
        name=data.name,
        source="user",
        category=data.category,
        source_expression=data.source_expression,
        fields_json=data.fields_json,
        metadata_json=data.metadata_json,
        conversion_status="pending",
        is_active=True,
    )
    db.add(factor)
    db.commit()
    db.refresh(factor)
    return factor


@router.get("/{factor_id}", response_model=FactorResponse)
def get_factor(
    factor_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
) -> FactorDefinitionDB:
    """获取因子详情。

    路径参数 ``factor_id`` 对应数据库自增主键 ``id``。
    若因子不存在或已被软删除，返回 404。
    """
    row = (
        db.query(FactorDefinitionDB)
        .filter(FactorDefinitionDB.id == factor_id, FactorDefinitionDB.is_active.is_(True))
        .first()
    )
    if not row:
        raise NotFoundError("因子不存在或已删除", code=ErrorCode.NOT_FOUND)
    if not row.is_builtin and row.user_id != current_user.id and not _is_admin(current_user):
        raise ForbiddenError("无权访问该因子")
    return row


@router.patch("/{factor_id}", response_model=FactorResponse)
def update_factor(
    factor_id: int,
    data: FactorUpdate,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
) -> FactorDefinitionDB:
    """更新因子（Patch 语义）。

    仅因子 owner 或管理员可修改；系统内置因子不可修改。
    若更新 ``source_expression``，会重新进行公式合法性校验。
    """
    row = db.query(FactorDefinitionDB).filter(FactorDefinitionDB.id == factor_id).first()
    if not row:
        raise NotFoundError("因子不存在", code=ErrorCode.NOT_FOUND)

    _check_factor_mutable(row, current_user)

    update_data: dict[str, Any] = data.model_dump(exclude_unset=True)

    if "source_expression" in update_data:
        try:
            validate_factor_formula(update_data["source_expression"])
        except ValueError as exc:
            raise ServiceError(
                f"因子公式校验失败：{exc}", code=ErrorCode.VALIDATION_ERROR
            ) from exc

    for key, value in update_data.items():
        setattr(row, key, value)

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{factor_id}")
def delete_factor(
    factor_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
) -> dict[str, str]:
    """软删除因子。

    仅因子 owner 或管理员可删除；系统内置因子不可删除。
    实际执行 ``is_active = False`` 而非物理删除。
    """
    row = db.query(FactorDefinitionDB).filter(FactorDefinitionDB.id == factor_id).first()
    if not row:
        raise NotFoundError("因子不存在", code=ErrorCode.NOT_FOUND)

    _check_factor_mutable(row, current_user)

    row.is_active = False
    db.commit()
    return {"message": "因子已删除"}
