"""Production container topology regressions."""

from pathlib import Path

import yaml


def _compose_services() -> dict:
    compose_path = Path(__file__).parents[2] / "docker-compose.yml"
    document = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    return document["services"]


def _environment_map(service: dict) -> dict[str, str]:
    entries = service.get("environment", [])
    return dict(entry.split("=", 1) for entry in entries)


def test_api_and_worker_have_single_scheduler_owner():
    services = _compose_services()
    backend_env = _environment_map(services["backend"])
    worker_env = _environment_map(services["worker"])

    assert backend_env["ENV"] == worker_env["ENV"] == "production"
    assert backend_env["ENABLE_SCHEDULER"] == "0"
    assert worker_env["ENABLE_SCHEDULER"] == "1"
    assert services["worker"]["command"] == ["python", "worker.py"]


def test_api_and_worker_share_required_sse_mode_and_redis():
    services = _compose_services()
    backend_env = _environment_map(services["backend"])
    worker_env = _environment_map(services["worker"])

    required_sse_mode = "${SSE_DEPLOYMENT_MODE:?SSE_DEPLOYMENT_MODE must be set}"
    assert backend_env["SSE_DEPLOYMENT_MODE"] == worker_env["SSE_DEPLOYMENT_MODE"] == required_sse_mode
    assert backend_env["REDIS_URL"] == worker_env["REDIS_URL"] == "redis://redis:6379/0"


def test_production_secrets_cors_and_data_source_are_required():
    services = _compose_services()
    backend_env = _environment_map(services["backend"])
    worker_env = _environment_map(services["worker"])

    assert backend_env["SECRET_KEY"] == "${SECRET_KEY:?SECRET_KEY must be set}"
    assert backend_env["CORS_ORIGINS"] == "${CORS_ORIGINS:?CORS_ORIGINS must be set}"
    assert backend_env["DATA_SOURCE"] == "${DATA_SOURCE:?DATA_SOURCE must be set}"
    assert worker_env["SECRET_KEY"] == "${SECRET_KEY:?SECRET_KEY must be set}"
    assert worker_env["DATA_SOURCE"] == "${DATA_SOURCE:?DATA_SOURCE must be set}"
