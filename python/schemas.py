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
    password: str = Field(..., min_length=6, max_length=128)


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


class PriceLevelCreate(BaseModel):
    variety_id: int = Field(..., ge=1)
    type: str = Field(..., pattern=r"^(support|resistance)$")
    price: Decimal = Field(..., ge=0, decimal_places=4)
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
    variety_symbol: str | None = None
    variety_name: str | None = None
    type: str
    price: Decimal
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

class PriceLevelBatchCreate(BaseModel):
    items: list[PriceLevelCreate] = Field(..., max_length=500)


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

    @field_validator("type", "level", mode="before")
    @classmethod
    def _strip_strings(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v
