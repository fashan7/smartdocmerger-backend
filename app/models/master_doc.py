import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, Integer, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class MasterDoc(Base):
    __tablename__ = "master_docs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), default="Master Document")
    description: Mapped[str] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="master_doc")  # noqa
    sections: Mapped[list["MasterDocSection"]] = relationship(
        "MasterDocSection", back_populates="master_doc",
        cascade="all, delete-orphan", order_by="MasterDocSection.position"
    )
    history: Mapped[list["MasterDocHistory"]] = relationship(
        "MasterDocHistory", back_populates="master_doc",
        cascade="all, delete-orphan", order_by="MasterDocHistory.created_at.desc()"
    )


class MasterDocSection(Base):
    __tablename__ = "master_doc_sections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    master_doc_id: Mapped[str] = mapped_column(String(36), ForeignKey("master_docs.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    master_doc: Mapped["MasterDoc"] = relationship("MasterDoc", back_populates="sections")
    ideas: Mapped[list["MasterDocIdea"]] = relationship(
        "MasterDocIdea", back_populates="section",
        cascade="all, delete-orphan", order_by="MasterDocIdea.position"
    )


class MasterDocIdea(Base):
    __tablename__ = "master_doc_ideas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    section_id: Mapped[str] = mapped_column(String(36), ForeignKey("master_doc_sections.id"), nullable=False, index=True)
    idea_id: Mapped[str] = mapped_column(String(36), ForeignKey("ideas.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)

    section: Mapped["MasterDocSection"] = relationship("MasterDocSection", back_populates="ideas")
    idea: Mapped["Idea"] = relationship("Idea", back_populates="master_doc_entries")  # noqa


class MasterDocHistory(Base):
    __tablename__ = "master_doc_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    master_doc_id: Mapped[str] = mapped_column(String(36), ForeignKey("master_docs.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    master_doc: Mapped["MasterDoc"] = relationship("MasterDoc", back_populates="history")
