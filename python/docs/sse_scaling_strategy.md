# SSE 横向扩展策略文档

> 制定日期：2026-05-29  
> 适用范围：实时行情 SSE 推送服务（`/api/realtime/stream`）

---

## 1. 当前架构

### 1.1 进程内状态

后端维护两份进程内全局状态：

1. **`_sse_connections: dict[int, asyncio.Task]`**（`routers/realtime.py`）
   - Key：`user_id`
   - Value：该用户当前活跃的 SSE `asyncio.Task`
   - 用途：同一用户限 1 个活跃连接；新连接建立时取消旧任务；全局上限 100 连接。

2. **`_last_update_time: datetime`**（`services/realtime_state.py`）
   - 用途：scheduler 每次刷新 realtime_quotes 后更新；SSE 生成器对比此时间决定是否推送。
   - 效果：将数据库查询频率从"每 5 秒"降到"数据有变更时才查"。

### 1.2 鉴权路径

- **当前一等路径**：cookie-only（`access_token` cookie）
- **废弃路径**：`POST /api/realtime/stream-token`（已标 `deprecated=True`，前端未消费）
- EventSource 通过 `withCredentials: true` 携带 cookie，后端 `effective_token = token or access_token`

### 1.3 单实例约束

由于 `_sse_connections` 和 `_last_update_time` 均为进程内状态，当前 SSE 服务**天然不支持多实例横向扩展**。若部署 2 个 API 实例：

- 用户 A 连接到实例 1，用户 B 连接到实例 2，各自正常。
- 同一用户通过负载均衡连到不同实例时，出现"多连接共存"（违背每用户限 1 连接）。
- scheduler 更新数据时，仅实例本地的 `_last_update_time` 被更新，其他实例 SSE 不会感知变更（导致不推送或延迟推送）。

---

## 2. 扩展路线

### 路线 A：单实例 + 负载均衡排除 SSE（当前，推荐）

**做法**：
- 声明 SSE 仅支持单 API 实例部署。
- 若使用 Nginx/ALB，将 `/api/realtime/stream` 路由到固定实例（或单独子域名指向单实例）。
- 其他 REST API 端点正常多实例负载均衡。

**适用场景**：
- 当前用户量和并发 SSE 连接数 < 100。
- 无需为 SSE 单独引入 Redis 或消息队列。

**风险**：
- SSE 实例成为单点，故障时实时推送中断（但 batch polling fallback 可用）。

---

### 路线 B：Sticky Session（中期，低成本）

**做法**：
- 负载均衡层启用 session affinity（如 Nginx `ip_hash`、AWS ALB sticky cookie）。
- 同一用户始终命中同一实例。
- `_sse_connections` 和 `_last_update_time` 仍保持进程内，不需要代码改造。

**适用场景**：
- 用户量增长，需要多实例分担 REST API 流量，但 SSE 并发仍可控。
- 不想引入 Redis 等外部依赖。

**风险**：
- 实例故障时，该实例上的 SSE 连接全部断开，用户需重连到另一实例。
- 实例扩缩容时，已有 sticky session 可能被打散。
- `_last_update_time` 仍是进程内，若 scheduler 与 SSE 不在同一实例，SSE 无法感知数据更新。
  - **缓解**：scheduler 更新数据时通过数据库/共享存储广播变更时间戳。

---

### 路线 C：Redis Pub/Sub（长期，支撑大规模）

**做法**：

1. **连接状态外迁**：
   - `_sse_connections` 从进程内 dict 改为 Redis Hash 或 Set。
   - Key：`sse:connections:{user_id}`，Value：实例标识 + 任务标识。
   - 新连接建立时，所有实例检查 Redis 中该用户的旧连接，旧连接所在实例负责取消任务。

2. **更新事件广播**：
   - scheduler 刷新数据后，向 Redis Pub/Sub channel `realtime:updates` 发布消息（含更新时间戳）。
   - 所有 API 实例订阅该 channel，收到消息后更新本地 `_last_update_time` 或触发推送。

3. **架构变化**：
   - `services/realtime_state.py`：增加 Redis pub/sub 订阅逻辑。
   - `routers/realtime.py`：连接注册/注销走 Redis；上限检查走 Redis `SCARD`。
   - `data_collector/scheduler.py` 或 pipeline：刷新完成后 publish 更新事件。

**适用场景**：
- SSE 并发连接 > 500 或需要多实例高可用。
- 已有 Redis 基础设施（当前项目已支持 Redis 缓存）。

**风险**：
- 代码复杂度增加（分布式连接管理、Redis 断线重连、消息丢失处理）。
- 需要引入 Redis pub/sub 消费者协程（可能增加 CPU/内存开销）。

---

## 3. 决策矩阵

| 指标 | 路线 A（单实例） | 路线 B（Sticky） | 路线 C（Redis） |
|------|-----------------|-----------------|----------------|
| 代码改动量 | 无 | 无（配置层） | 中等（~200 行） |
| 运维复杂度 | 低 | 低 | 中 |
| 外部依赖 | 无 | 无 | Redis |
| 单点风险 | 有（SSE 实例） | 有（实例级） | 无 |
| 并发上限 | 100/实例 | 100/实例 | 100×实例数 |
| 数据更新感知 | 本地 | 需额外机制 | 实时广播 |
| 推荐阈值 | 当前阶段 | 并发 50-200 | 并发 200+ |

---

## 4. 当前建议（2026-05-29）

1. **立即执行**：在 README/部署文档中声明 SSE 仅支持单实例，或必须通过 sticky session 路由。
2. **暂不执行**：不引入 Redis pub/sub，不改造 `_sse_connections`。
3. **监控指标**：关注 `/metrics` 中 SSE 相关指标（如有）或新增连接数日志，达到 50 并发时评估路线 B，达到 100 并发时评估路线 C。
4. **鉴权保持**：继续 cookie-only 策略，stream-token 保持 deprecated，下个大版本考虑移除。

---

## 5. 验收清单

- [x] `_sse_connections` 确认为进程内状态
- [x] cookie-only 鉴权已统一
- [x] 本文档已产出
- [ ] 部署文档已补充单实例/sticky session 约束说明（待后续补充）

---

*最后更新：2026-05-29*
