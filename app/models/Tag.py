from sqlalchemy import (
    Column, Integer, String, DateTime, func, UniqueConstraint
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from .base import Base
from typing import List


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.current_timestamp())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.current_timestamp())

    # 💡 關聯到 entity_tags（多對多多型關聯）
    entities: Mapped[List["EntityTag"]] = relationship(
        "EntityTag",
        back_populates="tag",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tag(id={self.id}, name='{self.name}')>"
