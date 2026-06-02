"""AI 聊天端点。

用户与大模型助手的对话接口，支持上下文检索和对话历史。
"""

from fastapi import APIRouter, Depends, HTTPException, Query  # noqa: F401
from sqlalchemy import desc
from sqlalchemy.orm import Session

from dependencies import get_current_user_dependency, get_db
from models import ChatMessageDB, UserDB
from schemas import ChatMessageCreate, ChatMessageResponse
from services.ai_chat import chat_with_ai

router = APIRouter(prefix="/api/chat", tags=["AI 聊天"])


@router.get("", response_model=list[ChatMessageResponse])
def list_chat_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """查询当前用户的 AI 对话历史。"""
    messages = (
        db.query(ChatMessageDB)
        .filter(ChatMessageDB.user_id == current_user.id)
        .order_by(ChatMessageDB.created_at)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        ChatMessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.post("", response_model=ChatMessageResponse)
async def send_chat_message(
    data: ChatMessageCreate,
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """发送消息给 AI 助手，返回助手回复。"""
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="content_required")

    # 保存用户消息
    user_msg = ChatMessageDB(
        user_id=current_user.id,
        role="user",
        content=data.content.strip(),
    )
    db.add(user_msg)
    db.commit()

    # 调用 AI
    assistant_content, context = await chat_with_ai(current_user.id, data.content.strip(), db)

    # 保存助手回复
    assistant_msg = ChatMessageDB(
        user_id=current_user.id,
        role="assistant",
        content=assistant_content,
        context_json=str(context) if context else None,
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    return ChatMessageResponse(
        id=assistant_msg.id,
        role=assistant_msg.role,
        content=assistant_msg.content,
        created_at=assistant_msg.created_at,
    )


@router.delete("", status_code=204)
def clear_chat_history(
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """清空当前用户的对话历史。"""
    db.query(ChatMessageDB).filter(ChatMessageDB.user_id == current_user.id).delete()
    db.commit()
    return None
