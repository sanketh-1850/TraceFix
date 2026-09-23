"""Fixture loading, conflict-safe seeding, and reproducible snapshot identity."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from tracefix.persistence.models import (
    TargetCustomer,
    TargetOrder,
    TargetOrderItem,
    TargetProduct,
)
from tracefix.target_agent.config import DATA_ROOT, digest

TABLES = {
    "customers": TargetCustomer,
    "products": TargetProduct,
    "orders": TargetOrder,
    "order_items": TargetOrderItem,
}


def normalize(value):
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if isinstance(value, date):
        return value.isoformat()
    return value


def row_dict(row) -> dict:
    return {column.name: normalize(getattr(row, column.name)) for column in row.__table__.columns}


def load_fixtures(path: Path = DATA_ROOT / "seed/business.json") -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def seed_data(engine: Engine, fixtures: dict | None = None) -> int:
    fixtures = fixtures or load_fixtures()
    inserted = 0
    with Session(engine) as session, session.begin():
        for name, model in TABLES.items():
            for raw in fixtures[name]:
                values = dict(raw)
                for field in ("ordered_on", "delivered_on"):
                    if values.get(field):
                        values[field] = date.fromisoformat(values[field])
                for field in ("price", "unit_price"):
                    if field in values:
                        values[field] = Decimal(values[field])
                identity = tuple(values[c.name] for c in model.__table__.primary_key)
                existing = session.get(model, identity)
                if existing is not None:
                    if row_dict(existing) != {k: normalize(v) for k, v in values.items()}:
                        raise ValueError(f"Conflicting fixture: {name} {identity}")
                else:
                    session.add(model(**values))
                    inserted += 1
            session.flush()
    return inserted


def snapshot(engine: Engine, documents: Path = DATA_ROOT / "documents") -> str:
    """Hash actual database contents and document bytes, not just the seed file."""
    with Session(engine) as session:
        tables = {
            name: [
                row_dict(row)
                for row in session.scalars(
                    select(model).order_by(*model.__table__.primary_key.columns)
                )
            ]
            for name, model in TABLES.items()
        }
    corpus = {
        path.name: path.read_text(encoding="utf-8") for path in sorted(documents.glob("*.md"))
    }
    return digest({"tables": tables, "documents": corpus})
