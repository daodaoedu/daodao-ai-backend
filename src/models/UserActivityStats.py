from sqlalchemy import Column, Integer, String, TIMESTAMP, func

from src.models.base import Base


class UserActivityStats(Base):
    __tablename__ = "user_activity_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ===== Login Activity =====
    last_login_at = Column(TIMESTAMP(timezone=True))

    last_active_at = Column(TIMESTAMP(timezone=True))

    login_count = Column(Integer, server_default="0")

    # ===== Engagement Metrics =====
    profile_views = Column(Integer, server_default="0")

    # ===== Device Info =====
    last_device_type = Column(String(20))
    last_os = Column(String(50))
    last_browser = Column(String(50))

    # ===== Timestamp =====
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    updated_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self):
        return f"<UserActivityStats id={self.id}>"
