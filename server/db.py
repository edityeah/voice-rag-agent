from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, DateTime, Integer, String, Text, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./voice_agent.db")
# Render gives postgres://, SQLAlchemy 2.x needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
QUOTA_SECONDS = int(os.getenv("QUOTA_SECONDS", str(15 * 60)))
QUOTA_PERIOD_DAYS = int(os.getenv("QUOTA_PERIOD_DAYS", "30"))

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    google_sub = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    period_start = Column(DateTime, default=utcnow)
    seconds_used = Column(Integer, default=0)
    custom_voice_id = Column(String, nullable=True)
    custom_voice_name = Column(String, nullable=True)

    events = relationship("UsageEvent", back_populates="user", cascade="all, delete-orphan")

    def roll_period_if_needed(self):
        if utcnow() - self.period_start.replace(tzinfo=timezone.utc) >= timedelta(days=QUOTA_PERIOD_DAYS):
            self.period_start = utcnow()
            self.seconds_used = 0

    def remaining_seconds(self) -> int:
        self.roll_period_if_needed()
        return max(0, QUOTA_SECONDS - self.seconds_used)

    def period_resets_at(self) -> datetime:
        return self.period_start.replace(tzinfo=timezone.utc) + timedelta(days=QUOTA_PERIOD_DAYS)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_name = Column(String, nullable=False, index=True)
    started_at = Column(DateTime, default=utcnow)
    duration_seconds = Column(Integer, default=0)
    user = relationship("User", back_populates="events")


class KbDocument(Base):
    __tablename__ = "kb_documents"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    char_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)
