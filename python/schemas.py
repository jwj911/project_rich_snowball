from pydantic import BaseModel, Field, field_validator, EmailStr, ConfigDict
from typing import List, Optional
from datetime import datetime as dt
from decimal import Decimal
import html
import re


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    created_at: dt


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProductResponse(BaseModel):
    id: int
    name: str
    symbol: str
    current_price: float
    change_percent: float
    open_price: Optional[float]
    high: Optional[float]
    low: Optional[float]
    volume: Optional[float]
    category: Optional[str]
    margin: Optional[float]
    commission: Optional[float]
    updated_at: dt


class CommentCreate(BaseModel):
    product_id: int = Field(..., ge=1)
    content: str = Field(..., min_length=1, max_length=2000)
    price_level_id: Optional[int] = Field(None, ge=1)

    @field_validator("content", mode="before")
    @classmethod
    def sanitize_content(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        v = html.escape(v)
        if not v:
            raise ValueError("评论内容不能为空")
        return v


class CommentResponse(BaseModel):
    id: int
    product_id: int
    user_id: int
    username: str
    content: str
    price_level_id: Optional[int] = None
    created_at: dt


class ProductDetailResponse(BaseModel):
    product: ProductResponse
    comments: List[CommentResponse]


class VarietyResponse(BaseModel):
    id: int
    symbol: str
    contract_code: str
    name: str
    exchange: str
    category: Optional[str]
    margin_rate: Optional[float]
    commission: Optional[float]


class KlineResponse(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class RealtimeResponse(BaseModel):
    symbol: str
    current_price: float
    change_percent: float
    open_price: Optional[float]
    high: Optional[float]
    low: Optional[float]
    volume: Optional[int]
    updated_at: dt


class RealtimeBatchResponse(BaseModel):
    quotes: list[RealtimeResponse]
    not_found: list[str]


# ========== Price Level / Workspace schemas ==========

class PriceLevelType:
    SUPPORT = "support"
    RESISTANCE = "resistance"


class PriceLevelCreate(BaseModel):
    variety_id: int = Field(..., ge=1)
    type: str = Field(..., pattern=r"^(support|resistance)$")
    price: Decimal = Field(..., ge=0, decimal_places=4)
    note: Optional[str] = Field(None, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def sanitize_note(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            v = v.strip()
            if v:
                v = html.escape(v)
        return v if v else None


class PriceLevelUpdate(BaseModel):
    price: Optional[Decimal] = Field(None, ge=0, decimal_places=4)
    note: Optional[str] = Field(None, max_length=500)

    @field_validator("note", mode="before")
    @classmethod
    def sanitize_note(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            v = v.strip()
            if v:
                v = html.escape(v)
        return v if v else None


class PriceLevelResponse(BaseModel):
    id: int
    user_id: int
    variety_id: int
    type: str
    price: Decimal
    note: Optional[str]
    source: str
    created_at: dt
    updated_at: dt

    model_config = ConfigDict(from_attributes=True)


class WatchlistCreate(BaseModel):
    variety_id: int = Field(..., ge=1)
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("notes", mode="before")
    @classmethod
    def sanitize_notes(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            v = v.strip()
            if v:
                v = html.escape(v)
        return v if v else None


class WatchlistUpdate(BaseModel):
    notes: Optional[str] = Field(None, max_length=500)
    is_notified: Optional[bool] = None

    @field_validator("notes", mode="before")
    @classmethod
    def sanitize_notes(cls, v: Optional[str]) -> Optional[str]:
        if isinstance(v, str):
            v = v.strip()
            if v:
                v = html.escape(v)
        return v if v else None


class WatchlistResponse(BaseModel):
    id: int
    user_id: int
    variety_id: int
    variety_symbol: str
    variety_name: str
    notes: Optional[str]
    is_notified: bool
    created_at: dt

    model_config = ConfigDict(from_attributes=True)


class WorkspaceSummary(BaseModel):
    price_levels: List[PriceLevelResponse]
    watchlists: List[WatchlistResponse]
    recent_comments: List[CommentResponse]


# ========== Contract / Rollover schemas ==========

class ContractResponse(BaseModel):
    id: int
    ts_code: str
    symbol: Optional[str]
    name: Optional[str]
    fut_code: Optional[str]
    exchange: Optional[str]
    list_date: Optional[dt]
    delist_date: Optional[dt]
    contract_type: Optional[str]
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ContractRolloverResponse(BaseModel):
    id: int
    variety_id: int
    old_contract_id: Optional[int]
    new_contract_id: Optional[int]
    old_contract_code: Optional[str]
    new_contract_code: Optional[str]
    effective_date: dt
    source: str
    created_at: dt

    model_config = ConfigDict(from_attributes=True)


class ContinuousKlineResponse(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    contract_code: Optional[str]
