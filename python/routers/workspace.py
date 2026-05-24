from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import UserDB
from schemas import WorkspaceSummary
from services.domain.workspace_service import WorkspaceService

router = APIRouter(prefix="/api/workspace", tags=["工作区"])


@router.get("/me", response_model=WorkspaceSummary)
def get_workspace(
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user_dependency)
):
    return WorkspaceService(db).get_workspace_summary(current_user)
