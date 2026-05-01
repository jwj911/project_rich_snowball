# 期货交流社区

一个前后端分离的期货品种数据展示与评论社区应用。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 14 + React 18 + TypeScript + Tailwind CSS |
| 后端 | Python FastAPI + SQLAlchemy + SQLite |
| 认证 | JWT + OAuth2 |

---

## 项目结构

```
project_rich_snowball/
├── frontend/          # 前端：Next.js 应用
│   ├── app/           # App Router 页面
│   ├── components/    # React 组件
│   └── lib/           # API 客户端与工具
│
├── python/            # 后端：FastAPI 应用
│   ├── main.py        # 主入口文件
│   ├── init_data.py   # 数据初始化脚本
│   └── requirements.txt
│
└── src/main/java/     # Java 后端目录（目前仅有空包结构）
```

---

## 前端架构

- **框架**: Next.js 14 (App Router)
- **运行端口**: `localhost:3000`
- **UI 组件库**: `lucide-react`

### 入口文件
- `frontend/app/layout.tsx` — 根布局
- `frontend/app/page.tsx` — 首页（热门品种列表）

### 页面路由
| 路径 | 说明 |
|------|------|
| `/` | 首页，展示热门期货品种卡片 |
| `/products` | 全部品种列表 |
| `/products/[id]` | 品种详情 + 社区评论 |
| `/my-comments` | 当前用户的评论 |

### 核心模块
- `lib/api.ts` — 封装所有后端 API 调用（登录、注册、品种数据、评论）
- `components/Navbar.tsx` — 顶部导航栏
- `components/KlineChart.tsx` — K 线图展示

---

## 后端架构

- **框架**: FastAPI
- **ORM**: SQLAlchemy
- **数据库**: SQLite (`futures_community.db`)
- **运行端口**: `localhost:8000`

### 入口文件
- `python/main.py` — 主入口，启动 Uvicorn 服务器

### 数据模型
- `UserDB` — 用户表（用户名、邮箱、密码哈希）
- `ProductDB` — 期货品种表（名称、代码、价格、涨跌幅、分类等）
- `CommentDB` — 评论表（用户与品种的多对多关联）

### API 接口
| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 服务状态与文档链接 |
| `/api/auth/register` | POST | 用户注册 |
| `/api/auth/login` | POST | 用户登录（OAuth2 密码流） |
| `/api/auth/me` | GET | 获取当前登录用户信息 |
| `/api/products` | GET | 获取全部品种列表 |
| `/api/products/{id}` | GET | 获取品种详情及评论 |
| `/api/comments` | POST | 发表评论（需登录） |
| `/api/comments/user/{username}` | GET | 获取指定用户的评论 |

---

## 环境要求

- **Node.js**: >= 18
- **Python**: >= 3.9
- **npm**: >= 9

---

## 安装与启动

### 1. 克隆或进入项目目录

```bash
cd project_rich_snowball
```

### 2. 启动后端

```bash
cd python

# 创建虚拟环境（推荐）
python -m venv venv

# Windows 激活虚拟环境
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 启动服务
python main.py
```

后端将运行在 `http://localhost:8000`，首次启动会自动初始化模拟数据。

API 文档可访问：
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 3. 启动前端

新开一个终端窗口：

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端将运行在 `http://localhost:3000`。

---

## 开发账号

后端初始化时会自动创建以下测试账号：

| 用户名 | 密码 |
|--------|------|
| `trader001` | `password123` |
| `investor_wang` | `password123` |
| `futures_master` | `password123` |

---

## 注意事项

- 前端与后端通过 CORS 通信，后端已配置允许 `http://localhost:3000` 访问。
- `python/init_data.py` 是一个独立的数据初始化脚本，其引用的数据模型与 `main.py` 略有不同，如需使用请根据当前模型做相应调整。
- `src/main/java/` 目录为预留的 Java 后端模块，目前暂无实质代码。
