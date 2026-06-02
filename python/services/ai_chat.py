"""AI 聊天服务。

基于 OpenAI 兼容 API 提供期货领域问答助手。
支持从数据库检索实时行情、品种信息、用户观点作为上下文。
"""

import json
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from config import CHAT_MAX_HISTORY, OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
from models import ChatMessageDB, OpinionDB, RealtimeQuoteDB, VarietyDB

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是「期货交流社区」的 AI 助手，专注于期货行情分析、交易观点解读和投资知识问答。\n"
    "回答时请遵循以下规则：\n"
    "1. 所有分析仅供参考，不构成投资建议。\n"
    "2. 使用中文回答，术语准确，表达简洁专业。\n"
    "3. 涉及价格时使用品种对应的价格精度。\n"
    "4. 如果用户询问具体品种，优先使用提供的实时行情数据。\n"
    "5. 如果涉及用户观点，客观转述，不添加主观评价。\n"
)


def _extract_symbols(text: str, db: Session) -> list[VarietyDB]:
    """从用户消息中提取可能的品种代码，返回匹配的品种列表。"""
    varieties = db.query(VarietyDB).filter(VarietyDB.is_active == True).all()  # noqa: E712
    found = []
    text_upper = text.upper()
    for v in varieties:
        if v.symbol in text_upper or v.name in text:
            found.append(v)
        if len(found) >= 3:
            break
    return found


def _build_context(varieties: list[VarietyDB], db: Session, user_id: int) -> dict:
    """构建上下文数据：实时行情 + 用户观点。"""
    context: dict = {"varieties": [], "opinions": []}
    variety_ids = [v.id for v in varieties]

    if variety_ids:
        quotes = {
            q.variety_id: q
            for q in db.query(RealtimeQuoteDB).filter(RealtimeQuoteDB.variety_id.in_(variety_ids)).all()
        }
        for v in varieties:
            q = quotes.get(v.id)
            context["varieties"].append({
                "symbol": v.symbol,
                "name": v.name,
                "exchange": v.exchange,
                "category": v.category,
                "current_price": str(q.current_price) if q else None,
                "change_percent": str(q.change_percent) if q else None,
                "high": str(q.high) if q else None,
                "low": str(q.low) if q else None,
                "volume": q.volume if q else None,
            })

        recent_opinions = (
            db.query(OpinionDB)
            .filter(
                OpinionDB.variety_id.in_(variety_ids),
                OpinionDB.status == "open",
            )
            .order_by(OpinionDB.created_at.desc())
            .limit(5)
            .all()
        )
        for o in recent_opinions:
            context["opinions"].append({
                "type": o.type,
                "reason": o.reason,
                "target_price": str(o.target_price) if o.target_price else None,
                "stop_loss": str(o.stop_loss) if o.stop_loss else None,
            })

    return context


def _format_context(context: dict) -> str:
    """将上下文格式化为 prompt 文本。"""
    lines = []
    if context.get("varieties"):
        lines.append("【实时行情数据】")
        for v in context["varieties"]:
            price_info = f"最新价 {v['current_price']}" if v["current_price"] else "暂无行情"
            change = f", 涨跌幅 {v['change_percent']}%" if v["change_percent"] else ""
            lines.append(f"- {v['symbol']} ({v['name']}, {v['exchange']}): {price_info}{change}")
    if context.get("opinions"):
        lines.append("\n【相关交易观点】")
        for o in context["opinions"]:
            lines.append(f"- {o['type']}: {o['reason']}")
            if o["target_price"]:
                lines.append(f"  目标价 {o['target_price']}, 止损 {o['stop_loss']}")
    return "\n".join(lines) if lines else ""


def _build_messages(user_content: str, context: dict, history: list[ChatMessageDB]) -> list[dict]:
    """构造发送给 LLM 的 messages 列表。"""
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]

    ctx_text = _format_context(context)
    if ctx_text:
        messages.append({"role": "system", "content": f"以下是从数据库检索到的上下文信息（仅供参考）：\n{ctx_text}"})

    # 截取最近历史
    for h in history[-CHAT_MAX_HISTORY:]:
        messages.append({"role": h.role, "content": h.content})

    messages.append({"role": "user", "content": user_content})
    return messages


async def chat_with_ai(user_id: int, user_content: str, db: Session) -> tuple[str, dict]:
    """调用 AI 模型获取回复。

    Returns:
        (assistant_content, context_dict)
    """
    if not OPENAI_API_KEY:
        return (
            "AI 助手尚未配置。请管理员设置 OPENAI_API_KEY 环境变量以启用此功能。",
            {},
        )

    varieties = _extract_symbols(user_content, db)
    context = _build_context(varieties, db, user_id)

    history = (
        db.query(ChatMessageDB)
        .filter(ChatMessageDB.user_id == user_id)
        .order_by(ChatMessageDB.created_at)
        .all()
    )

    messages = _build_messages(user_content, context, history)

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENAI_MODEL,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 2048,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return content.strip(), context
    except httpx.HTTPStatusError as e:
        logger.error("AI API error: %s %s", e.response.status_code, e.response.text)
        return "AI 服务暂时不可用，请稍后重试。", context
    except Exception as e:
        logger.error("AI chat error: %s", e)
        return "请求 AI 服务时发生错误，请检查配置或稍后重试。", context
