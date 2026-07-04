import html
from datetime import datetime as dt
from decimal import Decimal
from enum import StrEnum
from typing import Any

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


class IndicatorResponse(BaseModel):
    """技术指标响应项。

    固定返回基础 OHLCV 和时间，其余指标字段通过 extra='allow' 动态附加。
    """

    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int

    model_config = ConfigDict(extra="allow")


class KlineSummaryResponse(BaseModel):
    """多周期 K 线汇总响应。"""

    data: dict[str, list[KlineResponse]]

    model_config = ConfigDict(extra="allow")


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


class MarketComparisonItem(BaseModel):
    symbol: str
    current_price: float | None
    change_percent: float
    direction: str


class MarketComparisonResponse(BaseModel):
    items: list[MarketComparisonItem]

    model_config = ConfigDict(from_attributes=True)


class DataQualityDetail(BaseModel):
    symbol: str
    data_source: str | None
    updated_at: str | None
    stale: bool


class DataQualityResponse(BaseModel):
    overall: str
    total: int
    stale_count: int
    stale_threshold_seconds: float
    details: list[DataQualityDetail]

    model_config = ConfigDict(from_attributes=True)


# ========== Frontend Logs ==========


def _validate_payload_structure(v: dict) -> dict:
    """校验 payload 结构：深度不超过 3，key 数不超过 20。"""
    if not isinstance(v, dict):
        raise ValueError("payload 必须是对象")

    def _count_keys(obj: dict | list | object, depth: int) -> tuple[int, int]:
        """返回 (key_count, max_depth)。"""
        if not isinstance(obj, dict):
            return 0, depth
        keys = len(obj)
        max_d = depth
        for val in obj.values():
            if isinstance(val, dict):
                k, d = _count_keys(val, depth + 1)
                keys += k
                max_d = max(max_d, d)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, (dict, list)):
                        k, d = _count_keys(item, depth + 1)
                        keys += k
                        max_d = max(max_d, d)
        return keys, max_d

    key_count, max_depth = _count_keys(v, 1)
    if max_depth > 3:
        raise ValueError("payload 嵌套深度不得超过 3 层")
    if key_count > 20:
        raise ValueError("payload 键数量不得超过 20 个")
    return v


class FrontendLogCreate(BaseModel):
    type: str = Field(..., max_length=20)
    payload: dict = Field(default_factory=dict)
    level: str | None = Field(default=None, max_length=20)
    meta: dict = Field(default_factory=dict)
    user_id: int | None = Field(
        default=None,
        ge=1,
        description="已废弃：后端从请求 token 中解析用户身份，此字段被忽略",
    )

    @field_validator("type", "level", mode="before")
    @classmethod
    def _strip_strings(cls, v):
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("payload")
    @classmethod
    def _validate_payload(cls, v):
        return _validate_payload_structure(v)


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


def _validate_safe_url(v: str) -> str:
    """校验 URL 安全：禁止非 HTTP(S) scheme 和内网/本地地址。"""
    import ipaddress
    from urllib.parse import urlparse

    try:
        parsed = urlparse(v)
    except Exception as exc:
        raise ValueError("无效的 URL") from exc

    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL scheme 必须是 http 或 https")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL 必须包含有效主机名")

    hostname_lower = hostname.lower()
    if hostname_lower in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise ValueError("禁止访问本地地址")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        pass  # 不是 IP 地址，无需进一步检查
    else:
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("禁止访问内网地址")

    return v


class NewsSourceBase(BaseModel):
    """新闻源基础字段。"""

    name: str = Field(..., max_length=100)
    url: str = Field(..., max_length=500)
    category: str | None = Field(default=None, max_length=50)
    is_enabled: bool = Field(default=True)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        return _validate_safe_url(v)


class NewsSourceCreate(NewsSourceBase):
    """创建新闻源请求。"""

    pass


class NewsSourceUserCreate(BaseModel):
    """普通用户创建自定义新闻源请求。"""

    name: str = Field(..., max_length=100)
    url: str = Field(..., max_length=500)
    category: str | None = Field(default=None, max_length=50)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        return _validate_safe_url(v)


class NewsSourceResponse(NewsSourceBase):
    """新闻源响应。"""

    id: int
    is_builtin: bool
    user_id: int | None
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
    ai_summary: str | None
    url: str
    published_at: dt | None
    fetched_at: dt

    model_config = ConfigDict(from_attributes=True)


class NewsFetchTaskResponse(BaseModel):
    """RSS 抓取任务提交响应。"""

    status: str = Field(default="accepted")
    message: str
    source_id: int | None = Field(default=None)


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

    @field_validator("reason", mode="before")
    @classmethod
    def _sanitize_reason(cls, v):
        return sanitize_html_text(v) if isinstance(v, str) else v


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

    @field_validator("reason", mode="before")
    @classmethod
    def _sanitize_reason(cls, v):
        return sanitize_html_text(v) if isinstance(v, str) else v


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


class PriceAlertCreate(BaseModel):
    """创建价格预警请求。"""

    variety_id: int = Field(..., ge=1)
    alert_type: str = Field(..., max_length=10)
    target_price: Decimal = Field(..., ge=0, decimal_places=4)

    @field_validator("alert_type", mode="before")
    @classmethod
    def _normalize_alert_type(cls, v):
        if isinstance(v, str):
            v = v.strip().lower()
            if v not in ("above", "below"):
                raise ValueError('alert_type must be one of: "above", "below"')
            return v
        return v


class PriceAlertUpdate(BaseModel):
    """更新价格预警请求。"""

    target_price: Decimal | None = Field(default=None, ge=0, decimal_places=4)
    is_triggered: bool | None = Field(default=None)


class PriceAlertResponse(BaseModel):
    """价格预警响应。"""

    id: int
    user_id: int
    variety_id: int
    variety_symbol: str
    variety_name: str
    alert_type: str
    target_price: Decimal
    is_triggered: bool
    triggered_at: dt | None
    created_at: dt

    model_config = ConfigDict(from_attributes=True)


class TradeRecordCreate(BaseModel):
    """创建模拟持仓请求。"""

    variety_id: int = Field(..., ge=1)
    opinion_id: int | None = Field(default=None, ge=1)
    direction: str = Field(..., max_length=10)  # long | short
    entry_price: Decimal = Field(..., ge=0, decimal_places=4)
    quantity: int = Field(default=1, ge=1)

    @field_validator("direction", mode="before")
    @classmethod
    def _normalize_direction(cls, v):
        if isinstance(v, str):
            v = v.strip().lower()
            if v not in ("long", "short"):
                raise ValueError('direction must be one of: "long", "short"')
            return v
        return v


class TradeRecordClose(BaseModel):
    """平仓请求。"""

    exit_price: Decimal = Field(..., ge=0, decimal_places=4)


class TradeRecordResponse(BaseModel):
    """模拟持仓响应。"""

    id: int
    user_id: int
    variety_id: int
    variety_symbol: str
    variety_name: str
    opinion_id: int | None
    direction: str
    entry_price: Decimal
    exit_price: Decimal | None
    quantity: int
    status: str
    pnl: Decimal | None
    pnl_percent: Decimal | None
    unrealized_pnl: Decimal | None
    unrealized_pnl_percent: Decimal | None
    closed_at: dt | None
    created_at: dt

    model_config = ConfigDict(from_attributes=True)


class ChatMessageCreate(BaseModel):
    """发送 AI 聊天消息请求。"""

    content: str = Field(..., min_length=1, max_length=4000)


class ChatMessageResponse(BaseModel):
    """AI 聊天消息响应。"""

    id: int
    role: str
    content: str
    created_at: dt

    model_config = ConfigDict(from_attributes=True)


# ========== Agent / AI Assistant schemas ==========


class AgentType(StrEnum):
    """Agent 类型枚举。"""

    DATA = "data"
    TECH_ANALYSIS = "tech_analysis"
    RISK_MANAGEMENT = "risk_management"
    ANALYSIS_PIPELINE = "analysis_pipeline"
    BACKTEST = "backtest"
    ORCHESTRATOR = "orchestrator"
    STRATEGY_COMPILER = "strategy_compiler"
    FACTOR_MINING = "factor_mining"


class AgentTaskStatus(StrEnum):
    """Agent 任务状态枚举。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentTaskStepRole(StrEnum):
    """Agent 任务步骤角色枚举。"""

    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    SYSTEM = "system"
    ERROR = "error"


class AgentTaskCreate(BaseModel):
    """创建 Agent 任务请求。"""

    agent_type: str = Field(..., pattern=r"^(data|tech_analysis|risk_management|analysis_pipeline|backtest|orchestrator|factor_mining|strategy_compiler)$")
    query: str = Field(..., min_length=1, max_length=4000)


class AgentTaskStepResponse(BaseModel):
    """Agent 任务步骤响应。"""

    id: int
    task_id: int
    step_number: int
    role: str
    content: str
    tool_name: str | None
    tool_input: dict[str, Any] | None
    tool_output: Any = None
    created_at: dt

    model_config = ConfigDict(from_attributes=True)

    @field_validator("tool_input", "tool_output", mode="before")
    @classmethod
    def _parse_json_field(cls, v):
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
        return v


class AgentTaskResponse(BaseModel):
    """Agent 任务响应。"""

    id: int
    user_id: int
    parent_task_id: int | None = None
    agent_type: str
    query: str
    status: str
    result: dict[str, Any] | None
    error_message: str | None
    started_at: dt | None
    finished_at: dt | None
    created_at: dt
    steps: list[AgentTaskStepResponse] = Field(default_factory=list)
    sub_tasks: list["AgentTaskResponse"] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @field_validator("result", mode="before")
    @classmethod
    def _parse_result_json(cls, v):
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except (json.JSONDecodeError, TypeError):
                return None
        return v


class AgentCapabilityStatus(BaseModel):
    """单个 Agent 能力状态。"""

    agent_type: str
    label: str
    enabled: bool
    requires_llm: bool = False
    reason: str | None = None


class AgentStatusSummary(BaseModel):
    """Agent 状态汇总。"""

    server_time: dt
    llm_configured: bool
    total_tasks: int
    running_tasks: int
    completed_tasks: int
    failed_tasks: int
    recent_failed_tasks: list[AgentTaskResponse] = Field(default_factory=list)
    capabilities: list[AgentCapabilityStatus] = Field(default_factory=list)


class AgentPermissionHeartbeat(BaseModel):
    """Agent 权限心跳响应。"""

    server_time: dt
    authenticated: bool
    user_id: int
    username: str
    role: str
    can_create_tasks: bool
    can_stream_chat: bool
    can_view_own_tasks: bool
    can_delete_own_tasks: bool
    allowed_agent_types: list[str] = Field(default_factory=list)
    csrf_policy: str
    token_transport: str


class AgentChatRequest(BaseModel):
    """Agent 流式对话请求。

    兼容现有 Chat 接口，增加 agent_type 字段支持切换 Agent 模式。
    """

    content: str = Field(..., min_length=1, max_length=4000)
    agent_type: str = Field(default="data", pattern=r"^(data|tech_analysis|risk_management|analysis_pipeline|backtest|orchestrator|factor_mining|strategy_compiler)$")


class AgentStreamEvent(BaseModel):
    """Agent SSE 流式事件。

    用于向前端推送 Agent 思考过程和执行步骤。
    """

    event_type: str = Field(..., pattern=r"^(start|thought|action|observation|result|error|done)$")
    task_id: int | None = None
    step_number: int | None = None
    role: str | None = None
    content: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output: Any = None
    result: dict[str, Any] | None = None
    error_message: str | None = None

    model_config = ConfigDict(from_attributes=True)
