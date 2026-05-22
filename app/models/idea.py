import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class IdeaStatus:
    UNIQUE = "unique"
    DUPLICATE = "duplicate"
    MERGED = "merged"
    OUTDATED = "outdated"


class Idea(Base):
    __tablename__ = "ideas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    section_title: Mapped[str] = mapped_column(String(255), nullable=True)
    section_index: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default=IdeaStatus.UNIQUE)
    priority: Mapped[str] = mapped_column(String(20), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document: Mapped["Document"] = relationship("Document", back_populates="ideas")  # noqa
    pairs_as_a: Mapped[list["IdeaPair"]] = relationship("IdeaPair", foreign_keys="IdeaPair.idea_a_id", back_populates="idea_a", cascade="all, delete-orphan")  # noqa
    pairs_as_b: Mapped[list["IdeaPair"]] = relationship("IdeaPair", foreign_keys="IdeaPair.idea_b_id", back_populates="idea_b", cascade="all, delete-orphan")  # noqa
    master_doc_entries: Mapped[list["MasterDocIdea"]] = relationship("MasterDocIdea", back_populates="idea")  # noqa
