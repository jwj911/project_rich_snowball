# Tasks

- [x] Task 1: 建立生产发布预检核心能力，集中校验生产配置、发布元数据和 SSE 部署模式。
  - [x] SubTask 1.1: 定义稳定的检查代码、结果模型和总体验收状态。
  - [x] SubTask 1.2: 校验 PostgreSQL、强密钥、HTTPS CORS、真实数据源、Redis、提交、UTC 窗口及负责人。
  - [x] SubTask 1.3: 对连接串、Token 和密钥执行统一脱敏，禁止报告原始敏感值。
  - [x] SubTask 1.4: 生成包含独立 `trace_id` 的结构化诊断报告。

- [x] Task 2: 提供只读预检 CLI，并保证成功/失败均有可审计输出。
  - [x] SubTask 2.1: 从环境变量和命令参数读取预检输入，支持显式报告输出路径。
  - [x] SubTask 2.2: 通过退出码区分通过、门禁失败和报告写入失败。
  - [x] SubTask 2.3: 确认命令不修改数据库、Redis、部署状态或发布清单。

- [x] Task 3: 让 worker 与 API 共享 realtime quotes 更新标记。
  - [x] SubTask 3.1: 扩展 realtime state，在成功刷新后更新本地状态及 Redis 共享标记。
  - [x] SubTask 3.2: API 读取本地/共享标记中的较新值，驱动既有 SSE 查询与推送。
  - [x] SubTask 3.3: 刷新失败时不写共享标记，且标记内容不得包含原始行情数据。
  - [x] SubTask 3.4: Redis 异常时使用本地状态和有界周期刷新，并记录脱敏降级事件。

- [x] Task 4: 固化生产 SSE 部署边界和运行拓扑。
  - [x] SubTask 4.1: 增加 `SSE_DEPLOYMENT_MODE` 配置，生产环境只接受 `single` 或 `sticky`。
  - [x] SubTask 4.2: 更新 Compose，使 backend 与 worker 显式共享 Redis 和 SSE 部署模式。
  - [x] SubTask 4.3: 保持 access cookie、单用户连接、全局连接上限、symbol 上限和心跳契约不变。

- [x] Task 5: 补齐自动化验证和 CI 门禁。
  - [x] SubTask 5.1: 覆盖全部预检通过、逐项失败、退出码、`trace_id` 和诊断报告脱敏。
  - [x] SubTask 5.2: 使用共享 Redis fake/mocked client 模拟 worker 与 API 的独立进程状态。
  - [x] SubTask 5.3: 覆盖 Redis 断开、恢复、有界刷新和失败刷新不发布标记。
  - [x] SubTask 5.4: 回归现有 SSE 鉴权、限流、连接清理和 scheduler 测试。
  - [x] SubTask 5.5: 在 Backend CI 中执行 R7 专项门禁，并运行 Ruff 与后端全量 pytest。

- [ ] Task 6: 维护迭代和发布文档，保持工程基线与生产发布状态一致。
  - [ ] SubTask 6.1: 更新 `CHANGELOG.md`、`AGENTS.md`、`.agents/`、README 和迭代计划。
  - [ ] SubTask 6.2: 更新发布清单与 `python/docs/sse_scaling_strategy.md`，说明共享标记和剩余边界。
  - [ ] SubTask 6.3: 新增 R7 非生产发布记录，填写提交、测试、CI、回滚点和未完成生产项。
  - [ ] SubTask 6.4: 校验变更文档的相对链接、测试计数、提交哈希和状态表述。

- [ ] Task 7: 原子提交并推送本轮迭代。
  - [ ] SubTask 7.1: 检查工作区，只暂存 R7 相关代码、测试、规格和文档。
  - [ ] SubTask 7.2: 运行 pre-commit 与最终差异检查，创建范围单一的迭代提交。
  - [ ] SubTask 7.3: 推送至 `origin/master`，确认本地/远程提交一致且工作区干净。
  - [ ] SubTask 7.4: 记录远程 CI 结果；CI 失败时修复、重新验证并以独立提交推送。

# Task Dependencies

- Task 2 depends on Task 1.
- Task 4 depends on Task 1 and Task 3.
- Task 5 depends on Task 1 through Task 4.
- Task 6 depends on Task 5 的最终验证结果。
- Task 7 depends on Task 5 and Task 6.
- Task 1 与 Task 3 可并行实施。
