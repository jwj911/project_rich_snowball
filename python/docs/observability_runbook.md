# 可观测性运维手册（Observability Runbook）

> 目标：为生产环境提供有据可查、有险可防的观测体系。
> 更新日期：2026-05-27

---

## 一、指标总览

后端已接入 Prometheus 风格指标 + structlog 结构化日志，核心指标如下：

### 1.1 HTTP 层指标

| 指标名 | 类型 | 标签 | 说明 |
|--------|------|------|------|
| `http_requests_total` | Counter | method, endpoint, status_code | 按方法和状态码分类的请求总数 |
| `http_request_duration_seconds` | Histogram | method, endpoint | 请求处理延迟，桶覆盖 5ms~10s |
| `http_exceptions_total` | Counter | exception_type, endpoint | 未捕获异常分类计数 |

**采集方式**：`main.py:prometheus_middleware` 自动收集，跳过 `/metrics`, `/docs`, `/redoc`, `/openapi.json`。

### 1.2 数据采集指标

| 指标名 | 类型 | 标签 | 说明 |
|--------|------|------|------|
| `data_collection_runs_total` | Counter | task_name, status | 各任务执行次数（success/failed） |
| `data_collection_duration_seconds` | Histogram | task_name | 任务执行耗时，桶覆盖 0.5s~5min |
| `external_api_duration_seconds` | Histogram | source, operation | 外部数据源（AkShare/Tushare/Mock）调用延迟 |

**采集方式**：`data_collector/pipeline.py` 和 `data_collector/collector_registry.py` 中手动埋点。

### 1.3 缓存与业务指标

| 指标名 | 类型 | 标签 | 说明 |
|--------|------|------|------|
| `cache_operations_total` | Counter | operation, result | 缓存命中/ miss / 穿透 |
| `auth_operations_total` | Counter | operation, result | 登录/注册/刷新 token |
| `comment_operations_total` | Counter | action, result | 评论 CRUD |
| `price_level_operations_total` | Counter | action, result | 价位标注 CRUD |
| `watchlist_operations_total` | Counter | action, result | 自选 CRUD |

### 1.4 日志与追踪

- **request_id**：每个请求自动注入 `X-Request-ID`，structlog 上下文绑定，全链路可追踪。
- **慢查询日志**：SQLAlchemy 事件监听，阈值可通过 `SLOW_QUERY_THRESHOLD_SECONDS` 配置（默认 1.0s）。
- **结构化日志**：JSON 格式输出，包含 timestamp, level, request_id, event, msg 等字段。

---

## 二、关键告警规则（PromQL）

### 2.1 可用性

```promql
# API 5xx 错误率 > 1% 持续 2 分钟
(
  sum(rate(http_requests_total{status_code=~"5.."}[2m]))
  /
  sum(rate(http_requests_total[2m]))
) > 0.01

# /health 端点返回非 200
up{job="futures-api"} == 0
```

**严重等级**：P1（页面级告警，立即处理）
**恢复条件**：5xx 比例 < 0.1% 持续 2 分钟

### 2.2 延迟

```promql
# P99 延迟 > 500ms 持续 3 分钟
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint)
) > 0.5

# 关键端点 P95 > 200ms
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket{endpoint=~"/api/products|/api/realtime"}[5m])) by (le)
) > 0.2
```

**严重等级**：P2（性能告警，30 分钟内响应）
**恢复条件**：P99 < 300ms 持续 5 分钟

### 2.3 数据采集

```promql
# 实时行情任务 10 分钟内无成功记录
increase(data_collection_runs_total{task_name="refresh_realtime_quotes",status="success"}[10m]) == 0

# 任意采集任务失败率 > 20% 持续 15 分钟
(
  sum(rate(data_collection_runs_total{status="failed"}[15m])) by (task_name)
  /
  sum(rate(data_collection_runs_total[15m])) by (task_name)
) > 0.2

# 外部 API 调用 P99 > 30s
histogram_quantile(0.99,
  sum(rate(external_api_duration_seconds_bucket[10m])) by (le, source)
) > 30
```

**严重等级**：P1（数据断流影响交易决策）
**恢复条件**：任务恢复正常执行或 fallback 到 Mock

### 2.4 缓存与数据库

```promql
# 缓存降级频率过高（Redis 不可用时内存 fallback 占比 > 50%）
(
  sum(rate(cache_operations_total{result="fallback"}[10m]))
  /
  sum(rate(cache_operations_total[10m]))
) > 0.5
```

**严重等级**：P2
**说明**：Redis 降级本身不影响功能，但多实例部署时缓存不共享，可能导致 DB 压力上升。

---

## 三、SLO 建议

| 指标 | SLO | 测量窗口 |
|------|-----|----------|
| API 可用性 | > 99.9% | 30 天 |
| P99 延迟 | < 500ms | 7 天 |
| 数据采集成功率 | > 98% | 7 天 |
| 实时行情 freshness | < 90s（上次成功到当前时间） | 实时 |

---

## 四、排查手册

### 4.1 5xx 突增

1. 查看 `/health/ready` 确认 DB 和 Redis 状态。
2. 按 `exception_type` 聚合 `http_exceptions_total`，定位异常类型。
3. 检索 structlog 中 `level=error` 且时间窗口匹配的日志，关注 `request_id`。
4. 检查 `/health/scheduler` 是否有采集任务失败导致数据不一致。

### 4.2 延迟飙升

1. 按 `endpoint` 拆分 `http_request_duration_seconds`，定位慢端点。
2. 检查慢查询日志（`SLOW_QUERY_THRESHOLD_SECONDS` 阈值以上）。
3. 确认是否缓存降级：`cache_operations_total{result="fallback"}` 是否上升。
4. 检查 DB 连接池是否耗尽（需补充连接池指标，见"待办"）。

### 4.3 数据采集中断

1. 查看 `/health/scheduler` 的最近任务历史和成功率。
2. 检查熔断器状态：`circuit_breakers` 中是否有源被打开。
3. 查看 `external_api_duration_seconds` 确认外部源是否超时。
4. 检查 `ENABLE_SCHEDULER` 配置和 scheduler 进程是否运行。

### 4.4 实时行情 stale

1. 前端页面是否显示"数据刷新中"或心跳超时。
2. 检查 `refresh_realtime_quotes` 任务最近成功时间。
3. 确认 `RealtimeQuoteDB` 中最新记录时间戳。
4. 检查 collector fallback 链是否正常降级。

---

## 五、Dashboard 建议（Grafana）

### Panel 1：QPS & 错误率
- `sum(rate(http_requests_total[1m])) by (status_code)`
- 堆叠面积图，区分 2xx/4xx/5xx

### Panel 2：P50/P95/P99 延迟
- `histogram_quantile(0.50/0.95/0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))`
- 按关键端点分线

### Panel 3：DB 慢查询 TOP 10
- 需接入日志数据源（Loki/ELK）
- 过滤 `event="slow_query"`

### Panel 4：采集任务成功率
- `sum(rate(data_collection_runs_total{status="success"}[10m])) by (task_name) / sum(rate(data_collection_runs_total[10m])) by (task_name)`

### Panel 5：外部源延迟
- `histogram_quantile(0.95, sum(rate(external_api_duration_seconds_bucket[10m])) by (le, source))`

### Panel 6：缓存命中率
- `sum(rate(cache_operations_total{result="hit"}[5m])) / sum(rate(cache_operations_total[5m]))`

---

## 六、待办（待补充指标）

- [ ] **DB 连接池指标**：通过 SQLAlchemy event 暴露 `pool_size`, `checked_in`, `checked_out`, `overflow`。
- [ ] **JVM/GC 类指标**：Python 无 GC 压力指标，但可补充 `gc.collect()` 频率和内存占用。
- [ ] **业务级 SLO 面板**：用户登录成功率、评论发布成功率等。
- [ ] **告警通知渠道**：当前仅有指标，无告警路由（PagerDuty/钉钉/企业微信）。

---

*本文档随迭代进展更新。当前指标已覆盖 HTTP、采集、缓存、业务四层，缺少连接池和内存指标。*
