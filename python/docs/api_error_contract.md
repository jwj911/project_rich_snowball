# API 错误体契约设计文档

> 状态：草案（Draft）  
> 制定日期：2026-05-29  
> 适用范围：所有前后端交互的 HTTP API 错误响应

---

## 1. 现状

当前后端错误响应不统一：

- **FastAPI 自动校验错误**：`{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`
- **路由内主动抛错**：`{"detail": "品种不存在"}` 或 `raise HTTPException(status_code=404, detail=...)`
- **前端处理**：`lib/api.ts` 已支持读取 `error.code`，但后端并非所有错误都输出 `code`。

问题：
- 前端无法可靠地根据错误体做国际化或精确的用户提示。
- 日志排查时缺乏 `request_id`，难以关联前后端链路。

---

## 2. 目标契约（Target Contract）

所有后端错误响应应统一为以下结构：

```json
{
  "code": "RESOURCE_NOT_FOUND",
  "message": "品种不存在",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `code` | `string` | 是 | 机器可读的错误码，全大写 snake_case |
| `message` | `string` | 是 | 人类可读的错误描述（可直接展示给用户） |
| `request_id` | `string` | 是 | 当前请求的 `X-Request-ID`，用于链路追踪 |

### 错误码命名规范

格式：`{DOMAIN}_{REASON}`

| 前缀 | 领域 |
|------|------|
| `AUTH_` | 认证/鉴权 |
| `VALIDATION_` | 参数校验 |
| `RESOURCE_` | 资源操作（CRUD）|
| `RATE_LIMIT_` | 限流 |
| `SERVER_` | 服务端内部错误 |

示例：

| code | HTTP Status | 场景 |
|------|-------------|------|
| `AUTH_UNAUTHORIZED` | 401 | Token 无效或过期 |
| `AUTH_FORBIDDEN` | 403 | 权限不足 |
| `VALIDATION_INVALID_FIELD` | 422 | 字段校验失败（如密码复杂度） |
| `RESOURCE_NOT_FOUND` | 404 | 品种/合约/评论不存在 |
| `RESOURCE_CONFLICT` | 409 | 重复创建（如重复标注） |
| `RATE_LIMIT_EXCEEDED` | 429 | 请求过于频繁 |
| `SERVER_INTERNAL_ERROR` | 500 | 未预期的服务端错误 |

---

## 3. 渐进迁移策略

不一次性全局改造，按以下阶段逐步落地：

### Phase A：新增端点直接采用（立即执行）
- 所有新路由、新端点的错误响应直接输出 `{code, message, request_id}`。

### Phase B：试点路由改造（本轮执行）
- 选一个已有路由作为试点，建议 `auth.py`（错误场景集中，前端消费路径明确）。
- 改造内容：
  1. 引入 `ApiError` 异常类（或直接使用 FastAPI HTTPException + 自定义 handler）。
  2. 将 `auth.py` 中所有 `HTTPException` 替换为带 `code` 的版本。
  3. 在 `main.py` 注册异常 handler，统一包装响应体。

### Phase C：存量路由逐步覆盖（后续迭代）
- 每轮迭代选择 1-2 个路由改造。
- 改造顺序建议：auth → comments → price_levels → varieties → kline/realtime。

### Phase D：FastAPI 自动校验错误统一（最后执行）
- 覆盖 `RequestValidationError` 和 `ValidationError`，将 `detail` 数组转换为统一错误体。

---

## 4. 前端消费约定

`frontend/lib/api.ts` 已支持的扩展：

```typescript
interface ApiError {
  code: string;
  message: string;
  request_id: string;
}

// 错误处理示例
if (error.code === "AUTH_UNAUTHORIZED") {
  redirectToLogin();
} else if (error.code === "RATE_LIMIT_EXCEEDED") {
  showRetryLater(error.message);
} else {
  // 兜底：展示 message
  showToast(error.message);
}
```

前端应遵循：
1. 优先根据 `code` 做分支处理。
2. `message` 作为用户可见的兜底文案。
3. 发生未处理错误时，将 `request_id` 上报到 `POST /api/log/frontend`。

---

## 5. 试点方案（auth.py）

### 5.1 异常类定义

```python
# services/exceptions.py 或 schemas.py

class ApiException(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
```

### 5.2 异常 Handler（main.py）

```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(ApiException)
async def api_exception_handler(request: Request, exc: ApiException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "request_id": request.headers.get("X-Request-ID", ""),
        },
    )
```

### 5.3 auth.py 改造示例

```python
# 改造前
raise HTTPException(status_code=401, detail="用户名或密码错误")

# 改造后
raise ApiException(code="AUTH_INVALID_CREDENTIALS", message="用户名或密码错误", status_code=401)
```

---

## 6. 验收标准

- [ ] 本文档已产出并同步到 AGENTS.md。
- [ ] 至少 1 个试点路由（auth）按新契约输出错误体。
- [ ] 前端 `lib/api.ts` 能正确读取 `code` / `message` / `request_id`。
- [ ] 新增端点的 PR 必须经过错误体契约 review。

---

*最后更新：2026-05-29*
