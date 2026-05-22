import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class NotificationType:
    PROCESSING_COMPLETE = "processing_complete"
    DUPLICATES_FOUND = "duplicates_found"
    MERGE_SUGGESTED = "merge_suggested"
    MERGE_COMPLETE = "merge_complete"
    PROCESSING_FAILED = "processing_failed"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    link: Mapped[str] = mapped_column(String(255), nullable=True)   # e.g. /documents/:id
    reference_id: Mapped[str] = mapped_column(String(36), nullable=True)  # document_id or pair_id
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="notifications")  # noqa
