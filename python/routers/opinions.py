"""交易观点/日记端点。

用户可针对品种发表多空观点，记录目标价、止损价和理由，
支持事后复盘标记状态（open/closed_profit/closed_loss/expired）。

Router 仅负责 HTTP 契约转换，业务逻辑已下沉至 OpinionService。
"""

from fastapi import APIRouter, Depends, Query  # noqa: F401
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import UserDB
from schemas import OpinionCreate, OpinionResponse, OpinionUpdate
from services.domain.exceptions import ForbiddenError, NotFoundError
from services.domain.opinion_service import OpinionService

router = APIRouter(prefix="/api/opinions", tags=["交易观点"])


def _get_service(db: Session = Depends(get_db)) -> OpinionService:
    """依赖注入：创建 OpinionService 实例。"""
    return OpinionService(db)


@router.get("", response_model=list[OpinionResponse])
def list_opinions(
    variety_id: int | None = Query(None, description="按品种筛选"),
    status: str | None = Query(None, max_length=20, description="按状态筛选"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    service: OpinionService = Depends(_get_service),
):
    """查询交易观点列表（登录用户可见全部用户的公开观点）。"""
    return service.list_opinions(variety_id=variety_id, status=status, skip=skip, limit=limit)


@router.get("/me", response_model=list[OpinionResponse])
def list_my_opinions(
    status: str | None = Query(None, max_length=20, description="按状态筛选"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    service: OpinionService = Depends(_get_service),
):
    """查询当前用户的交易观点时间线。"""
    return service.list_my_opinions(
        user_id=current_user.id, status=status, skip=skip, limit=limit
    )


@router.get("/{opinion_id}", response_model=OpinionResponse)
def get_opinion(
    opinion_id: int,
    service: OpinionService = Depends(_get_service),
):
    """获取单条观点详情。"""
    return service.get_opinion(opinion_id)


@router.post("", response_model=OpinionResponse, status_code=201)
def create_opinion(
    data: OpinionCreate,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    service: OpinionService = Depends(_get_service),
):
    """创建交易观点。"""
    return service.create_opinion(user_id=current_user.id, data=data)


@router.put("/{opinion_id}", response_model=OpinionResponse)
def update_opinion(
    opinion_id: int,
    data: OpinionUpdate,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    service: OpinionService = Depends(_get_service),
):
    """更新交易观点（仅 owner）。支持关闭观点和标记复盘结果。"""
    return service.update_opinion(user_id=current_user.id, opinion_id=opinion_id, data=data)


@router.delete("/{opinion_id}", status_code=204)
def delete_opinion(
    opinion_id: int,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    service: OpinionService = Depends(_get_service),
):
    """删除交易观点（仅 owner）。"""
    service.delete_opinion(user_id=current_user.id, opinion_id=opinion_id)
    return None
