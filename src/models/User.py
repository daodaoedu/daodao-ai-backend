import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    ARRAY,
    TIMESTAMP,
    Boolean,
    Column,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship

from src.models.base import Base  # 引用分離出的 Base
from src.utils.code_enum import education_stage_t, gender_t

if TYPE_CHECKING:
    pass


# User 表
class User(Base):
    __tablename__ = "users"

    # 欄位定義
    id = Column(
        Integer, primary_key=True, autoincrement=True, nullable=False, unique=True
    )  # Primary Key
    mongo_id = Column(Text, nullable=False, unique=True)
    external_id = Column(
        UUID(as_uuid=True), default=uuid.uuid4, unique=True, nullable=False
    )

    gender = Column("gender", gender_t, nullable=True)  # 對應 gender_t
    language = Column(String(255), nullable=True)
    education_stage = Column(
        "education_stage", education_stage_t, default="other", nullable=True
    )  # Default 設定為 'other'
    tag_list = Column("tag_list", ARRAY(String), nullable=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True)  # 外鍵
    is_open_location = Column(Boolean, nullable=True)
    location_id = Column(Integer, ForeignKey("location.id"), nullable=True)  # 外鍵
    nickname = Column(String(255), nullable=True)
    # identity_list = Column(ARRAY(Integer))  # Assuming identity_t is an array of position ids
    role_id = Column(Integer, default=2, comment="一般使用者，擁有基本功能")
    is_open_profile = Column(Boolean, nullable=True)
    birth_date = Column("birth_date", Date, nullable=True)
    basic_info_id = Column(Integer, ForeignKey("basic_info.id"), nullable=True)  # 外鍵
    createdDate = Column(TIMESTAMP(timezone=False), nullable=False)
    updatedDate = Column(TIMESTAMP(timezone=False), nullable=False)

    created_by = Column(String(255), nullable=True)  # for developer
    created_at = Column(TIMESTAMP(timezone=True), nullable=True)  # for developer
    updated_by = Column(String(255), nullable=True)  # for developer
    updated_at = Column(TIMESTAMP(timezone=True), nullable=True)  # for developer

    # 定義外鍵關聯
    contact = relationship("Contact", back_populates="user")
    location = relationship("Location", back_populates="user")
    basic_info = relationship("BasicInfo", back_populates="user")
    resource = relationship("Resource", back_populates="creator")
    stores = relationship("Store", back_populates="user")
    # 與身份的多對多關聯
    user_positions = relationship("UserPosition", back_populates="user")
    identities = association_proxy("user_positions", "position")

    # 用來反向查詢User所創建的群組
    groups_created = relationship("Group", back_populates="created_by_user")

    # 用來反向查詢User加入的群組
    user_join_group = relationship("UserJoinGroup", back_populates="user")

    profile = relationship("UserProfile", back_populates="user", uselist=False)
    comments = relationship(
        "Comment", back_populates="user", cascade="all, delete-orphan"
    )
    posts = relationship("Post", back_populates="user", cascade="all, delete-orphan")
    ideas = relationship("Idea", back_populates="user", cascade="all, delete")
    practices = relationship("Practice", back_populates="user", cascade="all, delete")
    # 在 User 模型中
    created_entity_resources = relationship(
        "EntityResource", back_populates="creator", cascade="all, delete-orphan"
    )

    created_tags = relationship(
        "EntityTag", back_populates="creator", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User(id={self.id}, external_id='{self.external_id}', nickname='{self.nickname}')>"

    @classmethod
    def from_dict(cls, data):
        return cls(
            external_id=data.get("external_id"),
            gender=data.get("gender"),
            language=data.get("language"),
            education_stage=data.get("education_stage"),
            tag_list=data.get("tag_list"),
            contact_id=data.get("contact_id"),
            is_open_location=data.get("is_open_location"),
            location_id=data.get("location_id"),
            nickname=data.get("nickname"),
            role=data.get("role"),
            is_open_profile=data.get("is_open_profile"),
            birth_date=data.get("birth_date"),
            basic_info_id=data.get("basic_info_id"),
            createdDate=data.get("createdDate"),
            updatedDate=data.get("updatedDate"),
            created_by=data.get("created_by"),
            created_at=data.get("created_at"),
            updated_by=data.get("updated_by"),
            updated_at=data.get("updated_at"),
        )

    def to_dict(self):
        return {
            "id": self.id,
            "external_id": str(self.external_id) if self.external_id else None,
            "gender": self.gender,
            "language": self.language,
            "education_stage": self.education_stage,
            "tag_list": self.tag_list,
            "contact_id": self.contact_id,
            "is_open_location": self.is_open_location,
            "location_id": self.location_id,
            "nickname": self.nickname,
            "role": self.role,
            "is_open_profile": self.is_open_profile,
            "birth_date": self.birth_date,
            "basic_info_id": self.basic_info_id,
            "createdDate": self.createdDate,
            "updatedDate": self.updatedDate,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_by": self.updated_by,
            "updated_at": self.updated_at,
            "identities": [position.name for position in self.identities],  # 提取身份名稱
        }
