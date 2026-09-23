"""Four deterministic, read-only business tools with bounded output."""

import ast
import json
import re
from decimal import Decimal, DecimalException, localcontext
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

from pydantic import Field, StrictStr, ValidationError
from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from tracefix.persistence.models import TargetOrderItem
from tracefix.target_agent.config import DATA_ROOT, AgentConfig
from tracefix.target_agent.data import TABLES, row_dict
from tracefix.target_agent.schemas import Observation, StrictModel


class SearchArguments(StrictModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=3, ge=1, le=5, strict=True)


class QueryArguments(StrictModel):
    entity: Literal["customers", "products", "orders"]
    filters: dict[str, StrictStr] = Field(default_factory=dict, max_length=5)
    limit: int = Field(default=10, ge=1, le=20, strict=True)


class CalculatorArguments(StrictModel):
    expression: str = Field(min_length=1, max_length=200)


class PolicyArguments(StrictModel):
    policy_id: str = Field(pattern=r"^[A-Z]+-\d{3}$", max_length=40)


SCHEMAS = {
    "search_documents": SearchArguments,
    "query_records": QueryArguments,
    "calculator": CalculatorArguments,
    "lookup_policy": PolicyArguments,
}
FILTERS = {
    "customers": {"id", "name", "tier"},
    "products": {"id", "name", "category"},
    "orders": {"id", "customer_id", "status", "condition"},
}
PREFIXES = {"customers": "customer", "products": "product", "orders": "order"}


class ToolError(Exception):
    pass


def calculate(expression: str) -> str:
    try:
        tree = ast.parse(expression, mode="eval")
        if len(list(ast.walk(tree))) > 80:
            raise ToolError("calculation_too_complex")

        def evaluate(node):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                value = Decimal(ast.get_source_segment(expression, node))
            elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
                value = evaluate(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
            elif isinstance(node, ast.BinOp) and isinstance(
                node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)
            ):
                a, b = evaluate(node.left), evaluate(node.right)
                if isinstance(node.op, ast.Add):
                    value = a + b
                elif isinstance(node.op, ast.Sub):
                    value = a - b
                elif isinstance(node.op, ast.Mult):
                    value = a * b
                else:
                    value = a / b
            else:
                raise ToolError("invalid_expression")
            if not value.is_finite() or abs(value) > Decimal("1e12"):
                raise ToolError("calculation_out_of_range")
            if value.is_zero():
                return Decimal(0)
            if value.adjusted() < -28:
                raise ToolError("calculation_out_of_range")
            return value

        with localcontext() as context:
            context.prec = 28
            return format(evaluate(tree.body), "f")
    except (SyntaxError, DecimalException, ValueError, RecursionError) as exc:
        raise ToolError("invalid_calculation") from exc


class ToolEnvironment:
    def __init__(
        self,
        engine: Engine,
        documents: Path = DATA_ROOT / "documents",
        injected_errors: dict[str, int] | None = None,
    ):
        self.engine = engine
        self.documents = {
            p.stem: p.read_text(encoding="utf-8") for p in sorted(documents.glob("*.md"))
        }
        self.injected_errors = dict(injected_errors or {})
        self.injected = bool(injected_errors)

    def definitions(self, config: AgentConfig) -> list[dict]:
        if set(config.tool_descriptions) != set(SCHEMAS):
            raise ValueError("Configuration must describe exactly the four target tools")
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": config.tool_descriptions[name],
                    "parameters": schema.model_json_schema(),
                },
            }
            for name, schema in SCHEMAS.items()
        ]

    def execute(self, name: str, arguments: dict, call_id: str) -> Observation:
        start = perf_counter()
        result = Observation(
            observation_id=f"obs:{uuid4().hex}",
            call_id=call_id,
            tool=name,
            arguments=arguments,
            ok=False,
        )
        try:
            if name not in SCHEMAS:
                raise ToolError("unknown_tool")
            args = SCHEMAS[name].model_validate(arguments)
            if self.injected_errors.get(name, 0) > 0:
                self.injected_errors[name] -= 1
                raise ToolError("injected_unavailable")
            result.data, result.source_ids, result.truncated = getattr(self, name)(args)
            result.ok = True
        except ValidationError as exc:
            result.error = "invalid_arguments"
            result.data = {"fields": [".".join(map(str, e["loc"])) for e in exc.errors()]}
        except ToolError as exc:
            result.error = str(exc)
        except SQLAlchemyError:
            result.error = "data_source_unavailable"
        except Exception:
            # Unexpected tool failures are observations too; never expose exception payloads.
            result.error = "internal_tool_error"
        result.latency_ms = round((perf_counter() - start) * 1000, 3)
        return result

    def search_documents(self, args: SearchArguments):
        terms = set(re.findall(r"[a-z0-9]+", args.query.lower()))
        ranked = sorted(
            (
                (-len(terms & set(re.findall(r"[a-z0-9]+", text.lower()))), key, text)
                for key, text in self.documents.items()
            )
        )
        hits = [(score, key, text) for score, key, text in ranked if score < 0]
        selected = hits[: args.limit]
        data = [{"policy_id": key, "excerpt": text[:800]} for _, key, text in selected]
        return (
            data,
            [f"policy:{key}" for _, key, _ in selected],
            (len(hits) > args.limit or any(len(text) > 800 for _, _, text in selected)),
        )

    def lookup_policy(self, args: PolicyArguments):
        if args.policy_id not in self.documents:
            raise ToolError("not_found")
        text = self.documents[args.policy_id]
        return (
            {"policy_id": args.policy_id, "text": text[:2400]},
            [f"policy:{args.policy_id}"],
            len(text) > 2400,
        )

    def calculator(self, args: CalculatorArguments):
        return {"expression": args.expression, "result": calculate(args.expression)}, [], False

    def query_records(self, args: QueryArguments):
        if not set(args.filters) <= FILTERS[args.entity]:
            raise ToolError("invalid_filter")
        model = TABLES[args.entity]
        query = select(model).order_by(model.id)
        for key, value in args.filters.items():
            query = query.where(getattr(model, key) == value)
        with Session(self.engine) as session:
            rows = list(session.scalars(query.limit(args.limit + 1)))
            if not rows and "id" in args.filters:
                raise ToolError("not_found")
            data = []
            sources = []
            truncated = len(rows) > args.limit
            for row in rows[: args.limit]:
                record = row_dict(row)
                sources.append(f"{PREFIXES[args.entity]}:{row.id}")
                if args.entity == "orders":
                    items = list(
                        session.scalars(
                            select(TargetOrderItem)
                            .where(TargetOrderItem.order_id == row.id)
                            .order_by(TargetOrderItem.product_id)
                            .limit(21)
                        )
                    )
                    record["items"] = [row_dict(item) for item in items[:20]]
                    truncated |= len(items) > 20
                data.append(record)
        # Also cap long result payloads independently of the row limit.
        while len(json.dumps(data)) > 6000 and data:
            data.pop()
            sources.pop()
            truncated = True
        return data, sources, truncated
