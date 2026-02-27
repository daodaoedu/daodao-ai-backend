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
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship

from src.models.base import Base  # 引用分離出的 Base
from src.utils.code_enum import education_stage_t, gender_t

if TYPE_CHECKING:
    pass


class User(Base):
    __tablename__ = "users"

    # ===== PK =====
    id = Column(Integer, primary_key=True, autoincrement=True)

    # ===== External Identity =====
    external_id = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4
    )

    mongo_id = Column(Text, unique=True, nullable=False)

    # ===== Profile =====
    gender = Column(gender_t, nullable=True)

    language = Column(String(255))

    education_stage = Column(education_stage_t, server_default="other", nullable=True)

    tag_list = Column(ARRAY(String))

    nickname = Column(String(255))

    personal_slogan = Column(Text)

    professional_field = Column(String(255))

    custom_position = Column(String(100))

    # ===== Contact / Location =====
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"))

    location_id = Column(Integer, ForeignKey("location.id", ondelete="SET NULL"))

    basic_info_id = Column(Integer, ForeignKey("basic_info.id", ondelete="SET NULL"))

    # ===== Role =====
    role_id = Column(
        Integer, ForeignKey("roles.id"), nullable=False, comment="一般使用者預設角色"
    )

    # ===== Visibility =====
    is_open_location = Column(Boolean)

    is_open_profile = Column(Boolean)

    # ===== Birth =====
    birth_date = Column(Date)

    # ===== Activity =====
    activity_stats_id = Column(Integer, ForeignKey("user_activity_stats.id"))

    # ===== Verification =====
    verified = Column(Boolean, server_default="false")
    verified_at = Column(TIMESTAMP(timezone=True))

    custom_id = Column(String(255))
    custom_id_created_at = Column(TIMESTAMP)

    custom_id_verified = Column(Boolean, server_default="false")

    # ===== Audit =====
    createdDate = Column(TIMESTAMP(timezone=True), server_default=func.now())

    updatedDate = Column(TIMESTAMP(timezone=True), onupdate=func.now())

    created_by = Column(String(255))
    created_at = Column(TIMESTAMP(timezone=True))
    updated_by = Column(String(255))
    updated_at = Column(TIMESTAMP(timezone=True))

    # ===== Relationship =====
    contact = relationship("Contact", back_populates="user")
    location = relationship("Location", back_populates="user")
    basic_info = relationship("BasicInfo", back_populates="user")

    resource = relationship("Resource", back_populates="creator")

    stores = relationship("Store", back_populates="user")

    user_positions = relationship("UserPosition", back_populates="user")

    identities = association_proxy("user_positions", "position")

    posts = relationship("Post", back_populates="user", cascade="all, delete-orphan")

    ideas = relationship("Idea", back_populates="user", cascade="all, delete")

    practices = relationship("Practice", back_populates="user", cascade="all, delete")

    comments = relationship("Comment", back_populates="user")
    created_entity_resources = relationship("EntityResource", back_populates="creator")
    created_tags = relationship("EntityTag", back_populates="creator")
    groups_created = relationship("Group", back_populates="creator")

    user_join_group = relationship("UserJoinGroup", back_populates="user")
    profile = relationship(
        "UserProfile", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<User id={self.id} nickname={self.nickname}>"
