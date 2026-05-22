import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Float, Text, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class WorkspaceSettings(Base):
    __tablename__ = "workspace_settings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, unique=True)

    workspace_name: Mapped[str] = mapped_column(String(255), default="My Workspace")
    project_context: Mapped[str] = mapped_column(Text, nullable=True)
    default_priority: Mapped[str] = mapped_column(String(20), default="normal")

    # API keys stored as-is (encrypt in production with key_vault pattern)
    anthropic_api_key: Mapped[str] = mapped_column(String(500), nullable=True)
    openai_api_key: Mapped[str] = mapped_column(String(500), nullable=True)
    anthropic_key_valid: Mapped[bool] = mapped_column(Boolean, nullable=True)
    openai_key_valid: Mapped[bool] = mapped_column(Boolean, nullable=True)

    selected_model: Mapped[str] = mapped_column(String(100), default="claude-sonnet-4-20250514")
    similarity_threshold: Mapped[float] = mapped_column(Float, default=0.75)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="workspace_settings")  # noqa
