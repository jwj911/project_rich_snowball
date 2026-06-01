import html
from datetime import datetime as dt
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field, field_validator


def sanitize_html_text(v: str | None) -> str | None:
    """统一 XSS 过滤：去除首尾空白，对非空文本做 HTML escape。"""
    if isinstance(v, str):
        v = v.strip()
        if v:
            v = html.escape(v)
    return v if v else None


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def _validate_password_strength(cls, v: str) -> str:
        if not any(c.isalpha() for c in v):
            raise ValueError("密码必须包含至少一个字母")
        if not any(c.isdigit() for c in v):
            raise ValueError("密码必须包含至少一个数字")
        return v


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: dt

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None
    expires_in: int = 1800  # access token 默认有效期（秒）

    model_config = ConfigDict(from_attributes=True)


class RefreshTokenRequest(BaseModel):
    refresh_token: str | None = Field(None, min_length=10)


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """通用消息响应，用于删除、退出等无需返回实体的操作。"""

    detail: str

    model_config = ConfigDict(from_attributes=True)


# ---------- 用户偏好设置 ----------


class Theme(StrEnum):
    dark = "dark"
    light = "light"
    system = "system"


class UserPreferenceResponse(BaseModel):
    """用户偏好设置响应。"""

    user_id: int
    theme: str
    polling_interval_seconds: int
    notifications_enabled: bool
    language: str
    created_at: dt | None = None
    updated_at: dt | None = None

    model_config = ConfigDict(from_attributes=True)


class UserPreferenceUpdate(BaseModel):
    """用户偏好设置更新请求（Patch 语义：仅更新提供的字段）。"""

    theme: Theme | None = Field(None, description="主题: dark | light | system")
    polling_interval_seconds: int | None = Field(None, ge=5, le=3600, description="行情轮询间隔（秒）")
    notifications_enabled: bool | None = Field(None, description="是否启用通知")
    language: str | None = Field(None, max_length=10, description="语言代码，如 zh-CN")


class CommentCreate(BaseModel):
    variety_id: int = Field(..., ge=1)
    content: str = Field(..., min_length=1, max_length=2000)
    price_level_id: int | None = Field(None, ge=1)

    @field_validator("content", mode="before")
    @classmethod
    def sanitize_content(cls, v: str | None) -> str:
        v = sanitize_html_text(v)
        if v is None or not v:
            raise ValueError("评论内容不能为空")
        return v


class CommentResponse(BaseModel):
    id: int
    variety_id: int
    product_symbol: str | None = None
    product_name: str | None = None
    variety_symbol: str | None = None
    variety_name: str | None = None
    user_id: int
    username: str
    content: str
    price_level_id: int | None = None
    created_at: dt

    model_config = ConfigDict(from_attributes=True)


class VarietyDetailResponse(BaseModel):
    """品种详情（含实时行情+评论列表），用于替代 ProductDetailResponse。"""

    id: int
    symbol: str
    contract_code: str
    name: str
    exchange: str
    category: str | None
    margin_rate: float | None
    commission: float | None
    tick_size: float | None = None
    current_price: float | None = None
    change_percent: float | None = None
    open_price: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int | None = None
    limit_up: float | None = None
    limit_down: float | None = None
    price_precision: int = 2
    comments: list[CommentResponse] = []

    model_config = ConfigDict(from_attributes=True)


class VarietyResponse(BaseModel):
    id: int
    symbol: str
    contract_code: str
    name: str
    exchange: str
    category: str | None
    margin_rate: float | None
    commission: float | None
    tick_size: float | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def price_precision(self) -> int:
        """根据 tick_size 推导价格精度（小数位数）。"""
        if not self.tick_size:
            return 2
        tick = self.tick_size
        s = f"{tick:.10f}".rstrip("0")
        if "." in s:
            return len(s.split(".")[1])
        return 0


class VarietyWithQuoteResponse(BaseModel):
    """品种列表项（含实时行情），用于替代 ProductResponse。"""

    id: int
    symbol: str
    name: str
    category: str | None
    current_price: float | None = None
    change_percent: float | None = None
    open_price: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int | None = None
    limit_up: float | None = None
    limit_down: float | None = None
    price_precision: int = 2
    margin_rate: float | None = None
    commission: float | None = None
    updated_at: str | None = None

    model_config = ConfigDict(from_attributes=True)

    model_config = ConfigDict(from_attributes=True)


class KlineResponse(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int

    model_config = ConfigDict(from_attributes=True)


class RealtimeResponse(BaseModel):
    symbol: str
    current_price: float
    change_percent: float
    open_price: float | None
    high: float | None
    low: float | None
    volume: int | None
    updated_at: dt
    delayed: bool = False
    data_source: str | None = None
    limit_up: float | None = None
    limit_down: float | None = None

    model_config = ConfigDict(from_attributes=True)


class RealtimeBatchResponse(BaseModel):
    quotes: list[RealtimeResponse]
    not_found: list[str]

    model_config = ConfigDict(from_attributes=True)


# ========== Price Level / Workspace schemas ==========


class PriceLevelType(StrEnum):
    SUPPORT = "support"
    RESISTANCE = "resistance"


class PriceLevelScope(StrEnum):
    CONTINUOUS = "continuous"
    MAIN = "main"
    CONTRACT = "contract"


class PriceLevelCreate(BaseModel):
    variety_id: int = Field(..., ge=1)
    type: str = Field(..., pattern=r"^(support|resistance)$")
    price: Decimal = Field(..., ge=0, decimal_places=4)
    scope: str = Field(default="continuous", pattern=r"^(continuous|main|contract)$")
    contract_id: int | None = Field(None, ge=1)
    note: str | None = Field(None, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def sanitize_note(cls, v: str | None) -> str | None:
        return sanitize_html_text(v)


class PriceLevelUpdate(BaseModel):
    price: Decimal | None = Field(None, ge=0, decimal_places=4)
    note: str | None = Field(None, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def sanitize_note(cls, v: str | None) -> str | None:
        return sanitize_html_text(v)


class PriceLevelResponse(BaseModel):
    id: int
    user_id: int
    variety_id: int
    contract_id: int | None = None
    variety_symbol: str | None = None
    variety_name: str | None = None
    type: str
    price: Decimal
    scope: str
    note: str | None
    source: str
    created_at: dt
    updated_at: dt

    model_config = ConfigDict(from_attributes=True)


class WatchlistCreate(BaseModel):
    variety_id: int = Field(..., ge=1)
    notes: str | None = Field(None, max_length=500)

    @field_validator("notes", mode="before")
    @classmethod
    def sanitize_notes(cls, v: str | None) -> str | None:
        return sanitize_html_text(v)


class WatchlistUpdate(BaseModel):
    notes: str | None = Field(None, max_length=500)
    is_notified: bool | None = None

    @field_validator("notes", mode="before")
    @classmethod
    def sanitize_notes(cls, v: str | None) -> str | None:
        return sanitize_html_text(v)


class WatchlistResponse(BaseModel):
    id: int
    user_id: int
    variety_id: int
    variety_symbol: str
    variety_name: str
    notes: str | None
    is_notified: bool
    created_at: dt

    model_config = ConfigDict(from_attributes=True)


class WorkspaceSummary(BaseModel):
    price_levels: list[PriceLevelResponse]
    watchlists: list[WatchlistResponse]
    recent_comments: list[CommentResponse]


# ========== Contract / Rollover schemas ==========

class ContractResponse(BaseModel):
    id: int
    ts_code: str
    symbol: str | None
    name: str | None
    fut_code: str | None
    exchange: str | None
    list_date: dt | None
    delist_date: dt | None
    contract_type: str | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ContractRolloverResponse(BaseModel):
    id: int
    variety_id: int
    old_contract_id: int | None
    new_contract_id: int | None
    old_contract_code: str | None
    new_contract_code: str | None
    effective_date: dt
    source: str
    created_at: dt

    model_config = ConfigDict(from_attributes=True)


class ContinuousKlineResponse(KlineResponse):
    contract_code: str | None
    contract_id: int | None


# ========== Batch Price Levels ==========

class PriceLevelBatchItem(BaseModel):
    """批量导入价位标注的单项模型。

    与 PriceLevelCreate 语义一致，但作为 batch 接口的独立类型定义，
    保证单条创建与批量创建在 scope/contract_id 上完全一致。
    """

    variety_id: int = Field(..., ge=1)
    type: str = Field(..., pattern=r"^(support|resistance)$")
    price: Decimal = Field(..., ge=0, decimal_places=4)
    scope: str = Field(default="continuous", pattern=r"^(continuous|main|contract)$")
    contract_id: int | None = Field(None, ge=1)
    note: str | None = Field(None, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def sanitize_note(cls, v: str | None) -> str | None:
        return sanitize_html_text(v)


class PriceLevelBatchCreate(BaseModel):
    items: list[PriceLevelBatchItem] = Field(..., max_length=500)


class PriceLevelBatchResponse(BaseModel):
    success: list[PriceLevelResponse]
    failed: list[dict]
    created_count: int
    failed_count: int


# ========== Variety Fee ==========

class VarietyFeeResponse(BaseModel):
    symbol: str
    name: str | None
    exchange: str | None
    margin_rate: float | None
    margin_amount: float | None
    commission_open: float | None
    commission_close: float | None
    commission_close_today: float | None
    unit: str | None
    updated_at: dt | None

    model_config = ConfigDict(from_attributes=True)


# ========== Trading Calendar / Market Status ==========

class TradingCalendarEntry(BaseModel):
    trade_date: dt
    is_trading_day: bool
    day_session_start: str
    day_session_end: str
    night_session_start: str | None
    night_session_end: str | None
    exchange: str
    remark: str | None

    model_config = ConfigDict(from_attributes=True)


class MarketStatusResponse(BaseModel):
    date: str
    is_trading_day: bool
    current_session: str
    next_trade_date: str | None
    remark: str | None

    model_config = ConfigDict(from_attributes=True)


# ========== Frontend Logs ==========

class FrontendLogCreate(BaseModel):
    type: str = Field(..., max_length=20)
    payload: dict = Field(default_factory=dict)
    level: str | None = Field(default=None, max_length=20)
    meta: dict = Field(default_factory=dict)
    user_id: int | None = Field(default=None, ge=1, description="已登录用户上报时关联用户 ID")

    @field_validator("type", "level", mode="before")
    @classmethod
    def _strip_strings(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v


class FrontendLogResponse(BaseModel):
    """前端日志查询响应。"""

    id: int
    user_id: int | None
    type: str
    level: str | None
    url: str | None
    user_agent: str | None
    release: str | None
    environment: str | None
    payload: dict
    created_at: dt

    model_config = ConfigDict(from_attributes=True)

    @field_validator("payload", mode="before")
    @classmethod
    def _parse_payload_json(cls, v):
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return {}
        return v


class NewsSourceBase(BaseModel):
    """新闻源基础字段。"""

    name: str = Field(..., max_length=100)
    url: str = Field(..., max_length=500)
    category: str | None = Field(default=None, max_length=50)
    is_enabled: bool = Field(default=True)


class NewsSourceCreate(NewsSourceBase):
    """创建新闻源请求。"""
    pass


class NewsSourceResponse(NewsSourceBase):
    """新闻源响应。"""

    id: int
    last_fetched_at: dt | None
    fetch_error_count: int
    created_at: dt

    model_config = ConfigDict(from_attributes=True)


class NewsArticleResponse(BaseModel):
    """新闻条目响应。"""

    id: int
    source_id: int
    title: str
    summary: str | None
    url: str
    published_at: dt | None
    fetched_at: dt

    model_config = ConfigDict(from_attributes=True)


class OpinionCreate(BaseModel):
    """创建交易观点请求。"""

    variety_id: int = Field(..., ge=1)
    type: str = Field(..., max_length=10)  # long | short | neutral
    reason: str = Field(..., max_length=2000)
    target_price: Decimal | None = Field(default=None, ge=0, decimal_places=4)
    stop_loss: Decimal | None = Field(default=None, ge=0, decimal_places=4)

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, v):
        if isinstance(v, str):
            v = v.strip().lower()
            if v not in ("long", "short", "neutral"):
                raise ValueError("type must be one of: long, short, neutral")
            return v
        return v


class OpinionUpdate(BaseModel):
    """更新交易观点请求（Patch 语义）。"""

    reason: str | None = Field(default=None, max_length=2000)
    target_price: Decimal | None = Field(default=None, ge=0, decimal_places=4)
    stop_loss: Decimal | None = Field(default=None, ge=0, decimal_places=4)
    status: str | None = Field(default=None, max_length=20)
    actual_outcome: str | None = Field(default=None, max_length=20)

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, v):
        if isinstance(v, str):
            v = v.strip().lower()
            if v not in ("open", "closed_profit", "closed_loss", "expired"):
                raise ValueError("status must be one of: open, closed_profit, closed_loss, expired")
            return v
        return v

    @field_validator("actual_outcome", mode="before")
    @classmethod
    def _normalize_outcome(cls, v):
        if isinstance(v, str):
            v = v.strip().lower()
            if v not in ("profit", "loss", "breakeven"):
                raise ValueError("actual_outcome must be one of: profit, loss, breakeven")
            return v
        return v


class OpinionResponse(BaseModel):
    """交易观点响应。"""

    id: int
    user_id: int
    variety_id: int
    variety_symbol: str
    variety_name: str
    type: str
    reason: str | None
    target_price: Decimal | None
    stop_loss: Decimal | None
    status: str
    actual_outcome: str | None
    created_at: dt
    closed_at: dt | None

    model_config = ConfigDict(from_attributes=True)
