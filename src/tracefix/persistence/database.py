from uuid import uuid4

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from tracefix.common.config import Settings
from tracefix.persistence.models import ProjectMetadata


def make_engine(settings: Settings, *, include_database: bool = True) -> Engine:
    return create_engine(
        settings.database_url(include_database=include_database),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 5, "read_timeout": 15, "write_timeout": 15},
    )


def create_database(settings: Settings) -> str:
    """Create only the configured database; existing schemas/data are never dropped."""
    engine = make_engine(settings, include_database=False)
    try:
        with engine.connect() as conn:
            version = str(conn.exec_driver_sql("SELECT VERSION()").scalar_one())
            # Settings validates the identifier; quote it for the MySQL dialect as well.
            name = engine.dialect.identifier_preparer.quote_identifier(settings.db_name)
            conn.exec_driver_sql(
                f"CREATE DATABASE IF NOT EXISTS {name} "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            conn.commit()
            return version
    finally:
        engine.dispose()


def smoke_database(engine: Engine) -> str:
    """Commit a uniquely named record, read in a new session, then delete only that record."""
    key = f"smoke:{uuid4().hex}"
    expected = "TraceFix database smoke check"
    try:
        with Session(engine) as session, session.begin():
            session.add(ProjectMetadata(key=key, value=expected))
        with Session(engine) as session:
            value = session.scalar(select(ProjectMetadata.value).where(ProjectMetadata.key == key))
            if value != expected:
                raise RuntimeError("Database smoke record did not round-trip")
        return "Database insert/read smoke check passed"
    finally:
        with Session(engine) as session, session.begin():
            record = session.get(ProjectMetadata, key)
            if record is not None:
                session.delete(record)
