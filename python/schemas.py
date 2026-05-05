from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import List, Optional
from datetime import datetime as dt
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

    @field_validator("content", mode="before")
    @classmethod
    def sanitize_content(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        return html.escape(v)


class CommentResponse(BaseModel):
    id: int
    product_id: int
    user_id: int
    username: str
    content: str
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
