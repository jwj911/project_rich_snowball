"""用户级 LLM 配置测试。"""

from __future__ import annotations

from models import UserLLMConfigDB
from services.agent.llm_client import AgentLLMClient
from services.llm_config import decrypt_api_key, encrypt_api_key, resolve_llm_config


def test_encrypt_api_key_roundtrip_and_not_plaintext():
    encrypted = encrypt_api_key("sk-test-secret")

    assert encrypted != "sk-test-secret"
    assert "sk-test-secret" not in encrypted
    assert decrypt_api_key(encrypted) == "sk-test-secret"


def test_llm_config_api_crud_masks_api_key(client, auth_headers, db_session, monkeypatch):
    import config

    monkeypatch.setattr(config, "OPENAI_API_KEY", "")

    resp = client.put(
        "/api/llm-config",
        json={
            "provider": "openai-compatible",
            "base_url": "https://example.test/v1/",
            "model": "deepseek-chat",
            "api_key": "sk-user-123456",
        },
        headers=auth_headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["uses_system_default"] is False
    assert body["base_url"] == "https://example.test/v1"
    assert body["model"] == "deepseek-chat"
    assert body["has_api_key"] is True
    assert body["api_key_masked"] == "sk-...3456"

    stored = db_session.query(UserLLMConfigDB).one()
    assert stored.api_key_encrypted != "sk-user-123456"
    assert decrypt_api_key(stored.api_key_encrypted) == "sk-user-123456"

    delete_resp = client.delete("/api/llm-config/api-key", headers=auth_headers)
    assert delete_resp.status_code == 204

    resp = client.get("/api/llm-config", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["has_api_key"] is False


def test_user_llm_config_enables_agent_capability(client, auth_headers, db_session, monkeypatch):
    import config

    monkeypatch.setattr(config, "OPENAI_API_KEY", "")

    client.put(
        "/api/llm-config",
        json={
            "provider": "openai-compatible",
            "base_url": "https://provider.test/v1",
            "model": "qwen-plus",
            "api_key": "sk-user-capability",
        },
        headers=auth_headers,
    )

    status_resp = client.get("/api/agents/status", headers=auth_headers)

    assert status_resp.status_code == 200
    data_capability = next(item for item in status_resp.json()["capabilities"] if item["agent_type"] == "data")
    assert status_resp.json()["llm_configured"] is True
    assert data_capability["enabled"] is True


def test_agent_llm_client_resolves_user_config(db_session, seed_user, monkeypatch):
    import config

    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    db_session.add(
        UserLLMConfigDB(
            user_id=seed_user.id,
            provider="openai-compatible",
            base_url="https://provider.test/v1",
            model="custom-model",
            api_key_encrypted=encrypt_api_key("sk-user-client"),
            is_active=True,
        )
    )
    db_session.commit()

    resolved = resolve_llm_config(db_session, seed_user.id)
    client = AgentLLMClient(db_session, seed_user.id)

    assert resolved is not None
    assert resolved.model == "custom-model"
    assert resolved.api_key == "sk-user-client"
    assert resolved.uses_system_default is False
    assert client.is_configured is True
