"""将从股票量化库 quantative_tools 抽象出的技术因子导入为系统因子，

并创建几个示例期货策略，最后运行回测验证链路是否通畅。
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# 让脚本可以从 python/ 目录直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session

import config
from models import FactorDefinitionDB, SessionLocal, StrategyDB, UserDB, VarietyDB

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


FACTORS = [
    ("PriceVol20", "price_vol_20", "ts_std(close, 20)", "量价"),
    ("MaDisplaced20", "ma_displaced_20", "close / ts_delay(ts_mean(close, 40), 20) - 1", "动量"),
    ("CRet10", "c_ret_10", "ts_delay(close / ts_delay(close, 20) - 1, 10)", "反转"),
    (
        "MtmHcm20",
        "mtm_hcm_20",
        "ts_mean(close / ts_delay(close, 20) - 1, 20) / (close / ts_mean(close, 20)) - 1",
        "动量",
    ),
    ("Alpha95V2_10", "alpha95_v2_10", "ts_std(close, 10) * ts_std(close, 20) * ts_std(close, 40)", "波动"),
    (
        "Sroc20",
        "sroc_20",
        "(ts_mean(close, 20) - ts_delay(ts_mean(close, 20), 40)) / ts_delay(ts_mean(close, 20), 40)",
        "动量",
    ),
    (
        "MakV220",
        "mak_v2_20",
        "ts_mean((ts_mean(close, 20) / ts_delay(ts_mean(close, 20), 1) - 1) * 1000, 20)",
        "动量",
    ),
    ("Mm20", "mm_20", "ts_mean(close, 20) / ts_mean(close, 100) - 1", "动量"),
    ("Po20", "po_20", "(ts_mean(close, 20) - ts_mean(close, 60)) / ts_mean(close, 60) * 100", "动量"),
    (
        "Trv20",
        "trv_20",
        "ts_mean(100 * (ts_mean(close, 20) - ts_delay(ts_mean(close, 20), 20)) / ts_delay(ts_mean(close, 20), 20), 20)",
        "趋势",
    ),
    (
        "G161",
        "g_161",
        "ts_mean(max_df(max_df(high - low, abs(ts_delay(close, 1) - high)), abs(ts_delay(close, 1) - low)), 12)",
        "波动",
    ),
    (
        "CoppAtr20",
        "copp_atr_20",
        "ts_mean(100 * ((close - ts_delay(close, 20)) / ts_delay(close, 20) + (close - ts_delay(close, 40)) / ts_delay(close, 40)), 20) * (ts_mean(tr(high, low, close), 20) / ts_mean(close, 20))",
        "波动",
    ),
    (
        "Wc20",
        "wc_20",
        "ts_mean((high + low + 2 * close) / 4, 20) / ts_mean((high + low + 2 * close) / 4, 40) - 1",
        "趋势",
    ),
]


SAMPLE_STRATEGIES = [
    {
        "name": "螺纹钢 MtmHcm20 动量策略",
        "symbol": "RB",
        "description": "基于 MtmHcm20 因子的时序动量策略，因子大于 0 做多，小于 0 平仓",
        "timeframe": "1d",
        "direction": "long",
        "entry": {"conditions": [{"indicator": "factor:mtm_hcm_20", "operator": "greater_than", "value": 0.0}], "logic": "and"},
        "exit": {"conditions": [{"indicator": "factor:mtm_hcm_20", "operator": "less_than", "value": 0.0}], "logic": "and"},
    },
    {
        "name": "黄金 G161 波动策略",
        "symbol": "AU",
        "description": "基于 G161 波动因子的策略，因子大于 0 做多，小于 0 平仓",
        "timeframe": "1d",
        "direction": "long",
        "entry": {"conditions": [{"indicator": "factor:g_161", "operator": "greater_than", "value": 0.0}], "logic": "and"},
        "exit": {"conditions": [{"indicator": "factor:g_161", "operator": "less_than", "value": 0.0}], "logic": "and"},
    },
    {
        "name": "原油 PriceVol20 波动策略",
        "symbol": "SC",
        "description": "基于 PriceVol20 波动因子的策略，波动大于 50 做多，小于 20 平仓",
        "timeframe": "1d",
        "direction": "long",
        "entry": {"conditions": [{"indicator": "factor:price_vol_20", "operator": "greater_than", "value": 50.0}], "logic": "and"},
        "exit": {"conditions": [{"indicator": "factor:price_vol_20", "operator": "less_than", "value": 20.0}], "logic": "and"},
    },
]


def _require_secret_key() -> None:
    if not config.SECRET_KEY:
        logger.error("请先设置 SECRET_KEY 环境变量")
        sys.exit(1)


def _get_admin_or_first_user(db: Session) -> UserDB:
    user = db.query(UserDB).filter(UserDB.role == "admin").first()
    if not user:
        user = db.query(UserDB).order_by(UserDB.id.asc()).first()
    if not user:
        logger.error("数据库中没有用户，无法创建策略")
        sys.exit(1)
    return user


def _upsert_factors(db: Session) -> list[FactorDefinitionDB]:
    created_or_updated: list[FactorDefinitionDB] = []
    for name, factor_id, expression, category in FACTORS:
        factor = db.query(FactorDefinitionDB).filter(FactorDefinitionDB.factor_id == factor_id).first()
        if factor:
            factor.name = name
            factor.source_expression = expression
            factor.category = category
            factor.is_active = True
            logger.info("更新因子: %s", factor_id)
        else:
            factor = FactorDefinitionDB(
                user_id=None,
                is_builtin=True,
                package_id="quantative_tools",
                factor_id=factor_id,
                name=name,
                source="quantative_tools",
                category=category,
                source_expression=expression,
                conversion_status="pending",
                is_active=True,
            )
            db.add(factor)
            logger.info("创建因子: %s", factor_id)
        created_or_updated.append(factor)
    db.commit()
    for factor in created_or_updated:
        db.refresh(factor)
    return created_or_updated


def _create_sample_strategies(db: Session, user: UserDB) -> list[StrategyDB]:
    strategies: list[StrategyDB] = []
    for payload in SAMPLE_STRATEGIES:
        symbol = payload["symbol"]
        existing = (
            db.query(StrategyDB)
            .filter(StrategyDB.user_id == user.id, StrategyDB.name == payload["name"])
            .first()
        )
        if existing:
            logger.info("策略已存在，跳过: %s", payload["name"])
            continue

        variety = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
        if not variety:
            logger.warning("品种 %s 不存在，跳过策略 %s", symbol, payload["name"])
            continue

        dsl = {
            "name": payload["name"],
            "description": payload["description"],
            "universe": [symbol],
            "timeframe": payload["timeframe"],
            "direction": payload["direction"],
            "entry": payload["entry"],
            "exit": payload["exit"],
            "risk": {"position_size": {"type": "fixed_lots", "value": 1}},
        }
        strategy = StrategyDB(
            user_id=user.id,
            name=payload["name"],
            description=payload["description"],
            symbol=symbol,
            dsl_json=json.dumps(dsl, ensure_ascii=False),
            timeframe=payload["timeframe"],
            direction=payload["direction"],
            is_active=True,
            is_builtin=True,
        )
        db.add(strategy)
        strategies.append(strategy)
        logger.info("创建策略: %s", payload["name"])
    db.commit()
    for s in strategies:
        db.refresh(s)
    return strategies


def _run_sample_backtests(db: Session) -> None:
    # 延迟导入，避免 services.agent 与 services.backtest 的循环引用
    from services.backtest.service import run_dsl_backtest

    for payload in SAMPLE_STRATEGIES:
        try:
            result = run_dsl_backtest(
                db,
                symbol=payload["symbol"],
                period=payload["timeframe"],
                direction=payload["direction"],
                entry_conditions=payload["entry"]["conditions"],
                exit_conditions=payload["exit"]["conditions"],
                limit=500,
            )
            metrics = result.get("metrics", {})
            logger.info(
                "回测 %s: 交易次数=%s, 总收益=%s%%, 最大回撤=%s%%, score=%s",
                payload["name"],
                metrics.get("trade_count"),
                metrics.get("total_return_pct"),
                metrics.get("max_drawdown_pct"),
                metrics.get("score"),
            )
        except Exception as exc:
            logger.error("回测 %s 失败: %s", payload["name"], exc)


def main() -> None:
    _require_secret_key()
    db = SessionLocal()
    try:
        user = _get_admin_or_first_user(db)
        logger.info("使用用户: id=%s, username=%s", user.id, user.username)

        factors = _upsert_factors(db)
        logger.info("因子导入完成，共 %s 个", len(factors))

        strategies = _create_sample_strategies(db, user)
        logger.info("示例策略创建完成，共 %s 个", len(strategies))

        _run_sample_backtests(db)
        logger.info("示例回测验证完成")
    finally:
        db.close()


if __name__ == "__main__":
    main()
