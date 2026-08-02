# 前端安全风险记录

> 记录当前前端已知安全风险和已接受的折中方案。
> 最后更新：2026-08-02（Post-R9 规划，R10 待立项）

---

## RISK-001：Access Token 存储于 localStorage

### 风险描述

`lib/api/auth.ts` 将 access token 存储在 `localStorage`（key: `futures_access_token`）。

- **攻击面**：若未来引入 XSS 漏洞，恶意脚本可直接读取 localStorage 中的 token
- **影响范围**：攻击者可窃取 token 并冒充用户调用 API
- **当前缓解**：refresh token 已使用 HttpOnly cookie（后端实现），access token 有效期较短

### 评估结论

**当前阶段接受此风险。** 原因：

1. 本项目为期货社区内部工作台，非面向公众的金融交易系统
2. 短期内（Sprint 2 期间）迁移到 HttpOnly cookie 需要同步修改后端认证中间件和 SSE 连接逻辑，成本较高
3. refresh token 已采用 HttpOnly cookie，即使 access token 泄露，攻击窗口受限于 token 有效期

### 当前约束

- 写请求目前必须使用 `Authorization: Bearer`，不接受 access cookie 回退；直接改为
  HttpOnly cookie 会扩大 CSRF 攻击面。
- EventSource 无法设置 Bearer header，因此 SSE 使用 HttpOnly `access_token` cookie。
- refresh 轮换时必须同步轮换 access cookie；logout 必须清理两种 cookie，避免 SSE 保留过期会话。

### 分阶段迁移

1. **R10（evidence-only，待立项）**：只对 R9 已脱敏记录做有界只读归类并生成 S2 准入
   报告，不修改 CSP；只有本地或 CI synthetic 流量时必须判定 `insufficient_evidence`。
2. **R11（operator gate）**：只有具备真实目标环境、凭据、发布窗口、发布/回滚负责人和
   发布清单，才部署 S1 并完成至少一个真实完整业务周期观测。
3. **R12（S2）**：R10/R11 证据完整、无未知违规并经人工批准后，才使用 nonce/hash 收紧
   `script-src`，并验证 Next runtime、图表、登录、API、SSE 和详情页写操作。
4. **R13（S3）**：R12 稳定退出后才将 access token 收敛到内存，使用 HttpOnly refresh
   cookie 恢复会话；POST/PUT/PATCH/DELETE 继续要求 `Authorization: Bearer`。
5. cookie-only 写请求属于后续 S4，只有服务端具备可验证的 CSRF token/origin 策略后才评审，
   不属于 R13。

当前迁移门槛、停止条件和回退边界见
[`docs/iteration_plan_20260802_post_r9.md`](../../docs/iteration_plan_20260802_post_r9.md)；
R5 历史设计见
[`docs/r5_frontend_quality_observability.md`](../../docs/r5_frontend_quality_observability.md)。
