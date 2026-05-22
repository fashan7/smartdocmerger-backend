import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, Integer, Float, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class DocumentStatus:
    PROCESSING = "processing"
    CHUNKING = "chunking"
    EXTRACTING = "extracting"
    DETECTING = "detecting"
    READY = "ready"
    HAS_DUPLICATES = "has_duplicates"
    MERGED = "merged"
    FAILED = "failed"


class DocumentPriority:
    NORMAL = "normal"
    HIGH = "high"
    CORE = "core"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)  # md, pdf, txt, docx
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    priority: Mapped[str] = mapped_column(String(20), default=DocumentPriority.NORMAL)
    include_in_context: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(30), default=DocumentStatus.PROCESSING)
    processing_step: Mapped[str] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    idea_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="documents")  # noqa
    ideas: Mapped[list["Idea"]] = relationship("Idea", back_populates="document", cascade="all, delete-orphan")  # noqa
