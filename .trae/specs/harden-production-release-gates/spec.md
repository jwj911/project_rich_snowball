# R7 生产发布门禁与 SSE 更新信号 Spec

## Why

R6 已完成隔离环境发布候选验证，但真实生产发布仍依赖人工确认生产配置、发布元数据和
SSE 部署模式。同时，scheduler 已迁移到独立 worker，当前进程内行情更新时间无法被 API
进程及时感知，可能使 SSE 客户端长期收不到后续行情更新。

## What Changes

- 新增只读的生产发布预检命令，校验生产配置、发布/回滚元数据和 SSE 部署模式。
- 预检生成带独立 `trace_id` 的结构化诊断报告，并对凭据、连接串和 Provider Token 脱敏。
- 将实时行情更新时间写入 Redis 共享标记，使独立 worker 与 API 进程共享更新信号。
- Redis 不可用时保留本地状态，并按有界周期执行数据库刷新，避免 SSE 无限期停留在旧数据。
- 生产环境显式要求 `SSE_DEPLOYMENT_MODE=single|sticky`；本轮不实现跨实例连接注册和取消。
- 增加自动化回归与 CI 门禁，维护项目状态、路线图、发布清单、SSE 部署说明和迭代发布记录。
- 每轮验收完成后形成原子提交并推送至 GitHub `origin/master`。

## Impact

- Affected specs: 生产发布治理、实时行情 SSE、可观测性、运行拓扑。
- Affected code:
  - `python/services/release_preflight.py`
  - `python/scripts/release_preflight.py`
  - `python/services/realtime_state.py`
  - `python/data_collector/scheduler.py`
  - `python/routers/realtime.py`
  - `python/config.py`
  - `docker-compose.yml`
  - `.github/workflows/backend-ci.yml`
  - 相关后端测试与项目文档

## ADDED Requirements

### Requirement: 生产发布预检

系统 SHALL 提供只读的生产发布预检命令，并在修改数据库、Redis 或部署状态之前完成以下校验：

- `ENV` 必须为 `production`；
- `DATABASE_URL` 必须使用 PostgreSQL；
- `SECRET_KEY` 必须存在且长度不少于 32；
- CORS 来源必须存在、使用 HTTPS，且不得包含通配符、localhost 或 loopback；
- `DATA_SOURCE` 必须显式配置且不得为 `mock`；
- `REDIS_URL` 必须显式配置；
- 发布提交、UTC 发布窗口、发布负责人和回滚负责人必须存在；
- `SSE_DEPLOYMENT_MODE` 必须为当前支持的 `single` 或 `sticky`。

#### Scenario: 合法生产配置

- **WHEN** 操作者提供全部合法生产配置和发布元数据
- **THEN** 预检以退出码 0 结束，并将每项检查记录为通过

#### Scenario: 配置或元数据缺失

- **WHEN** 任一必填项缺失、格式错误或使用不安全值
- **THEN** 预检以非 0 退出码结束，并返回稳定、可定位的检查代码

#### Scenario: 不支持的 SSE 部署模式

- **WHEN** `SSE_DEPLOYMENT_MODE` 不是 `single` 或 `sticky`
- **THEN** 预检拒绝发布，并说明跨实例连接注册尚未实现

### Requirement: 脱敏诊断报告

系统 SHALL 为每次预检生成独立 `trace_id` 和结构化 JSON 报告。报告只记录检查代码、状态、
安全摘要、提交与时间元数据，不得记录原始 `SECRET_KEY`、数据库/Redis 密码、Provider Token
或原始行情数据。

#### Scenario: 预检失败

- **WHEN** 一个或多个检查失败
- **THEN** 报告仍被写入指定路径，并可通过 `trace_id` 与命令输出关联

#### Scenario: 凭据包含在输入中

- **WHEN** 数据库 URL、Redis URL 或 Provider 配置包含凭据
- **THEN** stdout、stderr、日志和报告均不得出现原始凭据

### Requirement: 跨进程行情更新信号

系统 SHALL 在 realtime quotes 成功刷新后更新本地状态，并在 Redis 可用时写入不包含行情内容的
共享更新标记。API 进程 SHALL 使用本地与共享标记中的较新值决定是否重新查询并推送 SSE 数据。

#### Scenario: 独立 worker 完成刷新

- **WHEN** worker 成功刷新 realtime quotes 并更新共享标记
- **THEN** API 进程中的既有 SSE 连接在下一个检查周期感知更新并推送最新行情

#### Scenario: 刷新失败

- **WHEN** realtime quotes 刷新抛出异常或未完成
- **THEN** 系统不得更新共享标记，也不得把失败误报为新行情

### Requirement: Redis 降级与有界陈旧时间

系统 SHALL 在 Redis 未配置、连接失败或运行中断开时继续提供 SSE 服务，并使用本地更新状态与
有界周期刷新作为降级路径。降级不得静默发生，且不得输出敏感连接信息。

#### Scenario: Redis 暂时不可用

- **WHEN** API 无法读取共享更新标记
- **THEN** SSE 保持连接并按配置的最长刷新间隔重新查询行情，同时记录脱敏的降级事件

#### Scenario: Redis 恢复

- **WHEN** Redis 在降级后恢复可用
- **THEN** 后续检查自动重新使用共享更新标记，无需重启 API

## MODIFIED Requirements

### Requirement: SSE 生产部署边界

生产部署 SHALL 显式选择 `single` 或 `sticky` 模式。`single` 表示实时行情 SSE 仅由单个 API
实例承载；`sticky` 表示负载均衡必须保证同一用户持续命中同一实例。两种模式均使用 Redis
共享行情更新标记，但每用户单连接和全局连接上限仍由实例本地管理。

#### Scenario: 生产配置未声明部署模式

- **WHEN** 生产预检未收到 `SSE_DEPLOYMENT_MODE`
- **THEN** 预检失败，且不得默认推断为已具备多实例能力

#### Scenario: 既有 SSE 行为回归

- **WHEN** 用户通过 access cookie 建立 SSE 连接
- **THEN** 既有鉴权、每用户单连接、50 个 symbol 上限、心跳和前端轮询降级行为保持不变

### Requirement: 迭代文档与远程交付

R7 完成后 SHALL 同步更新 `CHANGELOG.md`、`AGENTS.md`、`.agents/` 状态、README、迭代计划、
发布清单、SSE 扩展文档和新的非生产发布记录。所有验证通过后 SHALL 创建范围单一的提交并
推送至 GitHub；远程同步前不得把 R7 描述为真实生产已发布。

#### Scenario: 工程验收完成

- **WHEN** R7 代码、测试、CI 和文档均通过验收
- **THEN** 提交被推送到 `origin/master`，本地与远程提交一致且工作区干净

## REMOVED Requirements

本轮不移除现有 API 或兼容行为。Redis Pub/Sub 广播、跨实例连接注册与跨实例旧连接取消不在
R7 范围内，后续仅在并发量或高可用需求达到既定阈值时单独立项。
