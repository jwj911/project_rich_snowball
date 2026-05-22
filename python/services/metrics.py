"""
Prometheus 指标定义
========================
用于收集 API 请求延迟、错误率、采集任务成功率等可观测性数据。
"""

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

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


def metrics_response():
    """返回 Prometheus 指标文本。"""
    return generate_latest()


def get_content_type():
    """返回 Prometheus 指标 Content-Type。"""
    return CONTENT_TYPE_LATEST
