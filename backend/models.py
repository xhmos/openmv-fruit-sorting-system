# -*- coding: utf-8 -*-
"""数据库 ORM 模型：user / sort_record / sys_setting。"""

from datetime import datetime

from extensions import bcrypt, db


class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="operator")  # admin / operator
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # 头像：存 uploads 下的相对路径（如 avatars/20261110153000_ab12cd34ef.jpg），空表示没传过
    avatar = db.Column(db.String(200))
    create_time = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, raw_password: str):
        """只允许通过这里写密码，业务代码里不出现明文。"""
        self.password_hash = bcrypt.generate_password_hash(raw_password).decode("utf-8")

    def check_password(self, raw_password: str) -> bool:
        if not self.password_hash:
            return False
        return bcrypt.check_password_hash(self.password_hash, raw_password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "is_active": bool(self.is_active),
            "avatar": self.avatar or "",
            "create_time": self.create_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.create_time else None,
        }


class SortRecord(db.Model):
    __tablename__ = "sort_record"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fruit_type = db.Column(db.String(50), nullable=False, index=True)
    result = db.Column(db.String(20), nullable=False, index=True)  # good / bad
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    area = db.Column(db.Integer, nullable=False, default=0)
    img_path = db.Column(db.String(255), nullable=False, default="")
    create_time = db.Column(db.DateTime, default=datetime.now, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "fruit_type": self.fruit_type,
            "result": self.result,
            "confidence": round(float(self.confidence or 0), 3),
            "area": self.area or 0,
            "img_path": self.img_path or "",
            "create_time": self.create_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.create_time else None,
        }


class SysSetting(db.Model):
    """注意：你库里真实列名是 key_name / value，不是 setting_key / setting_value。"""

    __tablename__ = "sys_setting"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    key_name = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(100), nullable=False, default="")
    remark = db.Column(db.String(100), default="")

    def to_dict(self):
        # 对外仍用 key / value，前端和 OpenMV 都按这两个名字取
        return {
            "key": self.key_name,
            "value": self.value,
            "remark": self.remark or "",
        }
class OperationLog(db.Model):
    """敏感操作审计日志：谁、在什么时候、对什么做了什么。"""

    __tablename__ = "operation_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, index=True)
    username = db.Column(db.String(50), default="")
    action = db.Column(db.String(100), nullable=False)
    target = db.Column(db.String(100), default="")
    detail = db.Column(db.String(255), default="")
    ip = db.Column(db.String(50), default="")
    create_time = db.Column(db.DateTime, default=datetime.now, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "action": self.action,
            "target": self.target,
            "detail": self.detail,
            "ip": self.ip,
            "create_time": self.create_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.create_time else None,
        }


class SecurityEvent(db.Model):
    """
    安全事件：外部「尝试攻击」行为的落地记录。

    和 operation_log 的区别：
        operation_log —— 自己人干了什么（谁改了参数、谁删了记录）
        security_event —— 外面的人想干什么（扫路径、试注入、撞密码、越权）

    写入走独立连接（见 utils/security_guard.py），不参与业务事务，
    所以业务失败也不会把安全日志一起回滚。

    count：同一来源 + 同一类型 + 同一路径在合并窗口内的累计次数。
           扫描器一秒能发几十个请求，逐条落库会把表写爆，
           合并成一条带次数的记录，既保留「次数」又不炸库。
    """

    __tablename__ = "security_event"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ip = db.Column(db.String(50), nullable=False, default="", index=True)
    event_type = db.Column(db.String(32), nullable=False, index=True)
    severity = db.Column(db.String(10), nullable=False, default="low")  # high / medium / low
    method = db.Column(db.String(10), default="")
    path = db.Column(db.String(255), default="")
    status_code = db.Column(db.Integer, default=0)
    username = db.Column(db.String(50), default="")
    user_agent = db.Column(db.String(200), default="")
    detail = db.Column(db.String(255), default="")
    count = db.Column(db.Integer, nullable=False, default=1)
    first_time = db.Column(db.DateTime, default=datetime.now, index=True)
    last_time = db.Column(db.DateTime, default=datetime.now, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "ip": self.ip or "",
            "event_type": self.event_type,
            "severity": self.severity,
            "method": self.method or "",
            "path": self.path or "",
            "status_code": self.status_code or 0,
            "username": self.username or "",
            "user_agent": self.user_agent or "",
            "detail": self.detail or "",
            "count": int(self.count or 1),
            "first_time": self.first_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.first_time else "",
            "last_time": self.last_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.last_time else "",
        }


class SavedDevice(db.Model):
    """
    已保存的设备，类似电脑 WiFi 里的「已保存网络」。

    dev_type：
        camera —— 本地摄像头（target 存设备名，或采集脚本用的序号）
        serial —— 串口设备（target 存 COM7 这种端口号）
        stream —— 网络流（target 存 http://... 的 MJPEG 地址）

    这里只存「怎么连」的参数和最近一次连接结果，
    真正的图像采集仍由 pc_camera_device.py 这类脚本完成——
    后端进程不长期占用摄像头，避免两个程序抢同一个设备。
    """

    __tablename__ = "saved_device"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(64), nullable=False, default="")
    dev_type = db.Column(db.String(16), nullable=False)
    target = db.Column(db.String(128), nullable=False, default="")
    note = db.Column(db.String(128), default="")
    auto_connect = db.Column(db.Boolean, nullable=False, default=True)
    last_status = db.Column(db.String(16), default="")  # ok / fail / ""
    last_message = db.Column(db.String(200), default="")
    last_connect_time = db.Column(db.DateTime)
    create_time = db.Column(db.DateTime, default=datetime.now)

    # 同一类型下不允许重复添加同一目标，避免列表里出现两条 COM7
    __table_args__ = (
        db.UniqueConstraint("dev_type", "target", name="uq_saved_device_type_target"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name or "",
            "dev_type": self.dev_type,
            "target": self.target or "",
            "note": self.note or "",
            "auto_connect": bool(self.auto_connect),
            "last_status": self.last_status or "",
            "last_message": self.last_message or "",
            "last_connect_time": self.last_connect_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.last_connect_time else "",
            "create_time": self.create_time.strftime("%Y-%m-%d %H:%M:%S")
            if self.create_time else "",
        }
