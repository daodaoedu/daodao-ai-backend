from sqlalchemy import Column, Integer, String, Text, UniqueConstraint
from src.models.base import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)

    name = Column(String(255), nullable=False, unique=True)

    description = Column(Text)

    __table_args__ = (UniqueConstraint("name", name="roles_name_key"),)

    def __repr__(self):
        return f"<Role id={self.id} name={self.name}>"
