# Tasks

- [x] Task 1: 完成 R8 交接检查，确认已完成迭代先于 R9 保持在 GitHub 远端。
  - [x] SubTask 1.1: fetch `origin` 并确认当前分支为 `master`。
  - [x] SubTask 1.2: 确认本地与 `origin/master` 领先/落后均为 0，远端包含 R8 最终文档提交。
  - [x] SubTask 1.3: 执行无破坏性的 `git push origin master` 同步检查，并确认工作区干净。

- [x] Task 2: 在 R9 代码实施前更新项目文档并推送独立启动提交。
  - [x] SubTask 2.1: 在当前迭代事实源中新增 R9，说明 S1 Report-Only 范围、验收和停止条件。
  - [x] SubTask 2.2: 同步 README、AGENTS、`.agents/roadmap.md`、`.agents/security.md` 和必要的发布入口。
  - [x] SubTask 2.3: 校验文档仍准确描述 R8 非生产边界，并明确 R9 不收紧强制 CSP、不迁移 token。
  - [x] SubTask 2.4: 只暂存规格与 R9 启动文档，运行文档差异检查，创建原子提交并推送 GitHub。
  - [x] SubTask 2.5: 确认 R9 实现提交尚不存在时，启动文档提交已经可从 `origin/master` 解析。

- [x] Task 3: 实现安全、可审计的 CSP 报告接收与观测能力。
  - [x] SubTask 3.1: 定义 legacy CSP 与 Reporting API 输入模型、允许字段、8 KiB 限制和批量上限。
  - [x] SubTask 3.2: 增加 CSP 报告端点，兼容两种 Content-Type，并拒绝不支持的结构与报告类型。
  - [x] SubTask 3.3: 对文档 URL、blocked URL、source file 和 referrer 去除 userinfo、query 与 fragment，
    丢弃 sample、Cookie、Authorization、页面内容和未知字段。
  - [x] SubTask 3.4: 为每条持久化报告生成独立 `trace_id`，复用 `FrontendLogDB` 保存规范化结果。
  - [x] SubTask 3.5: 增加受校验采样配置，以及 Redis 优先、内存降级的独立 IP 限流 action。
  - [x] SubTask 3.6: 增加低基数 outcome 指标；持久化失败只记录 `trace_id`、异常类型和安全计数。

- [x] Task 4: 增加前端 CSP Report-Only 响应头并保持现有强制边界。
  - [x] SubTask 4.1: 提取可测试的强制 CSP 与候选 Report-Only CSP 构建逻辑。
  - [x] SubTask 4.2: 保持现有 `Content-Security-Policy` 值不变，新增更严格候选 `script-src` 的
    `Content-Security-Policy-Report-Only`。
  - [x] SubTask 4.3: 通过受控配置生成 `report-uri`/Reporting API 报告地址，禁止拼接不受信任输入。
  - [x] SubTask 4.4: 保持 API、SSE、登录、字体、图片、frame、base 和 form 来源边界与当前运行需求一致。

- [x] Task 5: 补齐 R9 定向测试、浏览器回归和 CI 门禁。
  - [x] SubTask 5.1: 后端覆盖两种报告格式、Content-Type、大小、批量上限、非法类型和安全响应。
  - [x] SubTask 5.2: 后端覆盖 URL 脱敏、未知字段丢弃、`trace_id`、采样、限流、低基数指标和持久化失败。
  - [x] SubTask 5.3: 前端覆盖双 CSP 头、候选策略、报告地址和强制 CSP 未变化。
  - [x] SubTask 5.4: Playwright 覆盖登录、刷新恢复、退出、SSE 和至少一个 Bearer 写请求，确认
    Report-Only 不阻断业务。
  - [x] SubTask 5.5: Backend CI 增加 CSP 接收契约门禁，Frontend CI 增加双头与浏览器回归门禁。

- [x] Task 6: 执行本地完整验证并修复发现的问题。
  - [x] SubTask 6.1: 运行 R9 后端定向测试、认证/CSRF/SSE 回归、后端全量 pytest 和 Ruff。
  - [x] SubTask 6.2: 运行前端 Vitest、TypeScript、ESLint、production build 和 Playwright。
  - [x] SubTask 6.3: 运行 `git diff --check`，确认无报告、浏览器产物、原始 URL 或敏感数据进入版本控制。
  - [x] SubTask 6.4: 对失败项做最小修复并重新运行受影响门禁。

- [x] Task 7: 维护 R9 发布、状态和运维文档。
  - [x] SubTask 7.1: 更新 `CHANGELOG.md`、README、AGENTS、`.agents/`、当前迭代计划和发布清单。
  - [x] SubTask 7.2: 更新 R5 安全文档，将 S1 标为 R9 工程实现，并保留完整业务周期观测要求。
  - [x] SubTask 7.3: 新增 R9 非生产工程基线记录，包含提交、测试、CI、回滚点和未完成 S2/S3 项。
  - [x] SubTask 7.4: 记录指标与告警输入，明确 CI/本地报告不构成生产 SLO 或强制 CSP 收紧证据。
  - [x] SubTask 7.5: 校验文档链接、测试计数、提交哈希、状态表述和非生产边界。

- [ ] Task 8: 原子提交并推送 R9 实现与最终验证。
  - [x] SubTask 8.1: 检查工作区，只暂存 R9 相关代码、测试、CI、规格和文档。
  - [x] SubTask 8.2: 运行 pre-commit 与最终差异检查，按实现和验证/文档边界创建原子提交。
  - [x] SubTask 8.3: 推送至 `origin/master`，确认本地与远端提交一致。
  - [x] SubTask 8.4: 核对 Backend CI 与 Frontend CI；失败时以独立修复提交处理并重新验证。
  - [ ] SubTask 8.5: 确认临时报告、测试数据库、浏览器产物和日志已清理，最终工作区干净。

- [x] Task 9: 修复独立安全与 CI 审查发现，并重新验证受影响边界。
  - [x] SubTask 9.1: 将同步限流和批量数据库持久化移出异步事件循环，并避免逐条提交。
  - [x] SubTask 9.2: 对 document URL 强制 HTTP(S) 绝对地址，拒绝 NaN/Infinity JSON 常量并补测试。
  - [x] SubTask 9.3: 增加 PostgreSQL CSP 持久化专项或等价真实 PostgreSQL CI 证据。
  - [x] SubTask 9.4: 扩大 Frontend CI 后端路径触发范围，避免相关后端变更跳过浏览器门禁。
  - [x] SubTask 9.5: 补齐并发 401 单飞刷新和 SSE 断线重连回归。
  - [x] SubTask 9.6: 重跑 CSP 定向、认证/SSE、Ruff、前端静态检查和 R9 Playwright。

- [x] Task 10: 修复最终验收发现的 R9 文档状态漂移。
  - [x] SubTask 10.1: 将 README、CHANGELOG、AGENTS、`.agents/`、当前迭代计划、发布清单和
    发布入口中“增强版浏览器/远端 CI 待验证”的过期表述更新为可追溯的成功结果。
  - [x] SubTask 10.2: 在相关事实源中记录 Backend CI run `30739553595`、Frontend CI run
    `30740784839` 和 CI 稳定性修复提交 `c7a721a04f58caa51860be67d870855663186a14`。
  - [x] SubTask 10.3: 保留 R9 未生产部署、完整业务周期观测未完成、S2/S3 未启动以及
    `localStorage` access token 风险未关闭的边界。
  - [x] SubTask 10.4: 全文检索并消除与当前 CI 状态冲突的“待补/待验证”表述，重新校验链接、
    测试计数、提交哈希和 `git diff --check`。

# Task Dependencies

- Task 2 depends on Task 1.
- Task 3 and Task 4 depend on Task 2，二者可并行实施。
- Task 5 depends on Task 3 and Task 4.
- Task 6 depends on Task 5.
- Task 7 depends on Task 6 的最终验证结果。
- Task 8 depends on Task 6 and Task 7.
- Task 9 depends on Task 6，且 Task 7 的最终校验与 Task 8 depend on Task 9.
- Task 10 depends on Task 9，且 Task 7.5、Task 8 和最终 checklist depend on Task 10.
