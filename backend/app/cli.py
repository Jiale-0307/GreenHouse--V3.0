import argparse
import getpass
import json

from pydantic import TypeAdapter

from .auth import bootstrap_admin
from .config import Settings
from .core import seed
from .db import Database
from .ingestion import configure_site
from .schemas import Identifier, SiteConfig


def main():
    parser = argparse.ArgumentParser(description="后端建表和初始化；不会连接PLC或下发动作")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="在已有MySQL数据库中创建初始表（不删除现有表）")
    admin = commands.add_parser("create-admin", help="交互式创建首个管理员")
    admin.add_argument("--username", default="admin")
    configure = commands.add_parser("configure-site", help="导入站点定义；文件可能含视频签名，勿提交")
    configure.add_argument("--site", default="default-site")
    configure.add_argument("--file", required=True)
    commands.add_parser("export-sql", help="输出MySQL初始建表SQL，不连接数据库")
    preview = commands.add_parser("preview-modbus", help="离线校验读取配置并预览报文；不连接MQTT/数据库")
    preview.add_argument("--file", required=True)
    args = parser.parse_args()
    if args.command == "preview-modbus":
        from .modbus_mqtt import load_config, modbus_request

        config = load_config(args.file)
        for index, point in enumerate(config.points, 1):
            frame = modbus_request(index, point, config.addressOffset)
            print(f"{point.metricId} D{point.address} enabled={point.enabled}: {frame.hex(' ')}")
        print(f"传输配置已确认: {config.transportConfirmed}；仅预览，未发送任何报文")
        return
    if args.command == "export-sql":
        from sqlalchemy.dialects import mysql
        from sqlalchemy.schema import CreateIndex, CreateTable
        from .models import Base

        for table in Base.metadata.sorted_tables:
            print(str(CreateTable(table, if_not_exists=True).compile(dialect=mysql.dialect())) + ";")
            for index in sorted(table.indexes, key=lambda i: i.name):
                print(str(CreateIndex(index).compile(dialect=mysql.dialect())) + ";")
        return
    cfg = Settings()
    db = Database(cfg)
    try:
        db.migrate()
        with db.session() as session:
            seed(session, cfg)
            if args.command == "create-admin":
                username = TypeAdapter(Identifier).validate_python(args.username)
                password = getpass.getpass("管理员密码（至少12位）：")
                if password != getpass.getpass("再次输入密码："):
                    raise ValueError("两次密码不同")
                bootstrap_admin(session, username, password)
            elif args.command == "configure-site":
                with open(args.file, encoding="utf-8") as source:
                    body = SiteConfig.model_validate(json.load(source))
                configure_site(session, args.site, body, cfg, "local-cli")
        print("操作完成")
    except Exception as exc:
        print(f"操作失败（{type(exc).__name__}）；请检查配置、数据库权限和输入。")
        raise SystemExit(1) from None
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    main()
