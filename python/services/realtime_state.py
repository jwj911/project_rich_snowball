"""
实时行情数据状态
================
维护全局数据更新时间戳，供 SSE 推送端点判断数据是否有更新。

原理：
- scheduler 每次完成 realtime_quotes 刷新后，调用 mark_realtime_updated()
- SSE 生成器比较上次推送时间与全局更新时间，只在数据变后才查询并推送
- 这样将 SSE 的数据库查询频率从"每 5 秒"降到"每 60 秒 + 新连接时"
"""

from datetime import UTC, datetime

_last_update_time: datetime = datetime.min.replace(tzinfo=UTC)


def mark_realtime_updated() -> None:
    """标记实时行情数据已更新。由 scheduler 在每次刷新完成后调用。"""
    global _last_update_time
    _last_update_time = datetime.now(UTC)


def get_last_update_time() -> datetime:
    """获取最近一次实时行情数据更新时间。"""
    return _last_update_time
