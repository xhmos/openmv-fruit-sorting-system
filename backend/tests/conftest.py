# -*- coding: utf-8 -*-
"""
pytest 公共夹具。

设计原则：测试只打「不该写库」的接口路径（未登录、越权、参数非法、伪造文件），
不改动真实数据；登录只读校验，不新增用户。
"""

import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# 测试期间不要开 reloader，也不要让后台清理线程跑起来
os.environ.setdefault("FLASK_DEBUG", "0")

from app import app as flask_app  # noqa: E402
from extensions import limiter  # noqa: E402


@pytest.fixture(scope="session")
def app():
    flask_app.config.update(TESTING=True)
    # 关掉限流：测试会连续登录/请求，不禁用会被 429 挡住，测的就不是鉴权逻辑了
    limiter.enabled = False
    with flask_app.app_context():
        yield flask_app


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


def login(client, username, password):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


@pytest.fixture(scope="session")
def admin_token(client):
    resp = login(client, "admin", "admin123")
    assert resp.status_code == 200, f"admin 登录失败：{resp.get_json()}"
    return resp.get_json()["data"]["token"]


@pytest.fixture(scope="session")
def operator_token(client):
    resp = login(client, "operator1", "op123456")
    if resp.status_code != 200:
        pytest.skip(f"operator1 不可用（可能被禁用）：{resp.get_json()}")
    return resp.get_json()["data"]["token"]


@pytest.fixture(scope="session")
def auth(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def operator_auth(operator_token):
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture(scope="session")
def device_headers(app):
    return {"X-Device-Token": app.config["DEVICE_TOKEN"]}
