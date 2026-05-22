import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Float, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class PairStatus:
    PENDING = "pending"
    MERGED = "merged"
    KEPT_BOTH = "kept_both"
    DISCARDED = "discarded"
    DIFFERENT = "different"


class PairRecommendation:
    KEEP_A = "keep_a"
    KEEP_B = "keep_b"
    MERGE = "merge"
    KEEP_BOTH = "keep_both"


class IdeaPair(Base):
    __tablename__ = "idea_pairs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    idea_a_id: Mapped[str] = mapped_column(String(36), ForeignKey("ideas.id"), nullable=False)
    idea_b_id: Mapped[str] = mapped_column(String(36), ForeignKey("ideas.id"), nullable=False)

    # Similarity scores
    tfidf_score: Mapped[float] = mapped_column(Float, default=0.0)     # raw TF-IDF cosine score
    wording_match: Mapped[float] = mapped_column(Float, default=0.0)   # Claude: wording match %
    concept_match: Mapped[float] = mapped_column(Float, default=0.0)   # Claude: concept match %
    similarity_score: Mapped[float] = mapped_column(Float, default=0.0)  # final display score

    # Claude verdict
    ai_recommendation: Mapped[str] = mapped_column(String(20), nullable=True)
    ai_reason: Mapped[str] = mapped_column(Text, nullable=True)
    ai_confidence: Mapped[str] = mapped_column(String(20), nullable=True)  # high/medium/low

    # Resolution
    status: Mapped[str] = mapped_column(String(20), default=PairStatus.PENDING)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    idea_a: Mapped["Idea"] = relationship("Idea", foreign_keys=[idea_a_id], back_populates="pairs_as_a")  # noqa
    idea_b: Mapped["Idea"] = relationship("Idea", foreign_keys=[idea_b_id], back_populates="pairs_as_b")  # noqa
