from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProjectMetadata(Base):
    __tablename__ = "project_metadata"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class TargetCustomer(Base):
    __tablename__ = "target_customers"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    tier: Mapped[str] = mapped_column(String(16))


class TargetProduct(Base):
    __tablename__ = "target_products"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(24))
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))


class TargetOrder(Base):
    __tablename__ = "target_orders"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("target_customers.id"))
    status: Mapped[str] = mapped_column(String(24))
    ordered_on: Mapped[date] = mapped_column(Date)
    delivered_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    condition: Mapped[str] = mapped_column(String(24))


class TargetOrderItem(Base):
    __tablename__ = "target_order_items"
    order_id: Mapped[str] = mapped_column(ForeignKey("target_orders.id"), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("target_products.id"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
