# 用户设置 API 设计文档

> 文档日期：2026-05-31
> 对应功能：Settings（用户偏好设置）
> 状态：后端已闭环，前端可消费

---

## 一、设计原则

- **扁平字段**：不抽象 key-value 配置表，直接为每个偏好加列。新增偏好时加列即可，查询简单、类型安全。
- **用户级隔离**：每个用户一条记录，`user_id` 唯一索引。
- **自动初始化**：用户注册时自动创建默认偏好，无需前端额外调用。
- **Patch 语义**：`PUT /api/settings` 只更新请求体中提供的字段，未提供的保持原值。
- **如无必要，勿增实体**：没有配置版本、没有配置分组、没有用户级覆盖，保持最小可用。

---

## 二、数据模型

### `user_preferences` 表

| 字段 | 类型 | 约束 | 默认值 | 说明 |
|------|------|------|--------|------|
| id | INTEGER | PK, auto | — | 自增主键 |
| user_id | INTEGER | FK(users.id), NOT NULL, UNIQUE, INDEX | — | 关联用户，级联删除 |
| theme | VARCHAR(20) | NOT NULL | `dark` | 主题：`dark` / `light` / `system` |
| polling_interval_seconds | INTEGER | NOT NULL | `30` | 行情轮询间隔，范围 5~3600 |
| notifications_enabled | BOOLEAN | NOT NULL | `true` | 是否启用通知 |
| language | VARCHAR(10) | NOT NULL | `zh-CN` | 语言代码 |
| created_at | DateTime(tz) | — | now | 创建时间 |
| updated_at | DateTime(tz) | — | now | 更新时间（onupdate） |

---

## 三、API 契约

### `GET /api/settings`

获取当前登录用户的偏好设置。

**请求头：**
```
Authorization: Bearer <access_token>
```

**响应 200：**
```json
{
  "user_id": 1,
  "theme": "dark",
  "polling_interval_seconds": 30,
  "notifications_enabled": true,
  "language": "zh-CN",
  "created_at": "2026-05-31T12:00:00+00:00",
  "updated_at": "2026-05-31T12:00:00+00:00"
}
```

**异常：**
- 401：未登录

---

### `PUT /api/settings`

更新当前登录用户的偏好设置（Patch 语义）。

**请求头：**
```
Authorization: Bearer <access_token>
```

**请求体：**
```json
{
  "theme": "light",
  "polling_interval_seconds": 60
}
```

**规则：**
- 只更新请求体中出现的字段
- `theme` 必须是 `dark` / `light` / `system`
- `polling_interval_seconds` 必须在 5~3600 之间
- 未提供的字段保持原值不变

**响应 200：**
```json
{
  "user_id": 1,
  "theme": "light",
  "polling_interval_seconds": 60,
  "notifications_enabled": true,
  "language": "zh-CN",
  "created_at": "2026-05-31T12:00:00+00:00",
  "updated_at": "2026-05-31T12:05:00+00:00"
}
```

**异常：**
- 401：未登录
- 422：字段校验失败（非法 theme、interval 越界等）

---

## 四、前端消费建议

### 初始化时机

用户登录成功后，调用 `GET /api/settings` 获取偏好，存入全局状态（如 React Context / Zustand）。

### 主题切换

```typescript
// 示例
const updateTheme = async (theme: 'dark' | 'light' | 'system') => {
  await api.put('/settings', { theme })
  // 立即应用主题到 document.documentElement
}
```

### 轮询间隔

```typescript
// 从 settings 中读取 polling_interval_seconds
const interval = settings?.polling_interval_seconds ?? 30
useMarketPolling({ interval: interval * 1000 })
```

### 通知开关

```typescript
// 在需要发送通知的组件中检查
if (settings?.notifications_enabled) {
  // 调用浏览器 Notification API 或自定义 Toast
}
```

---

## 五、测试覆盖

测试文件：`python/tests/test_settings.py`（12 个用例）

| 测试类 | 用例数 | 覆盖点 |
|--------|--------|--------|
| TestSettingsAuth | 2 | 未登录访问 GET/PUT 返回 401 |
| TestSettingsDefaults | 2 | 新用户默认偏好、用户 A/B 隔离 |
| TestSettingsUpdate | 7 | theme/interval/notifications/language 更新、部分更新、非法值拒绝、interval 越界 |
| TestSettingsDbState | 1 | 注册后数据库中偏好记录存在 |

---

## 六、后续扩展方向

如需新增偏好字段，按以下步骤：

1. `models.py` `UserPreferenceDB` 新增列（带默认值）
2. `schemas.py` `UserPreferenceResponse` / `UserPreferenceUpdate` 新增字段
3. `routers/settings.py` `_get_or_create_preference` 无需改动（模型自动处理）
4. 编写 Alembic 迁移：新增列并设置默认值
5. 补测试
6. 更新本文档

---

*文档维护：后端 agent。如有变更请同步更新。*
