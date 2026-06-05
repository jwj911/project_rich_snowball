# 前端安全风险记录

> 记录当前前端已知安全风险和已接受的折中方案。
> 最后更新：2026-06-04

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

### 可选方案（中长期规划）

| 方案 | 描述 | 优先级 |
|------|------|--------|
| 方案 A | access token 改为 HttpOnly cookie，API 请求自动带 cookie | 推荐（未来实施） |
| 方案 B | 短 access token（内存）+ refresh token（HttpOnly cookie），登录后先换 token | 高安全性 |
| 方案 C | 保留 localStorage，在 CSP + XSS 防护上加强投入 | 现状 |

### 后续行动

- [ ] 实施 CSP（Content Security Policy）策略，减少 XSS 入口
- [ ] 定期审查前端依赖，避免引入含已知漏洞的库
- [ ] 在引入第三方脚本（如分析、客服插件）时评估 XSS 风险
