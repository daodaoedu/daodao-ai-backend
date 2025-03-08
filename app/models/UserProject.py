
# 用戶身份聯接表
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base
from .base import Base  # 引用分離出的 Base


class UserProject(Base):
    __tablename__ = "user_project"

    id = Column(Integer, primary_key=True, autoincrement=True, unique=True, comment="主鍵")
    user_external_id = Column(UUID(as_uuid=True), ForeignKey("users.external_id", ondelete="CASCADE"), comment="使用者外部 ID")
    project_id = Column(UUID(as_uuid=True), ForeignKey("project.id", ondelete="CASCADE"), comment="專案 ID")