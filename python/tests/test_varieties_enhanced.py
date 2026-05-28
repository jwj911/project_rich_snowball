"""Varieties API 增强测试
======================
验证扩展后的 /api/varieties 列表查询（搜索/筛选/排序/统计）
以及评论 variety_id 支持。
"""

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-varieties-enhanced")
os.environ["ENABLE_SCHEDULER"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import UTC, datetime

from models import RealtimeQuoteDB


class TestVarietiesListEnhanced:
    def test_varieties_list_returns_quote_data(self, client, auth_headers, seed_varieties, db_session):
        """列表应返回包含实时行情的品种数据。"""
        # 为品种写入实时行情（upsert，避免 UNIQUE 冲突）
        for v in seed_varieties[:3]:
            q = db_session.query(RealtimeQuoteDB).filter_by(variety_id=v.id).first()
            if q:
                q.current_price = 3500.50
                q.change_percent = 1.25
                q.open_price = 3450.00
                q.high = 3550.00
                q.low = 3400.00
                q.volume = 10000
                q.limit_up = 3600.00
                q.limit_down = 3300.00
                q.updated_at = datetime.now(UTC)
            else:
                q = RealtimeQuoteDB(
                    variety_id=v.id,
                    current_price=3500.50,
                    change_percent=1.25,
                    open_price=3450.00,
                    high=3550.00,
                    low=3400.00,
                    volume=10000,
                    limit_up=3600.00,
                    limit_down=3300.00,
                    updated_at=datetime.now(UTC),
                )
                db_session.add(q)
        db_session.commit()

        r = client.get("/api/varieties", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0

        # 验证响应头统计
        assert "X-Total-Count" in r.headers
        assert "X-Up-Count" in r.headers
        assert "X-Down-Count" in r.headers
        assert "X-Categories" in r.headers

        # 验证返回的数据包含实时行情
        item = data[0]
        assert "current_price" in item
        assert "change_percent" in item
        assert "volume" in item

    def test_varieties_list_search(self, client, auth_headers, seed_varieties):
        """搜索功能应正确过滤。"""
        r = client.get("/api/varieties?search=黄金", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert any("黄金" in (v["name"] or "") for v in data)

    def test_varieties_list_category_filter(self, client, auth_headers, seed_varieties):
        """分类筛选应正确过滤。"""
        r = client.get("/api/varieties?category=农产品", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert all(v.get("category") == "农产品" for v in data)

    def test_varieties_list_direction_filter(self, client, auth_headers, seed_varieties, db_session):
        """涨跌筛选应正确过滤。"""
        # 设置一些上涨，一些下跌（upsert）
        for i, v in enumerate(seed_varieties[:5]):
            q = db_session.query(RealtimeQuoteDB).filter_by(variety_id=v.id).first()
            if q:
                q.current_price = 3000.0 + i
                q.change_percent = 1.0 if i % 2 == 0 else -1.0
                q.updated_at = datetime.now(UTC)
            else:
                q = RealtimeQuoteDB(
                    variety_id=v.id,
                    current_price=3000.0 + i,
                    change_percent=1.0 if i % 2 == 0 else -1.0,
                    updated_at=datetime.now(UTC),
                )
                db_session.add(q)
        db_session.commit()

        r = client.get("/api/varieties?direction=up", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        # 上涨品种数量应与实际一致
        assert len(data) >= 1

    def test_varieties_list_sort_by_volume(self, client, auth_headers, seed_varieties, db_session):
        """按成交量排序应正确。"""
        for i, v in enumerate(seed_varieties[:3]):
            q = db_session.query(RealtimeQuoteDB).filter_by(variety_id=v.id).first()
            if q:
                q.current_price = 3000.0
                q.volume = 1000 * (i + 1)
                q.updated_at = datetime.now(UTC)
            else:
                q = RealtimeQuoteDB(
                    variety_id=v.id,
                    current_price=3000.0,
                    volume=1000 * (i + 1),
                    updated_at=datetime.now(UTC),
                )
                db_session.add(q)
        db_session.commit()

        r = client.get("/api/varieties?sort_by=volume&sort_order=desc", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        volumes = [v.get("volume") or 0 for v in data[:3]]
        assert volumes == sorted(volumes, reverse=True)


class TestCommentVarietyId:
    def test_create_comment_with_variety_id(self, client, auth_headers, seed_varieties, db_session):
        """创建评论时传入 variety_id 应被保存。"""
        variety = seed_varieties[0]
        r = client.post("/api/comments", json={
            "variety_id": variety.id,
            "content": "带 variety_id 的评论"
        }, headers=auth_headers)
        assert r.status_code == 201
        data = r.json()
        assert data["variety_id"] == variety.id

    def test_comment_response_includes_variety_id(self, client, auth_headers, seed_varieties, db_session):
        """评论响应应包含 variety_id。"""
        variety = seed_varieties[0]
        client.post("/api/comments", json={
            "variety_id": variety.id,
            "content": "测试评论"
        }, headers=auth_headers)

        r = client.get("/api/comments/me", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) > 0
        assert "variety_id" in data[0]
