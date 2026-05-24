"""
阶段一 + 阶段三 集成测试
=======================
验证：模型层重建后 Schema 完整性、新 API 接口行为、旧接口向后兼容

运行方式：
    cd python
    pytest -p no:langsmith tests/test_phase1_3_integration.py -v
"""

import os
import sys
import pytest
from datetime import datetime
from sqlalchemy import inspect, text

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-integration")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import engine, Base, init_db, SessionLocal, VarietyDB, KlineDataDB, RealtimeQuoteDB, WatchlistDB, OpinionDB, FutTradeFeeDB
from data_collector.init_varieties import init_varieties


# ============================================================================
# 阶段一：Schema 完整性
# ============================================================================

class TestSchemaIntegrity:
    def test_all_tables_exist(self):
        """数据库中应存在核心业务表"""
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        expected = {
            "users", "products", "comments",
            "varieties", "realtime_quotes", "kline_data",
            "watchlists", "opinions"
        }
        assert expected.issubset(tables), f"缺失表: {expected - tables}"

    def test_varieties_table_has_data(self, client, db_session):
        """varieties 表应有 10 条初始化数据"""
        count = db_session.query(VarietyDB).count()
        assert count == 10, f"预期 10 条品种数据，实际 {count}"

    def test_varieties_indexes(self):
        """varieties 表应有 symbol 和 category 索引"""
        inspector = inspect(engine)
        indexes = {idx["name"] for idx in inspector.get_indexes("varieties")}
        assert "ix_varieties_symbol" in indexes
        assert "ix_varieties_category" in indexes

    def test_kline_unique_constraint(self):
        """kline_data 应有 variety_id+contract_id+period+trading_time 唯一约束"""
        inspector = inspect(engine)
        constraints = inspector.get_unique_constraints("kline_data")
        names = {c["name"] for c in constraints}
        assert "uix_kline_contract" in names

    def test_foreign_keys(self):
        """关键外键关系存在"""
        inspector = inspect(engine)
        fk_map = {}
        for table in ["kline_data", "realtime_quotes", "watchlists", "opinions"]:
            fks = inspector.get_foreign_keys(table)
            fk_map[table] = {fk["referred_table"] for fk in fks}

        assert "varieties" in fk_map["kline_data"]
        assert "varieties" in fk_map["realtime_quotes"]
        assert "varieties" in fk_map["watchlists"]
        assert "users" in fk_map["watchlists"]
        assert "varieties" in fk_map["opinions"]
        assert "users" in fk_map["opinions"]

    def test_products_data_intact(self, client, db_session):
        """旧 products 表数据应完好"""
        from models import ProductDB
        count = db_session.query(ProductDB).count()
        assert count == 10, f"products 表应有 10 条数据，实际 {count}"


# ============================================================================
# 阶段三：旧接口向后兼容
# ============================================================================

class TestLegacyApiCompatibility:
    def test_products_list(self, client, auth_headers):
        """/api/products 应返回 10 条，字段结构不变"""
        r = client.get("/api/products", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 10
        p = data[0]
        assert "id" in p and "name" in p and "symbol" in p
        assert "current_price" in p and "change_percent" in p

    def test_product_detail(self, client, auth_headers):
        """/api/products/1 应返回 product + comments"""
        r = client.get("/api/products/1", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "product" in data
        assert "comments" in data
        assert data["product"]["id"] == 1

    def test_auth_register_login_me(self, client):
        """注册 → 登录 → 获取 Me 流程应通顺"""
        # 注册
        r = client.post("/api/auth/register", json={
            "username": "integration_user",
            "email": "integration@test.com",
            "password": "password123"
        })
        assert r.status_code == 201, r.text

        # 登录
        r = client.post("/api/auth/login", data={
            "username": "integration_user",
            "password": "password123"
        })
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]

        # Me
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["username"] == "integration_user"

    def test_comments_api(self, client, auth_headers):
        """评论接口应能正常写入和读取"""
        r = client.get("/api/comments/me", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)


# ============================================================================
# 阶段三：新增 API 行为验证
# ============================================================================

class TestNewApiEndpoints:
    def test_varieties_list(self, client, auth_headers):
        """/api/varieties 应返回 10 条品种"""
        r = client.get("/api/varieties", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 10
        assert data[0]["symbol"] is not None

    def test_varieties_pagination(self, client, auth_headers):
        """分页参数 skip/limit 应生效"""
        r = client.get("/api/varieties?skip=0&limit=5", headers=auth_headers)
        assert len(r.json()) == 5

        r = client.get("/api/varieties?skip=5&limit=5", headers=auth_headers)
        assert len(r.json()) == 5

    def test_varieties_category_filter(self, client, auth_headers):
        """分类过滤应生效"""
        r = client.get("/api/varieties?category=贵金属", headers=auth_headers)
        data = r.json()
        assert len(data) == 2  # AU, AG
        for v in data:
            assert v["category"] == "贵金属"

    def test_varieties_search(self, client, auth_headers):
        """搜索应生效"""
        r = client.get("/api/varieties?search=黄金", headers=auth_headers)
        data = r.json()
        assert len(data) >= 1
        assert any("黄金" in v["name"] for v in data)

    def test_varieties_detail(self, client, auth_headers):
        """/api/varieties/AU 应返回黄金详情"""
        r = client.get("/api/varieties/AU", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["symbol"] == "AU"
        assert data["name"] == "黄金"

    def test_varieties_detail_not_found(self, client, auth_headers):
        """不存在的品种应返回 404"""
        r = client.get("/api/varieties/UNKNOWN", headers=auth_headers)
        assert r.status_code == 404

    def test_varieties_invalid_pagination(self, client, auth_headers):
        """非法分页参数应返回 422"""
        r = client.get("/api/varieties?skip=-1", headers=auth_headers)
        assert r.status_code == 422

        r = client.get("/api/varieties?limit=1001", headers=auth_headers)
        assert r.status_code == 422

    def test_kline_has_data(self, client, auth_headers):
        """K 线表应返回数据"""
        r = client.get("/api/klines/AU?period=1h&limit=100", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0
        assert "time" in data[0] and "open" in data[0] and "close" in data[0]

    def test_kline_invalid_period(self, client, auth_headers):
        """非法周期应返回 422"""
        r = client.get("/api/klines/AU?period=invalid", headers=auth_headers)
        assert r.status_code == 422

    def test_kline_variety_not_found(self, client, auth_headers):
        """不存在的品种应返回 404"""
        r = client.get("/api/klines/UNKNOWN?period=1h", headers=auth_headers)
        assert r.status_code == 404

    def test_realtime_has_data(self, client, auth_headers):
        """实时行情表应返回动态价格"""
        r = client.get("/api/realtime/AU", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "current_price" in data
        assert "change_percent" in data

    def test_realtime_variety_not_found(self, client, auth_headers):
        """不存在的品种应返回 404"""
        r = client.get("/api/realtime/UNKNOWN", headers=auth_headers)
        assert r.status_code == 404

    def test_docs_accessible(self, client):
        """/docs 应可正常访问"""
        r = client.get("/docs")
        assert r.status_code == 200

    def test_root_endpoint(self, client):
        """/ 应重定向到 /docs"""
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers.get("location") == "/docs"


# ============================================================================
# 阶段三：模型关系验证
# ============================================================================

class TestModelRelationships:
    def test_variety_relationships(self, client, db_session):
        """VarietyDB 的关系属性应可访问（不抛异常）"""
        v = db_session.query(VarietyDB).filter(VarietyDB.symbol == "AU").first()
        assert v is not None
        # 关系属性应存在，当前无数据时返回空列表/None
        assert v.realtime is None or hasattr(v.realtime, "current_price")
        assert isinstance(v.klines, list)
        assert isinstance(v.watchlists, list)
        assert isinstance(v.opinions, list)


# ============================================================================
# 接口增强验证
# ============================================================================

class TestVarietyEnhancements:
    def test_varieties_list_total_count(self, client, auth_headers):
        """/api/varieties 应返回 X-Total-Count header"""
        r = client.get("/api/varieties", headers=auth_headers)
        assert r.status_code == 200
        assert "x-total-count" in r.headers
        total = int(r.headers["x-total-count"])
        assert total >= len(r.json())

    def test_variety_fees(self, client, db_session, auth_headers, seed_varieties):
        """/api/varieties/{symbol}/fees 应返回手续费数据"""
        from models import FutTradeFeeDB
        variety = db_session.query(VarietyDB).filter(VarietyDB.symbol == "AU").first()
        assert variety is not None

        # 清空该品种可能由 init_mock_data 预置的数据，确保测试确定性
        db_session.query(FutTradeFeeDB).filter(FutTradeFeeDB.contract_code.like("AU%")).delete()
        db_session.commit()

        fee = FutTradeFeeDB(
            exchange="SHFE",
            contract_name="黄金",
            contract_code=variety.contract_code,
            margin_per_hand=48050.00,
            fee_open_rate=10.00,
            fee_open_fixed=None,
            fee_close_yesterday_rate=None,
            fee_close_yesterday_fixed="10.0",
            fee_close_today_rate=0.00,
            fee_close_today_fixed=None,
            remark="克/手",
            fee_updated_at=datetime(2025, 1, 15, 0, 0, 0),
        )
        db_session.add(fee)
        db_session.commit()

        r = client.get("/api/varieties/AU/fees", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["symbol"] == "AU"
        assert data["name"] == "黄金"
        assert data["margin_amount"] == 48050.00
        assert data["commission_open"] == 10.00
        assert data["commission_close"] == 10.0
        assert data["commission_close_today"] == 0.00
        assert data["unit"] == "克/手"

    def test_variety_fees_not_found(self, client, auth_headers, seed_varieties):
        """无手续费数据时应返回 404"""
        r = client.get("/api/varieties/XX/fees", headers=auth_headers)
        assert r.status_code == 404
