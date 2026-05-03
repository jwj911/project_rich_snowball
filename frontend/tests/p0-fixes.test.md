# 前端 P0 修复测试清单

## 前置依赖
```bash
cd frontend
npm install
```

---

## 测试 4/9：F-P0-04 API_BASE 环境变量

### 验证方法 1：TypeScript 编译
```bash
cd frontend
npx tsc --noEmit
```
**预期结果**：编译通过，无 `api.ts` 相关错误。

### 验证方法 2：构建时注入
```bash
# Windows PowerShell
$env:NEXT_PUBLIC_API_BASE="https://api.example.com"; npm run build
```
**预期结果**：构建成功，且运行时 `API_BASE` 等于 `https://api.example.com`。
（可通过浏览器 DevTools → Network 查看请求地址验证）

### 验证方法 3：默认值回退
不设置环境变量直接启动：
```bash
npm run dev
```
**预期结果**：API 请求仍发送到 `http://localhost:8000`。

---

## 测试 8/9：F-P0-01 Navbar 非法 props

### 验证方法 1：TypeScript 严格检查
```bash
cd frontend
npx tsc --noEmit
```
**预期结果**：`products/[id]/page.tsx` 无类型错误，特别是 `Navbar` 组件无 props 相关报错。

### 验证方法 2：Next.js 构建
```bash
cd frontend
npm run build
```
**预期结果**：构建成功，无 TypeScript 编译错误。

### 验证方法 3：运行时检查
1. 打开浏览器访问 `http://localhost:3000/products/1`
2. 打开 DevTools → Console
**预期结果**：无 React props 类型警告（如 "Received true for non-boolean attribute" 等）。

---

## 测试 9/9：F-P0-02 KlineChart useMemo 响应 props

### 验证方法：运行时行为测试
1. 启动前后端：
   ```bash
   # 终端 1
   cd python && python main.py
   # 终端 2
   cd frontend && npm run dev
   ```
2. 访问 `http://localhost:3000/products/1`
3. 打开 DevTools → React DevTools → Components
4. 找到 `KlineChart` 组件，观察 `data` prop

**预期结果**：
- 首次加载：若 `externalData` 为空数组，`data` 为 mock 数据（基于 450）
- 后续若父组件传入新的 `externalData`（如从 API 获取到真实 K 线数据），`data` 应同步更新为真实数据
- 不会再锁定在初始 mock 数据

### 快速代码验证（无需 React DevTools）
在 `KlineChart.tsx` 中临时添加一行调试用代码：
```typescript
const data = useMemo<KlineData[]>(() => {
    console.log('[KlineChart] useMemo recomputing, externalData length:', externalData.length)
    return externalData.length > 0 ? externalData : generateMockKline(450, 80)
}, [externalData])
```
**预期结果**：当父组件传入新的 `externalData` 时，控制台打印新的长度。
（测试完成后删除这行日志）

---

## 自动化 TypeScript 验证脚本

在 `frontend/package.json` 的 `scripts` 中增加（如果还没有）：
```json
{
  "scripts": {
    "type-check": "tsc --noEmit"
  }
}
```

运行：
```bash
npm run type-check
```

**整体预期**：0 个类型错误。
