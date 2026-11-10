# -*- coding: utf-8 -*-
"""识别参数配置：网页修改阈值，OpenMV 定时拉取。"""

from flask import Blueprint, g, jsonify, request

from extensions import db
from models import SysSetting
from utils.security import admin_required, device_required, login_required, write_operation_log

setting_bp = Blueprint("setting", __name__)

# 只允许改这些键，值域也在这里定，避免任意写库
SETTING_SPEC = {
    "h_min": (0, 179, "色相最小值"),
    "h_max": (0, 179, "色相最大值"),
    "s_min": (0, 255, "饱和度最小值"),
    "s_max": (0, 255, "饱和度最大值"),
    "v_min": (0, 255, "亮度最小值"),
    "v_max": (0, 255, "亮度最大值"),
    "min_area": (0, 1000000, "最小识别面积"),
}
RELATION_PAIRS = [("h_min", "h_max"), ("s_min", "s_max"), ("v_min", "v_max")]


def _to_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


@setting_bp.get("/list")
@login_required
def list_settings():
    rows = db.session.query(SysSetting).order_by(SysSetting.id.asc()).all()
    items = [
        {
            "key": row.key_name,
            "value": _to_int(row.value) if _to_int(row.value) is not None else row.value,
            "remark": row.remark or SETTING_SPEC.get(row.key_name, ("", "", ""))[2],
        }
        for row in rows
    ]
    return jsonify(
        code=0,
        msg="ok",
        data={"items": items, "map": {row.key_name: row.value for row in rows}},
    )


@setting_bp.put("/update")
@admin_required
def update_settings():
    payload = request.get_json(silent=True) or {}
    incoming = payload.get("settings")
    if not isinstance(incoming, dict) or not incoming:
        return jsonify(code=400, msg="settings 必须是键值对象"), 400

    # 先整体校验，任何一项不合法就整批拒绝，不写半个
    checked = {}
    for key, raw in incoming.items():
        if key not in SETTING_SPEC:
            return jsonify(code=400, msg=f"不支持的参数：{key}"), 400
        low, high, _ = SETTING_SPEC[key]
        value = _to_int(raw)
        if value is None:
            return jsonify(code=400, msg=f"{key} 必须是整数"), 400
        if not (low <= value <= high):
            return jsonify(code=400, msg=f"{key} 取值范围 {low}~{high}"), 400
        checked[key] = value

    current = {row.key_name: _to_int(row.value) for row in db.session.query(SysSetting).all()}
    current.update(checked)

    for low_key, high_key in RELATION_PAIRS:
        low_val = current.get(low_key)
        high_val = current.get(high_key)
        if low_val is not None and high_val is not None and low_val > high_val:
            return jsonify(
                code=400, msg=f"{low_key} 不能大于 {high_key}（当前 {low_val} > {high_val}）"
            ), 400

    for key, value in checked.items():
        row = db.session.query(SysSetting).filter_by(key_name=key).first()
        if row is None:
            row = SysSetting(
                key_name=key,
                value=str(value),
                remark=SETTING_SPEC[key][2],
            )
            db.session.add(row)
        else:
            row.value = str(value)

    write_operation_log("修改识别参数", "sys_setting", str(checked))
    db.session.commit()

    return jsonify(code=0, msg="已保存", data={"updated": checked})


@setting_bp.get("/device")
@device_required
def device_settings():
    """OpenMV 定时拉取：返回扁平的 key -> int 字典。"""
    rows = db.session.query(SysSetting).all()
    result = {}
    for row in rows:
        value = _to_int(row.value)
        result[row.key_name] = value if value is not None else row.value
    return jsonify(code=0, msg="ok", data=result)
