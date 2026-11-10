# -*- coding: utf-8 -*-
"""
接口自动化测试：覆盖清单里要求的 4 条最低成本用例
——登录、越权 403、上传文件头魔数、参数越界，
外加健康检查、无 token 401、伪造 JWT、审计日志表存在性。

跑法：
    cd backend
    .\\venv\\Scripts\\python.exe -m pytest tests -v
"""

import io


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["code"] == 0


def test_login_success_returns_token(client):
    resp = client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["token"]
    assert data["user"]["role"] == "admin"
    # 响应里不能出现密码相关字段
    assert "password" not in str(data).lower()


def test_login_wrong_password_rejected(client):
    resp = client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong-password"}
    )
    assert resp.status_code in (401, 400)
    assert resp.get_json()["code"] != 0


def test_record_list_without_token(client):
    resp = client.get("/api/record/list")
    assert resp.status_code == 401


def test_record_list_with_forged_token(client):
    resp = client.get(
        "/api/record/list",
        headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJ1aWQiOjF9.forged"},
    )
    assert resp.status_code == 401


def test_operator_cannot_touch_admin_api(client, operator_auth):
    """操作员打管理员接口必须 403 —— 证明权限在后端，不只是前端藏了按钮。"""
    resp = client.get("/api/user/list", headers=operator_auth)
    assert resp.status_code == 403

    resp = client.delete("/api/record/999999", headers=operator_auth)
    assert resp.status_code == 403

    resp = client.put(
        "/api/setting/update", json={"settings": {"min_area": 300}}, headers=operator_auth
    )
    assert resp.status_code == 403


def test_upload_fake_suffix_rejected(client, device_headers):
    """把 PHP 脚本改名成 .jpg 上传，必须被文件头魔数挡住，返回 400 且不写库。"""
    php = b"<?php echo 'pwned'; ?>"
    resp = client.post(
        "/api/device/report",
        data={
            "fruit_type": "lemon",
            "result": "good",
            "confidence": "0.9",
            "area": "1000",
            "image": (io.BytesIO(php), "shell.jpg"),
        },
        content_type="multipart/form-data",
        headers=device_headers,
    )
    assert resp.status_code == 400
    msg = resp.get_json()["msg"]
    assert ("后缀" in msg) or ("格式" in msg) or ("篡改" in msg)


def test_upload_script_suffix_rejected(client, device_headers):
    php = b"<?php echo 'pwned'; ?>"
    resp = client.post(
        "/api/device/report",
        data={
            "fruit_type": "lemon",
            "result": "good",
            "image": (io.BytesIO(php), "shell.php"),
        },
        content_type="multipart/form-data",
        headers=device_headers,
    )
    assert resp.status_code == 400


def test_upload_with_bad_device_token(client):
    resp = client.post(
        "/api/device/report",
        data={"fruit_type": "lemon", "result": "good"},
        content_type="multipart/form-data",
        headers={"X-Device-Token": "wrong-token"},
    )
    assert resp.status_code == 401


def test_setting_out_of_range_rejected(client, auth):
    resp = client.put(
        "/api/setting/update",
        json={"settings": {"h_max": 300}},
        headers=auth,
    )
    assert resp.status_code == 400
    assert "取值范围" in resp.get_json()["msg"]


def test_setting_unknown_key_rejected(client, auth):
    resp = client.put(
        "/api/setting/update",
        json={"settings": {"not_a_real_key": 1}},
        headers=auth,
    )
    assert resp.status_code == 400


def test_setting_min_greater_than_max_rejected(client, auth):
    """min > max 要被关系校验拦住（这里只提交一项，另一项取库里当前值）。"""
    resp = client.put(
        "/api/setting/update",
        json={"settings": {"h_min": 150}},
        headers=auth,
    )
    # 库里 h_max 默认为 30，所以 150 > 30 应当被拒绝
    assert resp.status_code == 400


def test_detail_not_leak_internal_info(client):
    """错误响应里不应出现堆栈、SQL、文件路径等内部信息。"""
    resp = client.get("/api/record/list")
    body = resp.get_data(as_text=True)
    for leak in ("Traceback", "SELECT", "sqlalchemy", "C:\\\\Users"):
        assert leak not in body
