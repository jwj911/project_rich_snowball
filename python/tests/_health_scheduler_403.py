#!/usr/bin/env python3
"""辅助脚本：验证生产环境下 /health/scheduler 对非受信 IP 返回 403。"""
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)
resp = client.get("/health/scheduler")
print(resp.status_code)
if resp.status_code == 403:
    print("ACCESS_DENIED")
else:
    print(resp.json())
