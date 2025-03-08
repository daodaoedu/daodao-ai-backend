from sqlalchemy import Column, Integer, ARRAY, String
from sqlalchemy.orm import relationship
from utils.code_enum import want_to_do_list_t

from .base import Base  # 引用分離出的 Base


class BasicInfo(Base):
    __tablename__ = "basic_info"

    id = Column(Integer, primary_key=True, autoincrement=True, nullable=False, unique=True)
    self_introduction = Column(String, nullable=True)
    share_list = Column("share_list", String, nullable=True)  # text
    want_to_do_list = Column("want_to_do_list", ARRAY(want_to_do_list_t), nullable=True)

    # 與 User 關聯
    user = relationship("User", back_populates="basic_info")
