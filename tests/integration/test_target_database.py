from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from tracefix.common.config import load_settings
from tracefix.persistence.cli import migration_config
from tracefix.persistence.database import create_database, make_engine
from tracefix.persistence.models import ProjectMetadata, TargetOrder
from tracefix.target_agent.data import seed_data
from tracefix.target_agent.tools import ToolEnvironment

pytestmark = pytest.mark.integration


def test_target_seed_tools_and_isolated_downgrade():
    settings = load_settings().model_copy(update={"db_name": f"tracefix_test_{uuid4().hex}"})
    create_database(settings)
    engine = make_engine(settings)
    try:
        with engine.connect() as connection:
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "0001_project_metadata")
        with Session(engine) as session, session.begin():
            session.add(ProjectMetadata(key="preserve", value="original"))
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        assert seed_data(engine) == 79
        assert seed_data(engine) == 0
        with Session(engine) as session:
            assert len(list(session.scalars(select(TargetOrder)))) == 30
            assert session.get(ProjectMetadata, "preserve").value == "original"
        tools = ToolEnvironment(engine)
        result = tools.execute(
            "query_records", {"entity": "orders", "filters": {"id": "ORD-010"}}, "a"
        )
        assert result.ok and len(result.data[0]["items"]) == 2
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0001_project_metadata")
            assert "target_orders" not in inspect(connection).get_table_names()
            assert "project_metadata" in inspect(connection).get_table_names()
            command.upgrade(config, "head")
        assert seed_data(engine) == 79
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
