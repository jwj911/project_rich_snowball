# Phase 3: Agent 系统进化计划

## 目标

1. **新增 ParameterOptimizerAgent** — 将已有的 `parameter_optimizer.py` 网格搜索能力包装为 Agent，用户可直接在 Chat 中请求参数优化。
2. **新增智能意图路由（Auto 模式）** — 前端新增 `auto` 模式，后端 `IntentRouter` 自动解析用户意图并路由到正确 Agent，无需手动切换模式。
3. **代码成熟、简单直接** — 复用现有架构（`BaseAgent._stream_run`、`AgentExecutor.execute_streaming`），不引入新抽象。

## 变更清单

### 新建文件

| 文件 | 说明 |
|------|------|
| `python/services/agent/parameter_optimizer_agent.py` | ParameterOptimizerAgent 实现 |
| `python/services/agent/intent_router.py` | IntentRouter 意图路由实现 |
| `tests/test_parameter_optimizer_agent.py` | 参数优化 Agent 测试 |
| `tests/test_intent_router.py` | 意图路由测试 |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `python/schemas.py` | AgentType 添加 `PARAMETER_OPTIMIZER = "parameter_optimizer"`；AgentChatRequest `agent_type` pattern 添加 `parameter_optimizer\|auto` |
| `python/routers/agents.py` | `_AGENT_CAPABILITIES` 添加 `parameter_optimizer`；`_build_agent` 添加 `parameter_optimizer` 分支；`agent_chat` 添加 `auto` 模式处理逻辑 |
| `python/services/agent/__init__.py` | 导出 `ParameterOptimizerAgent` 和 `IntentRouter` |
| `frontend/app/chat/page.tsx` | AgentMode 添加 `parameter_optimizer` 和 `auto`；modeLabels/quickPrompts 扩展；`auto` 模式视为 Agent 流式 |
| `frontend/app/agents/page.tsx` | `agentTypeLabels` 扩展 |
| `frontend/lib/api/types.ts` | 如有需要同步类型 |

## 设计细节

### ParameterOptimizerAgent

- 输入：`query`（策略描述，如 "螺纹钢5日上穿20日均线参数优化"）
- 流程：
  1. 用 `StrategyParser` 将策略描述编译为 `StrategyDSL`
  2. 用 `optimize_strategy` 执行网格搜索
  3. 用 `format_optimization_report` 生成 Markdown 报告
- 流式：通过 `_stream_run` 通用辅助，yield thought/action/observation/progress/result 事件
- 步骤：thought → action(解析策略) → action(执行优化) → progress(网格搜索进度) → result

### IntentRouter

- 双层路由：
  1. **规则层**：正则匹配关键词 → 直接返回 Agent 类型（无需 LLM）
  2. **LLM Fallback**：规则未匹配且 LLM 已配置时，让 LLM 从描述中选择 Agent 类型
  3. **最终兜底**：返回 `data`
- 规则优先级：parameter_optimizer > backtest > strategy_compiler > factor_mining > analysis_pipeline > risk_management > tech_analysis > data_quality > data
- 规则关键词：见 `intent_router.py` 中的 `_RULE_MAP`

### Auto 模式后端逻辑

`agent_chat` 中收到 `agent_type == "auto"`：
1. 创建任务（类型记为 `auto`）
2. 调用 `IntentRouter.route(query)` 得到 `target_agent_type`
3. 用 `target_agent_type` 构建 Agent
4. 流式执行并 yield 事件
5. 任务状态中记录 `resolved_agent_type`

### Auto 模式前端行为

- 用户选择 Auto 模式，输入任意查询
- 前端发送 `agent_type: 'auto'` 到 `/api/agents/chat`
- 后端自动路由，前端展示正常流式过程
- 在最终结果展示时，可附带提示 "已自动路由到 XX Agent"

## 测试策略

1. `test_parameter_optimizer_agent.py`：解析策略 → 编译 DSL → 优化执行 → 结果报告完整链路
2. `test_intent_router.py`：各关键词规则匹配 + LLM fallback + 兜底
3. 全量 pytest 回归：`python -m pytest tests -v` 必须 `669 passed, 7 skipped, 0 failed`
4. 前端 `tsc --noEmit` + `lint` 通过

## Git 合并

所有改动完成并测试通过后，合并到 `master` 分支，commit message：`feat(agent): Phase 3 — 参数优化 Agent + 智能意图路由 Auto 模式`
