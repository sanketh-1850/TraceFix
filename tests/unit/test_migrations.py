from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from tracefix.persistence.cli import migration_config
from tracefix.persistence.database import smoke_database
from tracefix.persistence.models import Base, ProjectMetadata


def test_upgrade_roundtrip_and_downgrade(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    try:
        with engine.connect() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            assert "project_metadata" in inspect(connection).get_table_names()
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        with Session(engine) as session, session.begin():
            session.add(ProjectMetadata(key="existing", value="keep me"))
        assert "passed" in smoke_database(engine)
        with Session(engine) as session:
            assert list(session.scalars(select(ProjectMetadata.key))) == ["existing"]
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")  # Idempotent upgrade preserves existing records.
            assert connection.scalar(select(ProjectMetadata.value)) == "keep me"
            connection.commit()
            command.downgrade(config, "base")
            assert "project_metadata" not in inspect(connection).get_table_names()
            command.upgrade(config, "head")
            assert "project_metadata" in inspect(connection).get_table_names()
    finally:
        engine.dispose()
