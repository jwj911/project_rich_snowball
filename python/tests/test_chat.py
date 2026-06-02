"""AI 聊天 API 测试。

覆盖：鉴权、历史记录、消息发送（含 AI 未配置场景）、清空历史。
"""

import pytest
from unittest.mock import AsyncMock, patch


class TestChatAuth:
    def test_list_requires_auth(self, client):
        resp = client.get("/api/chat")
        assert resp.status_code == 401

    def test_create_requires_auth(self, client):
        resp = client.post("/api/chat", json={"content": "hello"})
        assert resp.status_code == 401

    def test_delete_requires_auth(self, client):
        resp = client.delete("/api/chat")
        assert resp.status_code == 401


class TestChatHistory:
    def test_list_empty_history(self, client, auth_headers):
        resp = client.get("/api/chat", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_send_and_list_history(self, client, auth_headers):
        with patch("routers.chat.chat_with_ai", new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = ("这是 AI 回复", {})
            resp = client.post("/api/chat", json={"content": "你好"}, headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["role"] == "assistant"
            assert data["content"] == "这是 AI 回复"

        resp = client.get("/api/chat", headers=auth_headers)
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "你好"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "这是 AI 回复"

    def test_send_empty_content(self, client, auth_headers):
        resp = client.post("/api/chat", json={"content": "  "}, headers=auth_headers)
        assert resp.status_code == 400

    def test_clear_history(self, client, auth_headers):
        with patch("routers.chat.chat_with_ai", new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = ("回复", {})
            client.post("/api/chat", json={"content": "test"}, headers=auth_headers)

        resp = client.delete("/api/chat", headers=auth_headers)
        assert resp.status_code == 204

        resp = client.get("/api/chat", headers=auth_headers)
        assert resp.json() == []

    def test_ai_not_configured(self, client, auth_headers):
        with patch("services.ai_chat.OPENAI_API_KEY", ""):
            resp = client.post("/api/chat", json={"content": "你好"}, headers=auth_headers)
            assert resp.status_code == 200
            data = resp.json()
            assert "尚未配置" in data["content"]

    def test_send_content_too_long(self, client, auth_headers):
        resp = client.post("/api/chat", json={"content": "x" * 4001}, headers=auth_headers)
        assert resp.status_code == 422
