# 后端可观测性 Runbook

> 制定日期：2026-05-26
> 目标：补全生产环境监控、告警、SLO 与恢复演练文档。

---

## 一、已具备的观测基础

| 组件 | 状态 | 说明 |
|------|------|------|
| Prometheus 指标 | ✅ | `services/metrics.py` 已注册 HTTP、Auth、Data Collection 计数器与直方图 |
| Request-ID 追踪 | ✅ | `main.py` 注入 `X-Request-ID`，structlog 上下文自动绑定 |
| 结构化日志 | ✅ | `services/logging_config.py` + structlog，JSON 格式输出 |
| 慢查询日志 | ✅ | SQLAlchemy 事件监听，阈值可通过 `SLOW_QUERY_THRESHOLD_SECONDS` 配置 |
| Scheduler 健康 | ✅ | `/health/scheduler` 返回最近 24h 任务统计、成功率、平均时长 |
| `/metrics` 端点 | ✅ | 限制为可信内网 IP，外网返回 403 |

---

## 二、建议的监控项与告警规则

### 2.1 黄金信号（Golden Signals）

| 信号 | 指标名 | 告警阈值建议 | 严重等级 |
|------|--------|-------------|----------|
| **延迟** | `http_request_duration_seconds` P99 | > 500ms 持续 5min | P2 |
| **流量** | `http_requests_total` QPS | 突增 > 300% 同比 | P3 |
| **错误** | `http_requests_total{status=~"5.."}` / 总数 | > 1% 持续 3min | P1 |
| **饱和度** | SQLAlchemy 连接池活跃连接数 | > 80% (pool_size=10) | P1 |

### 2.2 业务指标

| 指标 | 来源 | 告警阈值建议 | 严重等级 |
|------|------|-------------|----------|
| 采集成功率 | `data_collection_runs_total` (failed / total) | < 95% 持续 15min | P1 |
| 采集延迟 | `data_collection_duration_seconds` P99 | > 30s 持续 10min | P2 |
| 外部 API 延迟 | `external_api_duration_seconds` P99 | > 10s 持续 5min | P2 |
| 熔断器打开次数 | `circuit_breaker` 状态变化 | 任意熔断器打开 | P2 |
| 缓存命中率下降 | `cache_hit_rate`（需新增指标） | < 80% 持续 10min | P3 |

### 2.3 数据库指标

| 指标 | 来源 | 告警阈值建议 | 严重等级 |
|------|------|-------------|----------|
| 慢查询数量 | 结构化日志中 `slow_query=true` | > 10/min | P2 |
| 连接池等待 | SQLAlchemy `pool_timeout` 事件 | 任意等待 > 5s | P1 |
| PG 磁盘使用率 | node_exporter / cloud monitor | > 85% | P1 |

---

## 三、SLO 建议

| SLO | 目标 | 测量窗口 | 对应指标 |
|-----|------|----------|----------|
| API 可用性 | 99.9% | 30 天 | `http_requests_total` 中 2xx+3xx / 总数 |
| API P99 延迟 | < 300ms | 7 天 | `http_request_duration_seconds` |
| 实时行情 freshness | < 120s | 实时 | `mark_realtime_updated()` 时间戳 |
| 采集任务成功率 | > 98% | 7 天 | `data_collection_runs_total` |

---

## 四、Grafana 面板建议

### Panel 1：API 概览
- QPS（按状态码分类）
- P50/P95/P99 延迟
- 5xx 错误率

### Panel 2：数据采集合规
- 各任务成功率趋势
- 平均执行时长
- 熔断器状态表格

### Panel 3：数据库健康
- 连接池使用率
- 慢查询 TOP 10
- 事务等待时间

### Panel 4：资源饱和度
- CPU / 内存使用率
- 磁盘 I/O
- 网络流量

---

## 五、恢复演练 Checklist

### 演练场景 1：数据库连接池耗尽
1. 观察 `pool_overflow` 和活跃连接数
2. 定位慢查询 culprit
3. 临时扩容 `pool_size` / `max_overflow`
4. 重启应用释放僵尸连接（最后手段）

### 演练场景 2：外部数据源全部失败（Mock 降级）
1. 确认熔断器状态：`/health/scheduler` 或日志
2. 检查网络连通性：`curl` 外部 API
3. 非生产环境确认已降级 Mock
4. 生产环境不允许降级，需人工介入修复网络或更换 Token

### 演练场景 3：采集任务堆积
1. 检查 APScheduler `misfire_grace_time` 是否足够
2. 确认单任务执行时长是否超过调度间隔
3. 临时调高间隔或降低品种数量
4. 考虑将 worker 与 API 进程分离（已支持 `worker.py`）

---

## 六、缺失待补

- [ ] Grafana 大盘 JSON 导出并纳入版本控制
- [ ] Alertmanager 规则 YAML
- [ ] PagerDuty / 飞书 / 钉钉 告警通道配置
- [ ] 自动化恢复脚本（如连接池告警时自动重启）
- [ ] 容量基线文档（压测结果、QPS 上限、连接池上限）

---

*本 runbook 随生产运维实践更新。*
