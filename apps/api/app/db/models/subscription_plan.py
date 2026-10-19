from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SubscriptionPlanRecord(Base):
    __tablename__ = "subscription_plans"
    __table_args__ = (
        CheckConstraint("price_rub > 0", name="ck_subscription_plans_price_rub"),
        CheckConstraint(
            "price_stars IS NULL OR price_stars > 0",
            name="ck_subscription_plans_price_stars",
        ),
        CheckConstraint("duration_days > 0", name="ck_subscription_plans_duration"),
        CheckConstraint(
            "device_limit IS NULL OR device_limit >= 0",
            name="ck_subscription_plans_device_limit",
        ),
    )

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price_rub: Mapped[int] = mapped_column(BigInteger(), nullable=False)
    price_stars: Mapped[int | None] = mapped_column(BigInteger())
    duration_days: Mapped[int] = mapped_column(Integer(), nullable=False)
    features: Mapped[list[str]] = mapped_column(JSON(), nullable=False)
    device_limit: Mapped[int | None] = mapped_column(Integer())
    popular: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
