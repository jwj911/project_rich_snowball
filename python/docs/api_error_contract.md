# API 错误码契约

> 版本：v1
> 生效日期：2026-06-04
> 适用范围：所有 `/api/*` 端点

---

## 错误响应体结构

所有错误响应统一使用以下 JSON 结构：

```json
{
  "code": "BUSINESS_ERROR_CODE",
  "message": "人类可读的错误描述",
  "errors": [],
  "timestamp": "2026-06-04T12:00:00+00:00"
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | string | 是 | 业务错误码，全大写下划线分隔，稳定不变 |
| `message` | string | 是 | 人类可读的错误描述，可随语言/场景微调 |
| `errors` | array | 是 | 字段级校验错误列表，无校验错误时为 `[]` |
| `timestamp` | string | 是 | ISO 8601 格式，服务端生成时间 |

### 校验错误（errors 非空时）

当 `code` 为 `VALIDATION_ERROR` 时，`errors` 包含具体字段错误：

```json
{
  "code": "VALIDATION_ERROR",
  "message": "请求参数校验失败",
  "errors": [
    {"field": "price", "message": "必须大于等于 0"}
  ],
  "timestamp": "2026-06-04T12:00:00+00:00"
}
```

---

## 错误码定义

### 通用 / 系统

| 错误码 | HTTP Status | 说明 | 典型场景 |
|--------|-------------|------|----------|
| `INTERNAL_ERROR` | 500 | 服务器内部错误 | 未捕获异常、数据库连接失败 |
| `VALIDATION_ERROR` | 400 / 422 | 请求参数校验失败 | Pydantic 校验失败、字段缺失/类型错误 |
| `RATE_LIMITED` | 429 | 请求过于频繁 | 限流中间件触发、登录/注册限流 |
| `SERVICE_UNAVAILABLE` | 503 | 服务暂时不可用 | SSE 连接数满、依赖服务超时 |

### 认证 / 授权

| 错误码 | HTTP Status | 说明 | 典型场景 |
|--------|-------------|------|----------|
| `UNAUTHORIZED` | 401 | 未登录或认证无效 | 缺少 token、token 过期/无效 |
| `FORBIDDEN` | 403 | 无权访问 | 普通用户访问 admin 接口、CSRF 拦截 |
| `TOKEN_EXPIRED` | 401 | Token 已过期 | access token 超过有效期 |
| `TOKEN_INVALID` | 401 | Token 无效 | refresh token 不存在/被吊销 |
| `INSUFFICIENT_PERMISSIONS` | 403 | 权限不足 | 非 admin 访问 metrics dashboard |

### 资源

| 错误码 | HTTP Status | 说明 | 典型场景 |
|--------|-------------|------|----------|
| `NOT_FOUND` | 404 | 资源不存在 | 品种/合约/评论/观点 ID 不存在 |
| `ALREADY_EXISTS` | 409 | 资源已存在 | 用户名/邮箱已被注册 |
| `CONFLICT` | 409 | 资源冲突 | 价位标注重复、数据版本冲突 |
| `RESOURCE_GONE` | 410 | 资源已永久删除 | 已删除品种的历史引用 |

### 行情 / 品种

| 错误码 | HTTP Status | 说明 | 典型场景 |
|--------|-------------|------|----------|
| `INVALID_SYMBOL` | 400 | 无效的品种代码 | 空字符串、非法字符 |
| `SYMBOL_NOT_FOUND` | 400 / 404 | 品种不存在 | 查询不存在的品种代码 |
| `CONTRACT_NOT_FOUND` | 404 | 合约不存在 | 指定合约 ID 无效 |
| `REALTIME_DATA_UNAVAILABLE` | 404 | 暂无实时行情数据 | 品种尚未采集到行情 |
| `KLINE_DATA_UNAVAILABLE` | 404 | 暂无 K 线数据 | 新合约尚无历史 K 线 |
| `TOO_MANY_SYMBOLS` | 400 | 查询品种数超过上限 | batch/SSE 请求超过 50 个 |

### 用户 / 业务

| 错误码 | HTTP Status | 说明 | 典型场景 |
|--------|-------------|------|----------|
| `USER_NOT_FOUND` | 404 | 用户不存在 | 按 ID 查询用户不存在 |
| `INVALID_CREDENTIALS` | 401 | 用户名或密码错误 | 登录失败 |
| `PASSWORD_TOO_WEAK` | 422 | 密码强度不足 | 少于 8 位或缺少字母/数字 |
| `USERNAME_TAKEN` | 409 | 用户名已被占用 | 注册重复用户名 |
| `EMAIL_TAKEN` | 409 | 邮箱已被占用 | 注册重复邮箱 |

### 新闻 / 采集

| 错误码 | HTTP Status | 说明 | 典型场景 |
|--------|-------------|------|----------|
| `UNSAFE_URL` | 422 | URL 不安全 | 内网地址、非 http(s) scheme |
| `FETCH_TIMEOUT` | 504 | 抓取超时 | RSS 源 10 秒内无响应 |
| `RSS_PARSE_ERROR` | 502 | RSS 解析失败 | feedparser 无法解析内容 |

### 日志 / 监控

| 错误码 | HTTP Status | 说明 | 典型场景 |
|--------|-------------|------|----------|
| `PAYLOAD_TOO_LARGE` | 422 | Payload 超过大小限制 | 前端日志 payload > 8KB |
| `PAYLOAD_TOO_DEEP` | 422 | Payload 嵌套过深 | 嵌套层级超过 3 层 |
| `PAYLOAD_TOO_MANY_KEYS` | 422 | Payload 键数量过多 | 键数量超过 20 个 |

---

## HTTP Status 与错误码映射

当 router 直接抛出 `HTTPException`（而非 `ServiceError`）时，系统按以下规则将 HTTP status 映射为默认业务错误码：

| HTTP Status | 默认错误码 |
|-------------|-----------|
| 400 | `VALIDATION_ERROR` |
| 401 | `UNAUTHORIZED` |
| 403 | `FORBIDDEN` |
| 404 | `NOT_FOUND` |
| 409 | `CONFLICT` |
| 422 | `VALIDATION_ERROR` |
| 429 | `RATE_LIMITED` |
| 500 | `INTERNAL_ERROR` |
| 503 | `SERVICE_UNAVAILABLE` |

**最佳实践**：router 层优先抛出 `ServiceError` 子类并绑定精确业务码，避免依赖默认映射。

---

## 向后兼容说明

- `code` 字段是**稳定契约**，客户端应基于 `code` 做分支处理，而非 `message`
- `message` 字段**可能随版本微调**，仅用于展示，不作为程序逻辑依据
- 新增错误码时，遵循"只增不改"原则，已有 `code` 值永不变更语义
- HTTP status 与业务码**不是一一对应**关系：同一 HTTP status 可能对应多个业务码

---

## 代码示例

### Python 服务端抛出精确业务码

```python
from errors import ErrorCode
from services.domain.exceptions import NotFoundError, ServiceError, UnauthorizedError

# 精确业务码
raise NotFoundError("暂无实时行情数据", code=ErrorCode.REALTIME_DATA_UNAVAILABLE)

# 自定义 status code + 精确业务码
raise ServiceError(
    message="SSE 连接数已达上限",
    status_code=503,
    code=ErrorCode.SERVICE_UNAVAILABLE,
)
```

### TypeScript 前端基于 code 处理

```typescript
type ErrorCode =
  | "INTERNAL_ERROR"
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "NOT_FOUND"
  | "CONFLICT"
  | "VALIDATION_ERROR"
  | "RATE_LIMITED"
  | "TOO_MANY_SYMBOLS"
  | "REALTIME_DATA_UNAVAILABLE";

function handleApiError(error: { code: ErrorCode; message: string }) {
  switch (error.code) {
    case "UNAUTHORIZED":
    case "TOKEN_EXPIRED":
      redirectToLogin();
      break;
    case "FORBIDDEN":
      showToast("无权访问该资源");
      break;
    case "RATE_LIMITED":
      showToast("请求过于频繁，请稍后再试");
      break;
    case "TOO_MANY_SYMBOLS":
      showToast("一次最多查询 50 个品种");
      break;
    default:
      showToast(error.message || "请求失败");
  }
}
```
