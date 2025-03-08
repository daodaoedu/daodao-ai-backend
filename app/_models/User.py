from sqlalchemy import Column, Integer, String
from models import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    # 可擴充其他使用者基本資料

