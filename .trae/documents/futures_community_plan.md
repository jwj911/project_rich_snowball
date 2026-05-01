
# 期货交流社区页面优化计划

## 一、需求分析

根据用户提供的参考页面和需求，需要实现以下核心功能：

1. **支撑位和阻力位的标注与展示**
   - 在K线图上可视化标记支撑位和阻力位
   - 支持在图表上显示水平线标注
   - 鼠标悬停显示具体价格

2. **走势看法展示**
   - 展示用户对于品种后续走势的观点
   - 支持看多/看空/观望等观点类型
   - 显示观点统计数据

3. **评论功能**
   - 用户可以自由发表评论
   - 评论列表展示
   - 支持查看其他用户观点

## 二、技术实现方案

### 2.1 修改文件

| 文件路径 | 修改内容 |
|---------|---------|
| `python/templates/index.html` | 重写页面布局，添加支撑位/阻力位标注、走势看法展示、评论区 |
| `python/main.py` | 添加观点(Opinion)相关的API接口 |
| `python/init_data.py` | 添加观点数据初始化 |

### 2.2 新增数据库模型

```python
class OpinionDB(Base):
    __tablename__ = "opinion"
    id = Column(Integer, primary_key=True, index=True)
    variety_code = Column(String(20), nullable=False)
    user_id = Column(String(50), nullable=False)
    type = Column(String(20))  # bullish, bearish, neutral
    reason = Column(String(500))
    target_price = Column(Float)
    stop_loss = Column(Float)
    created_at = Column(DateTime, default=datetime.now)
```

### 2.3 新增API接口

| 接口 | 方法 | 功能 |
|-----|------|-----|
| `/api/opinion/{variety_code}` | GET | 获取品种观点列表 |
| `/api/opinion` | POST | 创建新观点 |
| `/api/opinion/stats/{variety_code}` | GET | 获取观点统计数据 |

### 2.4 页面布局调整

1. **顶部导航栏**：品种选择、时间周期切换、价格概览
2. **主图表区域**：K线图 + 支撑位/阻力位标注
3. **右侧面板**：观点统计、走势分析、关注设置
4. **底部评论区**：用户评论列表和发表评论

## 三、风险与注意事项

1. **图表性能**：大量K线数据可能影响渲染性能，需要限制显示数量
2. **数据一致性**：支撑位/阻力位需要与数据库同步
3. **用户体验**：确保交互流畅，避免卡顿

## 四、实施步骤

1. 先更新数据库模型，添加Opinion表
2. 添加相关API接口
3. 初始化测试数据
4. 重写前端页面

---

**计划状态**：待审批

请查看此计划并确认是否继续执行。
