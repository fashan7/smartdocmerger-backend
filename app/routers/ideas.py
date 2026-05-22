from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.idea import Idea, IdeaStatus
from app.models.idea_pair import IdeaPair, PairStatus

router = APIRouter(prefix="/ideas", tags=["ideas"])


def _idea_out(idea: Idea, duplicate_count: int = 0) -> dict:
    return {
        "id": idea.id,
        "document_id": idea.document_id,
        "summary": idea.summary,
        "full_text": idea.full_text,
        "section_title": idea.section_title,
        "section_index": idea.section_index,
        "status": idea.status,
        "priority": idea.priority,
        "tags": idea.tags or [],
        "word_count": idea.word_count,
        "duplicate_count": duplicate_count,
        "created_at": idea.created_at.isoformat(),
    }


@router.get("")
async def list_ideas(
    status: Optional[str] = None,
    document_id: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Idea).where(Idea.user_id == current_user.id)

    if status:
        query = query.where(Idea.status == status)
    if document_id:
        query = query.where(Idea.document_id == document_id)
    if tag:
        query = query.where(Idea.tags.contains([tag]))
    if search:
        search_term = f"%{search}%"
        query = query.where(
            Idea.summary.ilike(search_term) | Idea.full_text.ilike(search_term)
        )
    if priority:
        query = query.where(Idea.priority == priority)

    query = query.order_by(Idea.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    ideas = result.scalars().all()

    # Count totals
    total_result = await db.execute(
        select(func.count()).select_from(Idea).where(Idea.user_id == current_user.id)
    )
    unique_result = await db.execute(
        select(func.count()).select_from(Idea).where(
            Idea.user_id == current_user.id, Idea.status == IdeaStatus.UNIQUE
        )
    )
    dup_result = await db.execute(
        select(func.count()).select_from(Idea).where(
            Idea.user_id == current_user.id, Idea.status == IdeaStatus.DUPLICATE
        )
    )

    # Get duplicate pair count per idea
    idea_ids = [i.id for i in ideas]
    duplicate_counts: dict[str, int] = {}

    if idea_ids:
        for idea_id in idea_ids:
            count_result = await db.execute(
                select(func.count()).select_from(IdeaPair).where(
                    (IdeaPair.idea_a_id == idea_id) | (IdeaPair.idea_b_id == idea_id),
                    IdeaPair.status == PairStatus.PENDING,
                )
            )
            duplicate_counts[idea_id] = count_result.scalar() or 0

    return {
        "items": [_idea_out(i, duplicate_counts.get(i.id, 0)) for i in ideas],
        "total": total_result.scalar(),
        "unique": unique_result.scalar(),
        "duplicates": dup_result.scalar(),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{idea_id}")
async def get_idea(
    idea_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Idea).where(Idea.id == idea_id, Idea.user_id == current_user.id)
    )
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    # Find its pairs
    pairs_result = await db.execute(
        select(IdeaPair).where(
            ((IdeaPair.idea_a_id == idea_id) | (IdeaPair.idea_b_id == idea_id)),
            IdeaPair.status == PairStatus.PENDING,
        )
    )
    pairs = pairs_result.scalars().all()

    return {
        **_idea_out(idea),
        "pairs": [
            {
                "pair_id": p.id,
                "other_idea_id": p.idea_b_id if p.idea_a_id == idea_id else p.idea_a_id,
                "similarity_score": p.similarity_score,
                "ai_recommendation": p.ai_recommendation,
            }
            for p in pairs
        ],
    }


class IdeaUpdateRequest(BaseModel):
    summary: Optional[str] = None
    full_text: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[list] = None


@router.patch("/{idea_id}")
async def update_idea(
    idea_id: str,
    body: IdeaUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Idea).where(Idea.id == idea_id, Idea.user_id == current_user.id)
    )
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    if body.summary is not None:
        idea.summary = body.summary[:500]
    if body.full_text is not None:
        idea.full_text = body.full_text
    if body.priority is not None:
        idea.priority = body.priority
    if body.status is not None:
        idea.status = body.status
    if body.tags is not None:
        idea.tags = body.tags

    await db.commit()
    return _idea_out(idea)


@router.delete("/{idea_id}", status_code=204)
async def delete_idea(
    idea_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Idea).where(Idea.id == idea_id, Idea.user_id == current_user.id)
    )
    idea = result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    await db.delete(idea)
    await db.commit()
