from contextlib import contextmanager

from sqlalchemy import create_engine, delete, event, select, text
from sqlalchemy.orm import sessionmaker

from .models import Base, SchemaVersion


class Database:
    def __init__(self, settings):
        url = settings.database_url
        is_sqlite = str(url).startswith("sqlite")
        args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {"connect_timeout": 10}
        if settings.db_ssl_ca and not is_sqlite:
            args["ssl"] = {"ca": settings.db_ssl_ca, "check_hostname": True}
        self.engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=1800,
            connect_args=args,
            hide_parameters=True,
            **({"isolation_level": "READ COMMITTED"} if not is_sqlite else {}),
        )
        if is_sqlite:

            @event.listens_for(self.engine, "connect")
            def foreign_keys(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        self.runtime_lock = None

    def acquire_runtime_lock(self):
        if self.engine.dialect.name != "mysql":
            return
        connection = self.engine.connect()
        if connection.execute(text("SELECT GET_LOCK('zfxzg_backend_instance', 0)")).scalar() != 1:
            connection.close()
            raise RuntimeError("此MySQL已有后端实例运行；首版只支持1个worker/实例")
        connection.commit()
        self.runtime_lock = connection

    def release_runtime_lock(self):
        if self.runtime_lock:
            self.runtime_lock.execute(text("SELECT RELEASE_LOCK('zfxzg_backend_instance')"))
            self.runtime_lock.commit()
            self.runtime_lock.close()
            self.runtime_lock = None

    @contextmanager
    def session(self):
        with self.sessions() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def migrate(self):
        # MySQL DDL 会隐式提交；持有同一连接的命名锁，避免重复启动并发建表。
        with self.engine.connect() as connection:
            mysql = self.engine.dialect.name == "mysql"
            if mysql and connection.execute(text("SELECT GET_LOCK('zfxzg_schema_v1', 30)")).scalar() != 1:
                raise RuntimeError("数据库迁移锁超时")
            try:
                Base.metadata.create_all(connection)
                versions = connection.execute(select(SchemaVersion.version)).scalars().all()
                if versions and versions not in ([1], [2]):
                    raise RuntimeError("数据库结构版本不兼容，请使用对应迁移版本")
                # v2只新增表，不重建旧表、不更改账号与历史列；中断后可重复运行。
                if versions != [2]:
                    connection.execute(delete(SchemaVersion))
                    connection.execute(SchemaVersion.__table__.insert().values(version=2))
                connection.commit()
            finally:
                if mysql:
                    connection.execute(text("SELECT RELEASE_LOCK('zfxzg_schema_v1')"))
                    connection.commit()

    def check(self):
        with self.engine.connect() as connection:
            return connection.execute(select(SchemaVersion.version)).scalars().all() == [2]
