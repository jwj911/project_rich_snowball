
# 期货品种详情页 K线图表与功能优化计划

## 1. 需求分析

根据用户要求，需要实现以下功能：

1. **K线图表展示**
   - 类似 TradingView 的 K线图展示
   - 显示蜡烛图（涨红跌绿
   - 显示成交量柱状图

2. **右侧边栏功能**
   - **支撑/阻力位管理
   - 保证金和手续费

## 2. 技术实现方案

### 2.1 后端修改

**文件**: `python/main.py`

**修改内容**:
- 在 `ProductDB` 增加保证金和手续费字段
- 增加模拟数据补充保证金手续费
- 更新 `ProductResponse`

### 2.2 前端修改

**文件**: `frontend/app/products/[id]/page.tsx`

**修改内容**:
- 重构页面布局调整
- 增加 K线图表组件
- 重构右侧边栏
  - 支撑位/阻力位管理区域
  - 保证金/手续费显示区域

**文件**: `frontend/components/KlineChart.tsx

**新增文件**: K线图表组件

## 3. 实现步骤

1. 更新 `python/main.py`
   - 在 `ProductDB` 增加字段字段字段
   - 模拟数据补充
   - `ProductResponse`

2. `frontend/components/KlineChart.tsx`
   - 创建 K线图表
   - 实现蜡烛图渲染

3. `frontend/app/products/[id]/page.tsx`
   - 引入图表
   - 右侧边栏支撑/阻力管理
   - 保证金/手续费

## 4. 数据库表结构更新

```typescript
// 新增 ProductDB 字段
margin: {
  margin: Float;    // %
  commission: Float;     // 手续费/手
}
```
