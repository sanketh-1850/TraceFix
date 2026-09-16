import argparse
import logging

from alembic import command
from alembic.config import Config

from tracefix.common.config import PROJECT_ROOT, load_settings
from tracefix.common.logging import configure_logging
from tracefix.persistence.database import create_database, make_engine, smoke_database


def migration_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage TraceFix's configured MySQL/MariaDB schema"
    )
    parser.add_argument("action", choices=["init", "upgrade", "current", "smoke"])
    args = parser.parse_args()
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        if args.action == "init":
            version = create_database(settings)
            print(f"Database {settings.db_name} ready (server {version})")
        if args.action in ("init", "upgrade"):
            command.upgrade(migration_config(), "head")
            print("Migrations applied")
        elif args.action == "current":
            command.current(migration_config())
        elif args.action == "smoke":
            engine = make_engine(settings)
            try:
                print(smoke_database(engine))
            finally:
                engine.dispose()
        return 0
    except Exception as exc:
        # Avoid emitting database passwords or SQL parameter values from exceptions.
        logging.error(
            "Database command failed (%s). Check server.env and service access.", type(exc).__name__
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
