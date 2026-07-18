"""Job Registry：声明式调度任务注册中心。

设计目标：
- 新增采集任务时，只需在 JOB_CONFIGS 列表中添加条目，无需修改 start_scheduler() 主体。
- 所有任务的 trigger、max_instances、misfire_grace_time 集中管理。
"""

from collections.abc import Callable
from dataclasses import dataclass

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import REALTIME_REFRESH_INTERVAL_SECONDS


@dataclass
class JobConfig:
    """调度任务配置。"""

    id: str
    func: Callable
    trigger: object
    max_instances: int = 1
    coalesce: bool = True
    misfire_grace_time: int = 300


def register_jobs(scheduler, jobs: list[JobConfig]):
    """将 JobConfig 列表注册到 APScheduler 实例。"""
    for cfg in jobs:
        scheduler.add_job(
            cfg.func,
            cfg.trigger,
            id=cfg.id,
            replace_existing=True,
            max_instances=cfg.max_instances,
            coalesce=cfg.coalesce,
            misfire_grace_time=cfg.misfire_grace_time,
        )


def build_job_configs(
    refresh_realtime_quotes_func: Callable,
    sync_daily_kline_func: Callable,
    sync_minute_kline_func: Callable,
    sync_trading_calendar_func: Callable,
    sync_variety_metadata_func: Callable,
    sync_news_func: Callable,
    sync_fut_daily_func: Callable | None = None,
    sync_fut_main_daily_func: Callable | None = None,
    sync_fut_settle_func: Callable | None = None,
    sync_fut_weekly_detail_func: Callable | None = None,
    sync_fut_wsr_func: Callable | None = None,
    sync_fut_holding_func: Callable | None = None,
    sync_fut_price_limit_func: Callable | None = None,
) -> list[JobConfig]:
    """构建所有调度任务配置列表。

    Tushare 扩展任务通过传入非 None 的 func 参数条件注册。
    """
    jobs = [
        JobConfig(
            id="refresh_realtime",
            func=refresh_realtime_quotes_func,
            trigger=IntervalTrigger(seconds=REALTIME_REFRESH_INTERVAL_SECONDS),
            misfire_grace_time=10,
        ),
        JobConfig(
            id="daily_kline",
            func=sync_daily_kline_func,
            trigger=CronTrigger(hour=16, minute=5, timezone="Asia/Shanghai"),
            misfire_grace_time=300,
        ),
        JobConfig(
            id="minute_kline",
            func=sync_minute_kline_func,
            trigger=IntervalTrigger(minutes=15),
            misfire_grace_time=60,
        ),
        JobConfig(
            id="trading_calendar",
            func=sync_trading_calendar_func,
            trigger=CronTrigger(day=1, hour=3, minute=0, timezone="Asia/Shanghai"),
            misfire_grace_time=3600,
        ),
        JobConfig(
            id="variety_metadata",
            func=sync_variety_metadata_func,
            trigger=CronTrigger(hour=2, minute=0, timezone="Asia/Shanghai"),
            misfire_grace_time=3600,
        ),
        JobConfig(
            id="news",
            func=sync_news_func,
            trigger=IntervalTrigger(minutes=30),
            misfire_grace_time=300,
        ),
    ]

    if sync_fut_daily_func:
        jobs.append(
            JobConfig(
                id="fut_daily",
                func=sync_fut_daily_func,
                trigger=CronTrigger(hour=16, minute=10, timezone="Asia/Shanghai"),
                misfire_grace_time=300,
            )
        )
    if sync_fut_main_daily_func:
        jobs.append(
            JobConfig(
                id="fut_main_daily",
                func=sync_fut_main_daily_func,
                trigger=CronTrigger(hour=16, minute=12, timezone="Asia/Shanghai"),
                misfire_grace_time=300,
            )
        )
    if sync_fut_settle_func:
        jobs.append(
            JobConfig(
                id="fut_settle",
                func=sync_fut_settle_func,
                trigger=CronTrigger(hour=16, minute=15, timezone="Asia/Shanghai"),
                misfire_grace_time=300,
            )
        )
    if sync_fut_weekly_detail_func:
        jobs.append(
            JobConfig(
                id="fut_weekly_detail",
                func=sync_fut_weekly_detail_func,
                trigger=CronTrigger(day_of_week="mon", hour=3, minute=0, timezone="Asia/Shanghai"),
                misfire_grace_time=3600,
            )
        )
    if sync_fut_wsr_func:
        jobs.append(
            JobConfig(
                id="fut_wsr",
                func=sync_fut_wsr_func,
                trigger=CronTrigger(hour=16, minute=20, timezone="Asia/Shanghai"),
                misfire_grace_time=300,
            )
        )
    if sync_fut_holding_func:
        jobs.append(
            JobConfig(
                id="fut_holding",
                func=sync_fut_holding_func,
                trigger=CronTrigger(hour=16, minute=25, timezone="Asia/Shanghai"),
                misfire_grace_time=300,
            )
        )
    if sync_fut_price_limit_func:
        jobs.append(
            JobConfig(
                id="fut_price_limit",
                func=sync_fut_price_limit_func,
                trigger=CronTrigger(hour=16, minute=30, timezone="Asia/Shanghai"),
                misfire_grace_time=300,
            )
        )

    return jobs


def build_weekly_evolution_job(
    weekly_evolution_func: Callable | None = None,
) -> JobConfig | None:
    """构建周度策略自动进化任务配置（独立于 build_job_configs，便于按需启用）。

    周六凌晨 3:00（Asia/Shanghai）运行，遍历活跃品种自动执行策略进化。
    misfire_grace_time 设为 2 小时，因为进化可能耗时较长。
    """
    if weekly_evolution_func is None:
        return None
    return JobConfig(
        id="weekly_strategy_evolution",
        func=weekly_evolution_func,
        trigger=CronTrigger(day_of_week="sat", hour=3, minute=7, timezone="Asia/Shanghai"),
        max_instances=1,
        coalesce=True,
        misfire_grace_time=7200,
    )
