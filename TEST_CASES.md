# 期货交流社区 — P0 修复测试用例文档

> 版本：v1.0  
> 日期：2026-05-01  
> 范围：9 个 P0 级别修复的回归验证  
> 状态：待执行

---

## 一、测试环境准备

### 1.1 后端环境

```bash
cd python

# 1. 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 2. 安装依赖
pip install -r requirements.txt

# 3. 安装测试依赖
pip install pytest httpx

# 4. 创建测试环境变量文件
echo "SECRET_KEY=test-secret-key-for-testing-only" > .env
```

### 1.2 前端环境

```bash
cd frontend
npm install
```

### 1.3 测试数据准备

后端启动后会自动初始化 SQLite 数据库（`python/futures_community.db`）和模拟数据。  
测试前建议删除旧数据库，确保测试在干净环境中运行：

```bash
cd python
del futures_community.db        # Windows
# rm futures_community.db      # macOS/Linux
python main.py
```

---

## 二、测试范围与策略

| 编号 | 修复项 | 优先级 | 测试类型 | 自动化程度 |
|------|--------|--------|----------|------------|
| B-P0-01 | 硬编码 SECRET_KEY | P0 | 安全/配置 | 自动化（pytest） |
| B-P0-02 | SHA256 → bcrypt | P0 | 安全 | 自动化（pytest） |
| B-P0-06 | 评论 XSS + 长度限制 | P0 | 安全/输入校验 | 自动化（pytest） |
| B-P0-08 | 裸 except 吞异常 | P0 | 健壮性 | 自动化（pytest） |
| B-P0-09 | 模块级 create_all | P0 | 架构/启动 | 自动化（pytest） |
| B-P0-07 | init_data.py 连接泄漏 | P0 | 资源管理 | 自动化（pytest，条件skip） |
| F-P0-04 | API_BASE 硬编码 | P0 | 配置 | 半自动化（编译+手动） |
| F-P0-01 | Navbar 非法 props | P0 | 代码质量 | 半自动化（编译+手动） |
| F-P0-02 | KlineChart useMemo | P0 | 功能 | 手动（运行时验证） |

---

## 三、后端测试用例（pytest）

### 运行命令

```bash
cd python
SECRET_KEY=test-secret-key pytest tests/test_p0_fixes.py -v
```

### TC-B-001：SECRET_KEY 未设置时启动失败

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-B-001 |
| **关联修复** | B-P0-01 |
| **测试目的** | 验证未设置 SECRET_KEY 时，应用启动会立即失败 |
| **前置条件** | 环境变量 `SECRET_KEY` 不存在 |
| **操作步骤** | 1. 清除环境变量 `SECRET_KEY`<br>2. 执行 `python -c "import main"` |
| **预期结果** | 进程退出码非 0，stderr 包含 `"SECRET_KEY environment variable is not set"` |
| **通过标准** | 抛出 `ValueError`，不静默使用硬编码密钥 |
| **自动化脚本** | `test_secret_key_missing_raises_error` |

### TC-B-002：SECRET_KEY 从环境变量正确读取

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-B-002 |
| **关联修复** | B-P0-01 |
| **测试目的** | 验证 SECRET_KEY 正确从 `.env` 或环境变量读取 |
| **前置条件** | 已设置 `SECRET_KEY=test-secret-key-for-pytest` |
| **操作步骤** | 1. 导入 `main` 模块<br>2. 读取 `main.SECRET_KEY` |
| **预期结果** | `main.SECRET_KEY == "test-secret-key-for-pytest"` |
| **通过标准** | 值与环境变量一致 |
| **自动化脚本** | `test_secret_key_from_env` |

---

### TC-B-003：bcrypt 生成随机盐（同密码哈希不同）

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-B-003 |
| **关联修复** | B-P0-02 |
| **测试目的** | 验证 bcrypt 使用随机盐，相同明文两次哈希结果不同 |
| **前置条件** | `passlib[bcrypt]` 已安装 |
| **操作步骤** | 1. 调用 `hash_password("password123")` 两次<br>2. 比较两个哈希值 |
| **预期结果** | 两次结果不同，且均以 `$2b$` 开头 |
| **通过标准** | `h1 != h2` 且符合 bcrypt 格式 |
| **自动化脚本** | `test_hash_password_generates_bcrypt` |

### TC-B-004：bcrypt 正确密码验证通过

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-B-004 |
| **关联修复** | B-P0-02 |
| **测试目的** | 验证正确密码可验证通过 |
| **操作步骤** | 1. `h = hash_password("mypassword")`<br>2. `verify_password("mypassword", h)` |
| **预期结果** | 返回 `True` |
| **通过标准** | 验证成功 |
| **自动化脚本** | `test_verify_password_correct` |

### TC-B-005：bcrypt 错误密码验证失败

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-B-005 |
| **关联修复** | B-P0-02 |
| **测试目的** | 验证错误密码无法通过验证 |
| **操作步骤** | 1. `h = hash_password("mypassword")`<br>2. `verify_password("wrongpassword", h)` |
| **预期结果** | 返回 `False` |
| **通过标准** | 验证失败，不会误通过 |
| **自动化脚本** | `test_verify_password_incorrect` |

---

### TC-B-006：评论内容超过 2000 字符被拒绝

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-B-006 |
| **关联修复** | B-P0-06 |
| **测试目的** | 验证超长评论被 Pydantic 拒绝 |
| **操作步骤** | 1. 构造 `CommentCreate(product_id=1, content="x" * 2001)`<br>2. 或 POST `/api/comments` 带 2001 字符内容 |
| **预期结果** | HTTP 422 / `ValidationError`，提示 `max_length` 或 `String should have at most 2000 characters` |
| **通过标准** | 服务端拒绝入库，不存入数据库 |
| **自动化脚本** | `test_comment_content_max_length` |

### TC-B-007：评论内容为空被拒绝

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-B-007 |
| **关联修复** | B-P0-06 |
| **测试目的** | 验证空评论被 Pydantic 拒绝 |
| **操作步骤** | `CommentCreate(product_id=1, content="")` |
| **预期结果** | HTTP 422 / `ValidationError`，提示 `min_length` 或 `String should have at least 1 character` |
| **通过标准** | 服务端拒绝入库 |
| **自动化脚本** | `test_comment_content_min_length` |

### TC-B-008：评论 HTML 标签被转义

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-B-008 |
| **关联修复** | B-P0-06 |
| **测试目的** | 验证 XSS 攻击载荷被 `html.escape` 转义 |
| **操作步骤** | `CommentCreate(product_id=1, content='<script>alert("xss")</script>')` |
| **预期结果** | `comment.content` 中 `<script>` 变为 `&lt;script&gt;` |
| **通过标准** | 原始 HTML 标签不存在于返回内容中，前端渲染时不会执行脚本 |
| **自动化脚本** | `test_comment_content_xss_escaped` |

### TC-B-009：评论首尾空白被去除

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-B-009 |
| **关联修复** | B-P0-06 |
| **测试目的** | 验证首尾空白被 strip |
| **操作步骤** | `CommentCreate(product_id=1, content="  hello world  ")` |
| **预期结果** | `comment.content == "hello world"` |
| **通过标准** | 无首尾空格 |
| **自动化脚本** | `test_comment_content_strips_whitespace` |

---

### TC-B-010：过期 JWT 不抛异常，返回 None

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-B-010 |
| **关联修复** | B-P0-08 |
| **测试目的** | 验证过期 token 被精确捕获，不吞异常，记录日志 |
| **前置条件** | 已创建过期 token（exp 设为过去时间） |
| **操作步骤** | `get_current_user(expired_token, db)` |
| **预期结果** | 返回 `None`，控制台/日志有 `JWT decode failed` 警告，无未捕获异常 |
| **通过标准** | 不抛异常，不导致 500 错误，返回 None 后上游给出 401 |
| **自动化脚本** | `test_get_current_user_with_expired_token` |

### TC-B-011：无效 JWT 不抛异常，返回 None

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-B-011 |
| **关联修复** | B-P0-08 |
| **测试目的** | 验证格式错误的 token 被优雅处理 |
| **操作步骤** | `get_current_user("totally.invalid.token", db)` |
| **预期结果** | 返回 `None`，无未捕获异常 |
| **通过标准** | 同上 |
| **自动化脚本** | `test_get_current_user_with_invalid_token` |

---

### TC-B-012：导入 main 模块不自动创建表

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-B-012 |
| **关联修复** | B-P0-09 |
| **测试目的** | 验证 `Base.metadata.create_all` 已封装为 `init_db()` 函数 |
| **操作步骤** | 1. `import main`<br>2. 检查 `main.init_db` 是否为 callable |
| **预期结果** | `init_db` 是函数，导入时不自动执行 |
| **通过标准** | 导入无副作用，显式调用 `init_db()` 才建表 |
| **自动化脚本** | `test_import_does_not_call_create_all` |

---

### TC-B-013：init_data.py 上下文管理器正确关闭连接

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-B-013 |
| **关联修复** | B-P0-07 |
| **测试目的** | 验证 `get_db_session()` 正确 yield 和关闭 |
| **前置条件** | `init_data.py` 模型与 `main.py` 兼容（当前暂不兼容，测试自动 skip） |
| **操作步骤** | `with get_db_session() as db:` 执行 `SELECT 1` |
| **预期结果** | db 可用，退出 with 后连接关闭 |
| **通过标准** | 无连接泄漏，无 SQLite 线程安全错误 |
| **自动化脚本** | `test_get_db_session_closes_connection`（条件 skip） |

---

### TC-B-014：端到端 — 注册登录发评论全流程

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-B-014 |
| **关联修复** | B-P0-02 + B-P0-06 综合验证 |
| **测试目的** | 验证注册→登录→发评论全流程，bcrypt 和 XSS 过滤同时生效 |
| **前置条件** | 后端已启动，数据库已初始化 |
| **操作步骤** | 1. POST `/api/auth/register` 注册用户<br>2. POST `/api/auth/login` 获取 token<br>3. GET `/api/auth/me` 验证 token<br>4. POST `/api/comments` 带 HTML 内容<br>5. POST `/api/comments` 带 2001 字符内容 |
| **预期结果** | 注册/登录/me 均 200；HTML 评论返回转义后内容；超长评论返回 422 |
| **通过标准** | 全流程通顺，安全过滤生效 |
| **自动化脚本** | `test_register_and_login_flow` |

---

## 四、前端测试用例（手动 + 编译验证）

### TC-F-001：API_BASE 支持环境变量注入

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-F-001 |
| **关联修复** | F-P0-04 |
| **测试目的** | 验证 `API_BASE` 从 `NEXT_PUBLIC_API_BASE` 读取 |
| **操作步骤** | 1. `npx tsc --noEmit` 检查编译<br>2. `NEXT_PUBLIC_API_BASE=https://api.example.com npm run build` 检查构建<br>3. 运行时抓包验证请求地址 |
| **预期结果** | TS 编译通过；构建成功；未设置时回退到 `http://localhost:8000` |
| **通过标准** | 可配置，无硬编码 localhost 写死问题 |

### TC-F-002：Navbar 无非法 props，TypeScript 编译通过

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-F-002 |
| **关联修复** | F-P0-01 |
| **测试目的** | 验证 `products/[id]/page.tsx` 中 Navbar 不传未定义 props |
| **操作步骤** | 1. `npx tsc --noEmit`<br>2. `npm run build`<br>3. 浏览器访问 `/products/1`，DevTools Console 无 React 警告 |
| **预期结果** | 0 个 TS 错误，构建成功，运行时无 props 警告 |
| **通过标准** | 与 `Navbar.tsx` 无参签名一致 |

### TC-F-003：KlineChart 响应外部数据变化

| 项目 | 内容 |
|------|------|
| **用例编号** | TC-F-003 |
| **关联修复** | F-P0-02 |
| **测试目的** | 验证 `useMemo` 使图表数据随 `externalData` 更新 |
| **操作步骤** | 1. 启动前后端<br>2. 访问 `/products/1`<br>3. React DevTools 观察 `KlineChart` 的 `data`<br>4.（可选）临时在 `KlineChart.tsx` 加 `console.log` 观察 useMemo 重计算 |
| **预期结果** | 父组件传入新 `externalData` 时，`data` 同步更新，不再锁定初始 mock |
| **通过标准** | 数据绑定正确，props 变化可响应 |

---

## 五、测试执行记录模板

执行测试后，请在下表记录结果：

| 用例编号 | 执行人 | 执行时间 | 结果 | 备注 |
|----------|--------|----------|------|------|
| TC-B-001 | | | □通过 □失败 □跳过 | |
| TC-B-002 | | | □通过 □失败 □跳过 | |
| TC-B-003 | | | □通过 □失败 □跳过 | |
| TC-B-004 | | | □通过 □失败 □跳过 | |
| TC-B-005 | | | □通过 □失败 □跳过 | |
| TC-B-006 | | | □通过 □失败 □跳过 | |
| TC-B-007 | | | □通过 □失败 □跳过 | |
| TC-B-008 | | | □通过 □失败 □跳过 | |
| TC-B-009 | | | □通过 □失败 □跳过 | |
| TC-B-010 | | | □通过 □失败 □跳过 | |
| TC-B-011 | | | □通过 □失败 □跳过 | |
| TC-B-012 | | | □通过 □失败 □跳过 | |
| TC-B-013 | | | □通过 □失败 □跳过 | |
| TC-B-014 | | | □通过 □失败 □跳过 | |
| TC-F-001 | | | □通过 □失败 □跳过 | |
| TC-F-002 | | | □通过 □失败 □跳过 | |
| TC-F-003 | | | □通过 □失败 □跳过 | |

---

## 六、缺陷记录模板

若测试失败，请按以下格式记录：

```markdown
### 缺陷编号：DEF-001
- **关联用例**：TC-B-00X
- **严重级别**：□致命 □严重 □一般 □轻微
- **问题描述**：
- **复现步骤**：
- **预期结果**：
- **实际结果**：
- **截图/日志**：
- **修复建议**：
```

---

> **提示**：后端 pytest 用例运行命令  
> `cd python && SECRET_KEY=test-secret-key pytest tests/test_p0_fixes.py -v`
