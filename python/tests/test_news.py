"""新闻资讯路由测试
================
验证 /api/news 的源管理、文章查询和抓取行为。
"""

import os
import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-news")
os.environ["ENABLE_SCHEDULER"] = "0"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import NewsArticleDB, NewsSourceDB


class TestNewsSourcesRead:
    def test_list_sources_no_auth(self, client):
        """未登录访问源列表应返回 401。"""
        r = client.get("/api/news/sources")
        assert r.status_code == 401

    def test_list_sources_returns_enabled_only(self, client, auth_headers, db_session):
        """只返回启用的源。"""
        db_session.add(NewsSourceDB(name="启用源", url="http://a.com/rss", is_enabled=True))
        db_session.add(NewsSourceDB(name="禁用源", url="http://b.com/rss", is_enabled=False))
        db_session.commit()

        r = client.get("/api/news/sources", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == "启用源"


class TestNewsArticlesRead:
    def test_list_articles_no_auth(self, client):
        """未登录访问文章列表应返回 401。"""
        r = client.get("/api/news/articles")
        assert r.status_code == 401

    def test_list_articles_with_source_filter(self, client, auth_headers, db_session):
        """按 source_id 筛选应生效。"""
        s1 = NewsSourceDB(name="源1", url="http://a.com/rss")
        s2 = NewsSourceDB(name="源2", url="http://b.com/rss")
        db_session.add_all([s1, s2])
        db_session.flush()
        db_session.add(NewsArticleDB(source_id=s1.id, title="文章A", url="http://a.com/1"))
        db_session.add(NewsArticleDB(source_id=s2.id, title="文章B", url="http://b.com/1"))
        db_session.commit()

        r = client.get(f"/api/news/articles?source_id={s1.id}", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["title"] == "文章A"

    def test_list_articles_with_search(self, client, auth_headers, db_session):
        """标题搜索应生效（不区分大小写）。"""
        s = NewsSourceDB(name="源", url="http://a.com/rss")
        db_session.add(s)
        db_session.flush()
        db_session.add(NewsArticleDB(source_id=s.id, title="螺纹钢期货上涨", url="http://a.com/1"))
        db_session.add(NewsArticleDB(source_id=s.id, title="原油市场波动", url="http://a.com/2"))
        db_session.commit()

        r = client.get("/api/news/articles?q=螺纹钢", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert "螺纹钢" in data[0]["title"]

    def test_list_articles_pagination(self, client, auth_headers, db_session):
        """分页应生效。"""
        s = NewsSourceDB(name="源", url="http://a.com/rss")
        db_session.add(s)
        db_session.flush()
        for i in range(5):
            db_session.add(NewsArticleDB(source_id=s.id, title=f"文章{i}", url=f"http://a.com/{i}"))
        db_session.commit()

        r = client.get("/api/news/articles?skip=2&limit=2", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        assert data[0]["title"] == "文章2"

    def test_list_articles_order_by_published_desc(self, client, auth_headers, db_session):
        """文章应按 published_at 倒序。"""
        s = NewsSourceDB(name="源", url="http://a.com/rss")
        db_session.add(s)
        db_session.flush()
        now = datetime.now(UTC)
        db_session.add(NewsArticleDB(source_id=s.id, title="旧文章", url="http://a.com/1", published_at=now))
        db_session.add(
            NewsArticleDB(
                source_id=s.id, title="新文章", url="http://a.com/2",
                published_at=datetime(2099, 1, 1, tzinfo=UTC),
            )
        )
        db_session.commit()

        r = client.get("/api/news/articles", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data[0]["title"] == "新文章"


class TestNewsSourceAdmin:
    def test_create_source_requires_admin(self, client, auth_headers):
        """普通用户创建源应返回 403。"""
        r = client.post("/api/news/sources", json={"name": "源", "url": "http://a.com/rss"}, headers=auth_headers)
        assert r.status_code == 403

    def test_create_source_admin_success(self, client, admin_headers, db_session):
        """admin 可成功创建源。"""
        r = client.post(
            "/api/news/sources",
            json={"name": "新浪期货", "url": "http://a.com/rss", "category": "期货"},
            headers=admin_headers,
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "新浪期货"
        assert data["category"] == "期货"
        assert data["is_enabled"] is True

    def test_delete_source_requires_admin(self, client, auth_headers, db_session):
        """普通用户删除源应返回 403。"""
        s = NewsSourceDB(name="源", url="http://a.com/rss")
        db_session.add(s)
        db_session.commit()

        r = client.delete(f"/api/news/sources/{s.id}", headers=auth_headers)
        assert r.status_code == 403

    def test_delete_source_admin_success(self, client, admin_headers, db_session):
        """admin 可成功删除源。"""
        s = NewsSourceDB(name="源", url="http://a.com/rss")
        db_session.add(s)
        db_session.commit()

        r = client.delete(f"/api/news/sources/{s.id}", headers=admin_headers)
        assert r.status_code == 204
        assert db_session.get(NewsSourceDB, s.id) is None

    def test_delete_source_not_found(self, client, admin_headers):
        """删除不存在的源应返回 404。"""
        r = client.delete("/api/news/sources/99999", headers=admin_headers)
        assert r.status_code == 404


class TestNewsFetch:
    def test_fetch_trigger_requires_admin(self, client, auth_headers):
        """普通用户触发全量抓取应返回 403。"""
        r = client.post("/api/news/fetch", headers=auth_headers)
        assert r.status_code == 403

    def test_fetch_single_source_requires_admin(self, client, auth_headers, db_session):
        """普通用户触发单源抓取应返回 403。"""
        s = NewsSourceDB(name="源", url="http://a.com/rss")
        db_session.add(s)
        db_session.commit()

        r = client.post(f"/api/news/sources/{s.id}/fetch", headers=auth_headers)
        assert r.status_code == 403

    def test_fetch_single_source_not_found(self, client, admin_headers):
        """抓取不存在的源应返回 404。"""
        r = client.post("/api/news/sources/99999/fetch", headers=admin_headers)
        assert r.status_code == 404

    def test_fetch_single_source_mock(self, client, admin_headers, db_session, monkeypatch):
        """mock feedparser 抓取应成功入库。"""
        s = NewsSourceDB(name="源", url="http://mock/rss", is_enabled=True)
        db_session.add(s)
        db_session.commit()

        fake_entry = MagicMock()
        fake_entry.get.side_effect = lambda k, default="": {
            "title": "Mock 新闻",
            "link": "http://mock/article/1",
            "summary": "摘要内容",
        }.get(k, default)
        fake_entry.__getitem__ = lambda self, k: fake_entry.get(k)

        fake_feed = MagicMock()
        fake_feed.entries = [fake_entry]
        fake_feed.bozo_exception = None

        monkeypatch.setattr("services.news_fetcher.feedparser.parse", lambda url: fake_feed)

        r = client.post(f"/api/news/sources/{s.id}/fetch", headers=admin_headers)
        assert r.status_code == 200
        assert r.json() == 1

        article = db_session.query(NewsArticleDB).filter(NewsArticleDB.source_id == s.id).first()
        assert article is not None
        assert article.title == "Mock 新闻"
        assert article.url == "http://mock/article/1"
        assert article.summary == "摘要内容"

    def test_fetch_deduplicate_by_url(self, client, admin_headers, db_session, monkeypatch):
        """同一 URL 不应重复入库。"""
        s = NewsSourceDB(name="源", url="http://mock/rss", is_enabled=True)
        db_session.add(s)
        db_session.commit()

        fake_entry = MagicMock()
        fake_entry.get.side_effect = lambda k, default="": {
            "title": "Mock 新闻",
            "link": "http://mock/article/1",
        }.get(k, default)

        fake_feed = MagicMock()
        fake_feed.entries = [fake_entry, fake_entry]
        fake_feed.bozo_exception = None

        monkeypatch.setattr("services.news_fetcher.feedparser.parse", lambda url: fake_feed)

        r = client.post(f"/api/news/sources/{s.id}/fetch", headers=admin_headers)
        assert r.status_code == 200
        assert r.json() == 1
