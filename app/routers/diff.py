from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.idea import Idea
from app.models.idea_pair import IdeaPair
from app.models.document import Document

router = APIRouter(prefix="/diff", tags=["diff"])


@router.get("/{pair_id}")
async def get_diff(
    pair_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(IdeaPair).where(
            IdeaPair.id == pair_id,
            IdeaPair.user_id == current_user.id,
        )
    )
    pair = result.scalar_one_or_none()
    if not pair:
        raise HTTPException(status_code=404, detail="Idea pair not found")

    # Load both ideas
    idea_a_result = await db.execute(select(Idea).where(Idea.id == pair.idea_a_id))
    idea_a = idea_a_result.scalar_one_or_none()

    idea_b_result = await db.execute(select(Idea).where(Idea.id == pair.idea_b_id))
    idea_b = idea_b_result.scalar_one_or_none()

    if not idea_a or not idea_b:
        raise HTTPException(status_code=404, detail="One or both ideas not found")

    # Load source documents
    doc_a_result = await db.execute(select(Document).where(Document.id == idea_a.document_id))
    doc_a = doc_a_result.scalar_one_or_none()

    doc_b_result = await db.execute(select(Document).where(Document.id == idea_b.document_id))
    doc_b = doc_b_result.scalar_one_or_none()

    return {
        "pair_id": pair.id,
        "status": pair.status,
        "similarity_score": round(pair.similarity_score * 100, 1),
        "tfidf_score": round(pair.tfidf_score * 100, 1),
        "wording_match": pair.wording_match,
        "concept_match": pair.concept_match,
        "ai_recommendation": pair.ai_recommendation,
        "ai_reason": pair.ai_reason,
        "ai_confidence": pair.ai_confidence,
        "idea_a": {
            "id": idea_a.id,
            "summary": idea_a.summary,
            "full_text": idea_a.full_text,
            "section_title": idea_a.section_title,
            "priority": idea_a.priority,
            "word_count": idea_a.word_count,
            "created_at": idea_a.created_at.isoformat(),
            "document": {
                "id": doc_a.id if doc_a else None,
                "name": doc_a.name if doc_a else "Unknown",
                "file_type": doc_a.file_type if doc_a else "txt",
                "created_at": doc_a.created_at.isoformat() if doc_a else None,
            },
        },
        "idea_b": {
            "id": idea_b.id,
            "summary": idea_b.summary,
            "full_text": idea_b.full_text,
            "section_title": idea_b.section_title,
            "priority": idea_b.priority,
            "word_count": idea_b.word_count,
            "created_at": idea_b.created_at.isoformat(),
            "document": {
                "id": doc_b.id if doc_b else None,
                "name": doc_b.name if doc_b else "Unknown",
                "file_type": doc_b.file_type if doc_b else "txt",
                "created_at": doc_b.created_at.isoformat() if doc_b else None,
            },
        },
    }
