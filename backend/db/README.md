# 数据库变更规范

## 现状

项目用 `db.create_all()` 建表，它**只创建不存在的表**，对已有表的结构改动（加字段、改类型）完全无感。
所以「在 models.py 里加一列」不会自动生效，必须手工执行 SQL。

## 加字段 / 改字段的标准三步

以「给 sort_record 加一个 batch_no 批次号」为例：

**第一步：先改表（数据库里先有列）**

```sql
ALTER TABLE sort_record
  ADD COLUMN batch_no VARCHAR(40) NOT NULL DEFAULT '' COMMENT '分拣批次号'
  AFTER fruit_type;
```

**第二步：再改 `backend/models.py`**

```python
class SortRecord(db.Model):
    ...
    batch_no = db.Column(db.String(40), nullable=False, default="", comment="分拣批次号")
```

**第三步：重启后端**

```powershell
cd C:\Users\10149\Desktop\openMV\backend
.\venv\Scripts\python.exe app.py
```

顺序必须是「先改表、再改模型」。反过来会先报 `1054 Unknown column`。

## 变更脚本放哪

所有手工 SQL 按顺序编号存在本目录，命名规则 `NNN_描述.sql`：

```
db/
├─ README.md              # 本文档
├─ 000_baseline.sql       # 建库建表基线（可选，记录初始结构）
└─ 001_add_batch_no.sql   # 一次变更一个文件
```

执行方式（PowerShell，密码带末尾的点）：

```powershell
$env:MYSQL_PWD='Aa123456.'
& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe" -u root openmv_ai < "C:\Users\10149\Desktop\openMV\backend\db\001_add_batch_no.sql"
```

## 这个项目的表结构要点（踩过的坑）

| 表 | 注意点 |
|---|---|
| `user` | `password_hash` 是 **varchar(120)**，bcrypt 输出正好 60 字符；如果字段被截断到 18，任何密码都登不进 |
| `sys_setting` | 真实列名是 **`key_name`** 和 `value`，**没有 `update_time` 列**（加它会报 1054） |
| `sort_record` | `img_path` 存的是相对路径，形如 `records/20261109210945_xxx.jpg` |
| `detect_record` | 旧项目遗留表，本项目不映射、不读写、不删除 |
| `operation_log` | `write_operation_log()` 只 `add` 不 `commit`，跟着业务事务一起提交 |

## 以后要正规化：Flask-Migrate

现在表少、变更少，手工 ALTER 够用。多表多环境后建议引入 Alembic：

```powershell
.\venv\Scripts\python.exe -m pip install Flask-Migrate

# extensions.py: migrate = Migrate()
# app.py:       migrate.init_app(app, db)
.\venv\Scripts\python.exe -m flask --app app db init
.\venv\Scripts\python.exe -m flask --app app db migrate -m "baseline"
.\venv\Scripts\python.exe -m flask --app app db upgrade
```

注意：如果库里已经有表，第一次 `db migrate` 会检测到「表存在但没有版本记录」，需要先
`flask db stamp head` 把当前结构标记为基线，之后再做增量迁移。
