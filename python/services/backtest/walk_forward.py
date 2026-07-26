"""Deterministic walk-forward validation for a frozen Strategy DSL.

The service uses chronological windows only. It intentionally labels a frozen
DSL as a stability diagnostic rather than independent model selection: callers
that optimized a strategy over the full history must not present this output as
unseen-data acceptance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from statistics import mean, median
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from services.backtest.service import _load_backtest_data, run_dsl_backtest
from services.backtest.transform_contract import validate_condition_transform


@dataclass(frozen=True, slots=True)
class WalkForwardConfig:
    """Chronological window configuration measured in observed bars."""

    train_bars: int = 120
    test_bars: int = 60
    step_bars: int = 60
    window_mode: str = "expanding"
    min_windows: int = 2

    def validate(self) -> None:
        if self.train_bars < 30:
            raise ValueError("walk-forward train_bars 至少为 30")
        if self.test_bars < 30:
            raise ValueError("walk-forward test_bars 至少为 30")
        if self.step_bars < 1:
            raise ValueError("walk-forward step_bars 必须大于 0")
        if self.window_mode not in {"expanding", "rolling"}:
            raise ValueError("walk-forward window_mode 仅支持 expanding 或 rolling")
        if self.min_windows < 1:
            raise ValueError("walk-forward min_windows 必须大于 0")


@dataclass(frozen=True, slots=True)
class WalkForwardWindow:
    """One non-overlapping train/test boundary in a chronological plan."""

    index: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "test_start": self.test_start.isoformat(),
            "test_end": self.test_end.isoformat(),
        }


def build_walk_forward_windows(
    dates: list[date],
    config: WalkForwardConfig,
) -> list[WalkForwardWindow]:
    """Build chronological expanding or rolling windows from observed dates."""
    config.validate()
    observed_dates = sorted(set(dates))
    windows: list[WalkForwardWindow] = []
    test_start_index = config.train_bars

    while test_start_index + config.test_bars <= len(observed_dates):
        train_start_index = 0 if config.window_mode == "expanding" else test_start_index - config.train_bars
        windows.append(
            WalkForwardWindow(
                index=len(windows) + 1,
                train_start=observed_dates[train_start_index],
                train_end=observed_dates[test_start_index - 1],
                test_start=observed_dates[test_start_index],
                test_end=observed_dates[test_start_index + config.test_bars - 1],
            )
        )
        test_start_index += config.step_bars

    return windows


def run_walk_forward_validation(
    db: Session,
    *,
    symbol: str,
    period: str,
    direction: str,
    entry_conditions: list[dict[str, Any]],
    exit_conditions: list[dict[str, Any]],
    initial_cash: float = 100_000.0,
    quantity: int = 1,
    limit: int = 500,
    custom_columns: dict[str, pd.Series] | None = None,
    risk: dict[str, Any] | None = None,
    engine_mode: str = "legacy",
    data_view: str | None = None,
    contract_code: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    config: WalkForwardConfig | None = None,
) -> dict[str, Any]:
    """Run chronological IS/OOS window backtests and summarize stability.

    The strategy rules are frozen for all windows. This is useful for detecting
    regime sensitivity, but it is not an independent OOS selection procedure
    when a caller chose those rules after observing the complete history.
    """
    active_config = config or WalkForwardConfig()
    active_config.validate()
    _validate_transforms(entry_conditions, exit_conditions)

    report = _empty_report(active_config)
    if period != "1d":
        report["reason"] = "unsupported_period"
        report["warnings"].append("walk-forward 当前仅支持 1d 数据，以保证日期边界与回测窗口一致。")
        return report

    rows, data_source = _load_backtest_data(
        db,
        symbol=symbol,
        period=period,
        limit=limit,
        data_view=data_view,
        contract_code=contract_code,
        start_date=start_date,
        end_date=end_date,
    )
    report["data_source"] = data_source
    report["data_coverage"] = {
        "first_date": data_source.get("first_date"),
        "last_date": data_source.get("last_date"),
        "row_count": int(data_source.get("row_count") or len(rows)),
    }
    report["warnings"].extend(_quality_warnings(data_source))

    observed_dates = _observed_dates(rows)
    windows = build_walk_forward_windows(observed_dates, active_config)
    report["planned_window_count"] = len(windows)
    if len(windows) < active_config.min_windows:
        report["reason"] = "insufficient_windows"
        report["warnings"].append(
            "可构建窗口不足，未将样本外验证视为通过。"
            f"需要至少 {active_config.min_windows} 个窗口，实际 {len(windows)} 个。"
        )
        return report

    for window in windows:
        payload = window.to_dict()
        try:
            train_result = run_dsl_backtest(
                db,
                symbol=symbol,
                period=period,
                direction=direction,
                entry_conditions=entry_conditions,
                exit_conditions=exit_conditions,
                initial_cash=initial_cash,
                quantity=quantity,
                limit=limit,
                custom_columns=custom_columns,
                start_date=window.train_start,
                end_date=window.train_end,
                risk=risk,
                engine_mode=engine_mode,
                data_view=data_view,
                contract_code=contract_code,
            )
            test_result = run_dsl_backtest(
                db,
                symbol=symbol,
                period=period,
                direction=direction,
                entry_conditions=entry_conditions,
                exit_conditions=exit_conditions,
                initial_cash=initial_cash,
                quantity=quantity,
                limit=limit,
                custom_columns=custom_columns,
                start_date=window.test_start,
                end_date=window.test_end,
                risk=risk,
                engine_mode=engine_mode,
                data_view=data_view,
                contract_code=contract_code,
            )
        except (ValueError, KeyError, TypeError) as exc:
            report["windows"].append(
                {
                    **payload,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                }
            )
            continue

        report["windows"].append(
            {
                **payload,
                "status": "completed",
                "in_sample": _result_snapshot(train_result),
                "out_of_sample": _result_snapshot(test_result),
            }
        )

    _finalize_report(report, active_config)
    return report


def _empty_report(config: WalkForwardConfig) -> dict[str, Any]:
    return {
        "status": "not_run",
        "validation_status": "not_run",
        "reason": None,
        "evaluation_mode": "frozen_dsl",
        "independent_oos": False,
        "interpretation": (
            "固定 DSL 在滚动时间窗口上的稳定性诊断；若策略在完整历史上被挑选或调参，不能作为独立样本外验收。"
        ),
        "config": asdict(config),
        "planned_window_count": 0,
        "completed_window_count": 0,
        "failed_window_count": 0,
        "windows": [],
        "summary": None,
        "data_source": {},
        "data_coverage": {},
        "warnings": [],
    }


def _validate_transforms(
    entry_conditions: list[dict[str, Any]],
    exit_conditions: list[dict[str, Any]],
) -> None:
    for group_name, conditions in (("entry", entry_conditions), ("exit", exit_conditions)):
        for index, condition in enumerate(conditions):
            validate_condition_transform(condition, context=f"{group_name}.conditions[{index}]")


def _observed_dates(rows: list[dict[str, Any]]) -> list[date]:
    if not rows:
        return []
    timestamps = pd.to_datetime([row.get("time") for row in rows], format="mixed", errors="coerce")
    return [timestamp.date() for timestamp in timestamps if not pd.isna(timestamp)]


def _quality_warnings(data_source: dict[str, Any]) -> list[str]:
    statuses = sorted({str(status) for status in data_source.get("quality_statuses") or []})
    if not statuses or statuses == ["good"]:
        return []
    return [f"数据质量状态：{', '.join(statuses)}；结果需结合质量检查解释。"]


def _result_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "metrics": result.get("metrics", {}),
        "data_window": result.get("data_window", {}),
        "data_source": {
            "dataset_name": result.get("data_source", {}).get("dataset_name"),
            "data_view": result.get("data_source", {}).get("data_view"),
            "contract_code": result.get("data_source", {}).get("contract_code"),
            "quality_statuses": result.get("data_source", {}).get("quality_statuses", []),
        },
    }


def _finalize_report(report: dict[str, Any], config: WalkForwardConfig) -> None:
    completed = [window for window in report["windows"] if window["status"] == "completed"]
    report["completed_window_count"] = len(completed)
    report["failed_window_count"] = len(report["windows"]) - len(completed)
    if len(completed) < config.min_windows:
        report["status"] = "partial" if completed else "not_run"
        report["validation_status"] = "inconclusive"
        report["reason"] = "completed_windows_below_minimum"
        report["warnings"].append(
            "完成窗口不足，未将样本外验证视为通过。"
            f"需要至少 {config.min_windows} 个完成窗口，实际 {len(completed)} 个。"
        )
        return

    oos_metrics = [window["out_of_sample"]["metrics"] for window in completed]
    is_metrics = [window["in_sample"]["metrics"] for window in completed]
    oos_returns = [float(metrics.get("total_return_pct", 0) or 0) for metrics in oos_metrics]
    oos_sharpes = [float(metrics.get("sharpe", 0) or 0) for metrics in oos_metrics]
    oos_scores = [float(metrics.get("score", 0) or 0) for metrics in oos_metrics]
    is_sharpes = [float(metrics.get("sharpe", 0) or 0) for metrics in is_metrics]
    positive_return_rate = sum(value > 0 for value in oos_returns) / len(oos_returns)
    positive_sharpe_rate = sum(value > 0 for value in oos_sharpes) / len(oos_sharpes)
    consistency = max(
        0.0,
        100.0
        - mean(
            abs(is_value - oos_value)
            for is_value, oos_value in zip(
                is_sharpes,
                oos_sharpes,
                strict=True,
            )
        )
        * 20.0,
    )

    report["summary"] = {
        "oos_total_return_pct_mean": round(mean(oos_returns), 4),
        "oos_total_return_pct_median": round(median(oos_returns), 4),
        "oos_sharpe_mean": round(mean(oos_sharpes), 4),
        "oos_sharpe_median": round(median(oos_sharpes), 4),
        "oos_score_mean": round(mean(oos_scores), 4),
        "positive_oos_return_rate": round(positive_return_rate, 4),
        "positive_oos_sharpe_rate": round(positive_sharpe_rate, 4),
        "is_oos_sharpe_consistency_score": round(consistency, 2),
    }

    if report["failed_window_count"]:
        report["status"] = "partial"
        report["validation_status"] = "inconclusive"
        report["reason"] = "window_execution_failed"
        report["warnings"].append("存在失败窗口，未将 walk-forward 验证判定为通过。")
        return

    report["status"] = "completed"
    if positive_return_rate >= 0.6 and median(oos_sharpes) >= 0:
        report["validation_status"] = "stable"
    else:
        report["validation_status"] = "unstable"
