# SSE 横向扩展策略文档

> 制定日期：2026-05-29  
> 最后更新：2026-07-30（R7 Redis 更新时间戳共享标记）
> 适用范围：实时行情 SSE 推送服务（`/api/realtime/stream`）

---

## 1. 当前架构

### 1.1 进程内状态

后端维护实例内连接状态，以及本地/Redis 共享的行情更新时间：

1. **`_sse_connections: dict[int, asyncio.Task]`**（`routers/realtime.py`）
   - Key：`user_id`
   - Value：该用户当前活跃的 SSE `asyncio.Task`
   - 用途：同一用户限 1 个活跃连接；新连接建立时取消旧任务；全局上限 100 连接。

2. **本地 `_last_update_time` + Redis `futures:realtime:update_time`**
   （`services/realtime_state.py`）
   - worker 仅在 realtime quotes 成功刷新后更新本地时间，并尽力向 Redis 写入同一个 UTC
     时间戳；刷新失败不发布标记。
   - API 读取本地与共享标记中的较新值，SSE 生成器据此决定是否重新查询和推送。
   - 标记不包含 symbol、价格或其他原始行情内容。
   - Redis 未配置、断开或标记非法时记录脱敏降级事件，并至少每 60 秒强制重新查询；Redis
     恢复后自动重新使用共享标记。

### 1.2 鉴权路径

- **当前一等路径**：cookie-only（`access_token` cookie）
- **废弃路径**：`POST /api/realtime/stream-token`（已标 `deprecated=True`，前端未消费）
- EventSource 通过 `withCredentials: true` 携带 cookie，后端 `effective_token = token or access_token`

### 1.3 R7 生产部署边界

生产环境必须显式配置 `SSE_DEPLOYMENT_MODE=single|sticky`。R7 解决了独立 worker 与 API
之间的行情更新感知，但没有实现分布式连接管理。若部署多个 API 实例：

- 用户 A 连接到实例 1，用户 B 连接到实例 2，各自正常。
- 同一用户通过负载均衡连到不同实例时，出现"多连接共存"（违背每用户限 1 连接）。
- 各实例可通过 Redis 时间戳感知 worker 刷新，但每用户旧连接取消和全局连接上限仍只在实例
  内生效。
- `single` 表示仅一个 API 实例承载 SSE；`sticky` 表示负载均衡必须保证同一用户持续命中
  同一实例。
- 本轮未实现 Redis Pub/Sub、跨实例连接注册/注销或跨实例旧连接取消，因此不得使用其他
  模式，也不得把共享时间戳描述为完整多实例 SSE 支持。

---

## 2. 扩展路线

### 路线 A：单实例 + 负载均衡排除 SSE（当前，推荐）

**做法**：
- 声明 SSE 仅支持单 API 实例部署。
- 若使用 Nginx/ALB，将 `/api/realtime/stream` 路由到固定实例（或单独子域名指向单实例）。
- 其他 REST API 端点正常多实例负载均衡。

**适用场景**：
- 当前用户量和并发 SSE 连接数 < 100。
- 生产已有 Redis，用于 worker/API 更新时间戳共享；无需引入 Pub/Sub 或消息队列。

**风险**：
- SSE 实例成为单点，故障时实时推送中断（但 batch polling fallback 可用）。

---

### 路线 B：Sticky Session（中期，低成本）

**做法**：
- 负载均衡层启用 session affinity（如 Nginx `ip_hash`、AWS ALB sticky cookie）。
- 同一用户始终命中同一实例。
- `_sse_connections` 保持进程内；行情更新时间通过 R7 Redis 时间戳共享标记传播。

**适用场景**：
- 用户量增长，需要多实例分担 REST API 流量，但 SSE 并发仍可控。
- 不想引入 Redis 等外部依赖。

**风险**：
- 实例故障时，该实例上的 SSE 连接全部断开，用户需重连到另一实例。
- 实例扩缩容时，已有 sticky session 可能被打散。
- 同一用户若绕过或丢失会话亲和，仍可能在不同实例保留多个连接。
- 每实例 100 连接上限不是集群全局上限。

---

### 路线 C：Redis Pub/Sub（长期，支撑大规模）

> R7 当前只使用 Redis key 共享最新更新时间戳，不包含以下 Pub/Sub 与分布式连接能力。

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
| 外部依赖 | Redis 时间戳标记 | Redis 时间戳标记 | Redis Pub/Sub/连接注册 |
| 单点风险 | 有（SSE 实例） | 有（实例级） | 无 |
| 并发上限 | 100/实例 | 100/实例 | 100×实例数 |
| 数据更新感知 | Redis 时间戳 | Redis 时间戳 | Pub/Sub 实时广播 |
| 推荐阈值 | 当前阶段 | 并发 50-200 | 并发 200+ |

---

## 4. 当前建议（2026-07-30，R7 更新）

1. **生产必选**：显式设置 `SSE_DEPLOYMENT_MODE=single|sticky`，并为 backend/worker
   配置同一个 `REDIS_URL`。
2. **更新时间戳**：只把 Redis 标记作为 worker/API 刷新通知；不得在标记中写入行情内容，
   也不得把它当作连接注册表。
3. **降级边界**：Redis 不可用时允许 SSE 保持服务，但必须保留脱敏降级日志和 60 秒有界刷新。
4. **暂不执行**：不引入 Redis Pub/Sub，不改造 `_sse_connections`；达到多实例高可用或
   连接并发阈值后单独立项。
5. **鉴权保持**：cookie-only 策略已统一，`/api/realtime/stream` 的 `token` Query 参数已标记
   `deprecated=True`，仅作降级兼容。生产环境必须确保 cookie 正常工作。
6. **限流保护**：`middleware/rate_limit.py` 已对 `/api/realtime/stream` 实施独立限流
   （60s/30req），防止恶意高频建立 SSE 连接。

---

## 5. 验收清单

- [x] `_sse_connections` 确认为进程内状态
- [x] cookie-only 鉴权已统一
- [x] stream-token 已废弃（`deprecated=True`）
- [x] SSE 独立限流已实施（60s/30req）
- [x] 本文档已产出
- [x] 部署文档已补充单实例/sticky session 约束说明
- [x] worker/API 使用 Redis UTC 时间戳共享 realtime quotes 更新信号
- [x] Redis 降级时按 60 秒有界周期刷新，并在恢复后自动回到共享标记
- [x] 生产配置仅接受 `single|sticky`
- [ ] Redis Pub/Sub 更新广播
- [ ] 跨实例连接注册、全局上限和旧连接取消

---

*最后更新：2026-07-30*
