"""
Prometheus 指标定义
========================
用于收集 API 请求延迟、错误率、采集任务成功率等可观测性数据。
"""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# HTTP 请求总数（按方法和状态码分类）
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

# HTTP 请求处理延迟
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# 数据采集任务执行次数（按任务名和结果分类）
data_collection_runs_total = Counter(
    "data_collection_runs_total",
    "Total data collection runs",
    ["task_name", "status"],
)

# 数据采集任务执行耗时
data_collection_duration_seconds = Histogram(
    "data_collection_duration_seconds",
    "Data collection task duration in seconds",
    ["task_name"],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

# 缓存操作次数（按操作类型和命中结果分类）
cache_operations_total = Counter(
    "cache_operations_total",
    "Total cache operations",
    ["operation", "result"],
)

# 业务级操作计数器
auth_operations_total = Counter(
    "auth_operations_total",
    "Total auth operations",
    ["operation", "result"],
)

comment_operations_total = Counter(
    "comment_operations_total",
    "Total comment operations",
    ["action", "result"],
)

price_level_operations_total = Counter(
    "price_level_operations_total",
    "Total price level operations",
    ["action", "result"],
)

watchlist_operations_total = Counter(
    "watchlist_operations_total",
    "Total watchlist operations",
    ["action", "result"],
)

# 外部 API 调用延迟
external_api_duration_seconds = Histogram(
    "external_api_duration_seconds",
    "External data source API call duration in seconds",
    ["source", "operation"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

# HTTP 异常分类计数
http_exceptions_total = Counter(
    "http_exceptions_total",
    "Total HTTP exceptions by type",
    ["exception_type", "endpoint"],
)

# 数据库连接池指标（仅 PostgreSQL 等使用 QueuePool 时有效；SQLite 为 NullPool 不暴露状态）
db_pool_connections = Gauge(
    "db_pool_connections",
    "Current DB pool connection count by state",
    ["state"],
)
db_pool_connect_total = Counter(
    "db_pool_connect_total",
    "Total DB connections created",
)
db_pool_close_total = Counter(
    "db_pool_close_total",
    "Total DB connections closed",
)
db_pool_checkout_total = Counter(
    "db_pool_checkout_total",
    "Total DB connections checked out",
)
db_pool_checkin_total = Counter(
    "db_pool_checkin_total",
    "Total DB connections checked in",
)


def metrics_response():
    """返回 Prometheus 指标文本。"""
    return generate_latest()


def get_content_type():
    """返回 Prometheus 指标 Content-Type。"""
    return CONTENT_TYPE_LATEST
