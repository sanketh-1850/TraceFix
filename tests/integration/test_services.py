from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import inspect

from tracefix.common.config import load_settings
from tracefix.common.ollama_smoke import run_smoke
from tracefix.persistence.cli import migration_config
from tracefix.persistence.database import create_database, make_engine, smoke_database

pytestmark = pytest.mark.integration


def test_live_migration_roundtrip_in_disposable_database():
    # Never downgrade the configured project database. Use a fresh random schema.
    settings = load_settings().model_copy(update={"db_name": f"tracefix_test_{uuid4().hex}"})
    create_database(settings)
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        assert "passed" in smoke_database(engine)
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "base")
            assert "project_metadata" not in inspect(connection).get_table_names()
            command.upgrade(config, "head")
            assert "project_metadata" in inspect(connection).get_table_names()
    finally:
        engine.dispose()
        server = make_engine(settings, include_database=False)
        try:
            with server.connect() as connection:
                quoted = server.dialect.identifier_preparer.quote_identifier(settings.db_name)
                connection.exec_driver_sql(f"DROP DATABASE {quoted}")
                connection.commit()
        finally:
            server.dispose()


def test_live_database_roundtrip():
    engine = make_engine(load_settings())
    try:
        assert "passed" in smoke_database(engine)
    finally:
        engine.dispose()


@pytest.mark.parametrize("model_field", ["ollama_model", "ollama_judge_model"])
def test_live_ollama(model_field):
    settings = load_settings()
    assert run_smoke(settings, getattr(settings, model_field))["status"] == "passed"
