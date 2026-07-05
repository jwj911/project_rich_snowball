"""自定义因子在策略 DSL 与回测中的集成测试。"""

from __future__ import annotations

import pandas as pd

from models import (
    FactorDefinitionDB,
    FutContractDB,
    KlineDataDB,
    StrategyDB,
    UserDB,
    VarietyDB,
)
from services.agent.strategy_compiler_agent import (
    StrategyValidator,
    _is_valid_indicator,
    _parse_factor_conditions,
)
from services.backtest.service import _inject_factor_columns


def _create_test_variety(db_session, symbol="RB", name="螺纹钢", exchange="SHFE"):
    existing = db_session.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
    if existing:
        return existing
    variety = VarietyDB(
        symbol=symbol,
        contract_code=symbol + "2501",
        name=name,
        exchange=exchange,
        category="黑色系",
        margin_rate=8.0,
        multiplier=10.0,
        commission=0.0001,
        is_active=True,
    )
    db_session.add(variety)
    db_session.commit()
    db_session.refresh(variety)

    contract = FutContractDB(
        ts_code=symbol + "2501.SHF",
        symbol=symbol,
        name=name,
        exchange=exchange,
        fut_code=symbol,
        is_active=True,
    )
    db_session.add(contract)
    db_session.commit()
    return variety


def _seed_klines(db_session, variety_id: int, n: int = 60):
    base = 3500.0
    rows = []
    for i in range(n):
        close = base + (i % 10) * 10 - 45
        open_p = close - 5 + (i % 3) * 5
        high = max(open_p, close) + 10
        low = min(open_p, close) - 10
        volume = 1000 + i * 10
        rows.append(
            KlineDataDB(
                variety_id=variety_id,
                contract_id=1,
                period="1d",
                trading_time=pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                open_price=open_p,
                high_price=high,
                low_price=low,
                close_price=close,
                volume=volume,
            )
        )
    db_session.add_all(rows)
    db_session.commit()


def _create_factor(db_session, user_id: int, name: str, fid: str, expr: str):
    factor = FactorDefinitionDB(
        user_id=user_id,
        is_builtin=False,
        package_id=f"user_{user_id}",
        factor_id=fid,
        name=name,
        source="user",
        category="量价",
        source_expression=expr,
        conversion_status="pending",
        is_active=True,
    )
    db_session.add(factor)
    db_session.commit()
    db_session.refresh(factor)
    return factor


def _get_auth_user(db_session):
    return db_session.query(UserDB).filter(UserDB.username == "integration_tester").first()


class TestFactorIndicatorSupport:
    def test_is_valid_indicator_accepts_factor_prefix(self):
        assert _is_valid_indicator("factor:price_vol_20") is True
        assert _is_valid_indicator("factor:") is False
        assert _is_valid_indicator("sma5") is True

    def test_parse_factor_conditions_explicit_prefix(self):
        query = "螺纹钢 factor:price_vol_20 大于 0.5 做多"
        conds = _parse_factor_conditions(query)
        assert len(conds) == 1
        assert conds[0] == {"indicator": "factor:price_vol_20", "operator": "greater_than", "value": 0.5}

    def test_parse_factor_conditions_named_factor(self):
        query = "当 price_vol_20 因子小于 -0.5 时入场"
        conds = _parse_factor_conditions(query)
        assert len(conds) == 1
        assert conds[0] == {"indicator": "factor:price_vol_20", "operator": "less_than", "value": -0.5}


class TestFactorInjection:
    def test_inject_price_vol_factor(self, db_session, seed_user):
        user = seed_user
        variety = _create_test_variety(db_session)
        _create_factor(db_session, user.id, "PriceVol20", "price_vol_20", "ts_std(close, 20)")
        _seed_klines(db_session, variety.id, n=60)

        df = pd.DataFrame(
            [
                {
                    "time": k.trading_time.isoformat(),
                    "open": float(k.open_price),
                    "high": float(k.high_price),
                    "low": float(k.low_price),
                    "close": float(k.close_price),
                    "volume": k.volume,
                }
                for k in db_session.query(KlineDataDB).filter(KlineDataDB.variety_id == variety.id).all()
            ]
        )

        entry = [{"indicator": "factor:price_vol_20", "operator": "greater_than", "value": 0.0}]
        exit_ = [{"indicator": "factor:price_vol_20", "operator": "less_than", "value": 0.0}]
        df_out = _inject_factor_columns(db_session, df, variety.symbol, entry, exit_)

        assert "factor:price_vol_20" in df_out.columns
        assert df_out["factor:price_vol_20"].notna().sum() > 0


class TestFactorStrategyValidation:
    def test_factor_strategy_passes_validation(self):
        from services.agent.strategy_compiler_agent import StrategyDSL

        dsl = StrategyDSL(
            name="因子策略",
            description="基于自定义因子的策略",
            universe=["RB"],
            timeframe="1d",
            direction="long",
            entry={"conditions": [{"indicator": "factor:price_vol_20", "operator": "greater_than", "value": 0.5}], "logic": "and"},
            exit={"conditions": [{"indicator": "factor:price_vol_20", "operator": "less_than", "value": -0.5}], "logic": "and"},
            risk={"position_size": {"type": "fixed_lots", "value": 1}},
        )
        errors = StrategyValidator.validate(dsl)
        assert errors == []


class TestFactorBacktestIntegration:
    def test_run_backtest_with_multiple_stock_factors(self, db_session, seed_user):
        from services.backtest.service import run_dsl_backtest

        user = seed_user
        variety = _create_test_variety(db_session)
        _seed_klines(db_session, variety.id, n=120)

        # 从股票库抽象出的典型技术因子
        factors = [
            ("PriceVol20", "price_vol_20", "ts_std(close, 20)", "量价"),
            ("MaDisplaced20", "ma_displaced_20", "close / ts_delay(ts_mean(close, 40), 20) - 1", "动量"),
            ("CRet10", "c_ret_10", "ts_delay(close / ts_delay(close, 20) - 1, 10)", "反转"),
            ("MtmHcm20", "mtm_hcm_20", "ts_mean(close / ts_delay(close, 20) - 1, 20) / (close / ts_mean(close, 20)) - 1", "动量"),
            ("G161", "g_161", "ts_mean(max_df(max_df(high - low, abs(ts_delay(close, 1) - high)), abs(ts_delay(close, 1) - low)), 12)", "波动"),
        ]
        for name, fid, expr, _category in factors:
            _create_factor(db_session, user.id, name, fid, expr)

        # 用 MtmHcm20 因子做一个多空策略
        result = run_dsl_backtest(
            db_session,
            symbol=variety.symbol,
            period="1d",
            direction="long",
            entry_conditions=[{"indicator": "factor:mtm_hcm_20", "operator": "greater_than", "value": 0.0}],
            exit_conditions=[{"indicator": "factor:mtm_hcm_20", "operator": "less_than", "value": 0.0}],
            limit=120,
        )

        assert "metrics" in result
        assert "trades" in result
        assert result["metrics"]["trade_count"] >= 0


class TestFactorToStrategyApi:
    def test_create_strategy_from_factor(self, client, auth_headers, db_session):
        user = _get_auth_user(db_session)
        factor = _create_factor(db_session, user.id, "Momentum20", "momentum_20", "close / ts_delay(close, 20) - 1")

        resp = client.post(
            f"/api/strategies/from-factor/{factor.id}",
            json={"symbol": "rb", "direction": "long", "entry_value": 0.0, "exit_value": 0.0},
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "RB"
        assert data["direction"] == "long"

        strategy = db_session.query(StrategyDB).filter(StrategyDB.id == data["id"]).first()
        assert strategy is not None
        assert "factor:momentum_20" in strategy.dsl_json
        assert "factor_definition" in strategy.dsl_json

    def test_create_strategy_from_other_user_factor_forbidden(self, client, auth_headers, db_session, seed_user):
        factor = _create_factor(db_session, seed_user.id, "PrivateFactor", "private_factor", "close - open")

        resp = client.post(
            f"/api/strategies/from-factor/{factor.id}",
            json={"symbol": "RB"},
            headers=auth_headers,
        )

        assert resp.status_code == 403
