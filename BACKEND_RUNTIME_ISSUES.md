# 后端运行问题记录

## 2026-05-07：Tushare `ft_mins` 启动限频

### 现象

后端启动执行 `python main.py` 后，应用进入 startup，初始化品种和 mock 数据成功，但随后调度器立即执行实时行情刷新和 K 线同步。当前环境配置为 `DATA_SOURCE=tushare` 时，Tushare `ft_mins` 接口返回频率限制：

```text
抱歉，您访问接口(ft_mins)频率超限(2次/分钟)
```

日志中出现多次：

```text
retry 1/3 ...
retry 2/3 ...
retry 3/3 ...
Max retries exceeded ...
Execution of job "refresh_realtime_quotes" skipped: maximum number of running instances reached (1)
```

### 原因

- `main.py` 在 lifespan startup 中会立即执行一次 `refresh_realtime_quotes()` 和 `sync_daily_kline()`。
- `TushareCollector.fetch_realtime()` 会先通过 `fetch_kline(..., "1m")` 调用 `ft_mins`。
- 项目默认有多个期货品种，启动时对多个 symbol 连续调用 `ft_mins`，超过 Tushare 免费/当前权限接口频率限制。
- 原 `_retry()` 对限频错误仍按普通错误重试，导致日志刷屏并延长启动时间。

### 修复

- `TushareCollector` 增加 Tushare 限频识别。
- 命中限频后不再进行 1/2/4 秒重试，改为进入 65 秒冷却期。
- 调度器 fallback collector 对限频错误只记录首次 warning，后续同类限频降为 debug。
- 开发环境下即使配置 `DATA_SOURCE=tushare` / `akshare` / `auto`，也自动追加 `MockCollector` 作为最后兜底源，保证本地服务可启动、前端可演示。

### 建议

- 本地前后端联调默认使用：

```env
DATA_SOURCE=mock
```

- 需要验证真实 Tushare 数据时再临时切换：

```env
DATA_SOURCE=tushare
TUSHARE_TOKEN=your-token
```

- 若长期使用 Tushare 分钟线，应按接口权限调整采集频率、减少启动即采集的品种数量，或引入本地缓存。

## 2026-05-07：Scheduler 扩展 pipeline 变量未定义

### 现象

切换回 `DATA_SOURCE=mock` 后启动后端，应用在 startup 注册调度任务时失败：

```text
NameError: name '_pipeline_fut_daily' is not defined. Did you mean: '_pipeline_fut_settle'?
```

### 原因

`scheduler.py` 中扩展 pipeline 初始化行被前一段注释和变量赋值写在同一行：

```python
# ... Tushare 支持）_pipeline_fut_daily = None
```

导致 `_pipeline_fut_daily = None` 被当作注释内容，没有真正定义。使用 mock 数据源时 `_tushare_entry` 为空，不会进入后续赋值分支，于是在 `start_scheduler()` 判断 `_pipeline_fut_daily` 时触发 `NameError`。

### 修复

将注释和变量定义拆分为独立两行：

```python
# 扩展 pipeline：期货日线 / 结算 / 周报 / 仓单 / 持仓（仅 Tushare 支持）
_pipeline_fut_daily = None
```

## 2026-05-07：Windows 保留端口导致后端 8000 绑定失败

### 现象

后端 startup 完成后，Uvicorn 绑定 `0.0.0.0:8000` 失败：

```text
[Errno 13] error while attempting to bind on address ('0.0.0.0', 8000): [winerror 10013]
```

### 原因

当前 Windows 环境的 TCP 排除端口段包含：

```text
7933-8032
```

`8000` 正好落在该系统保留区间内，因此普通用户进程无法监听该端口。

### 修复

- 后端开发默认监听 `127.0.0.1:8200`。
- 可通过 `.env` 覆盖：

```env
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8200
```

- 前端默认 API 地址同步改为：

```text
http://127.0.0.1:8200
```

### 启动命令

```powershell
cd C:\Users\34226\.codex\worktrees\577a\project_rich_snowball\python
python main.py
```

启动成功后访问：

```text
http://127.0.0.1:8200/docs
```
