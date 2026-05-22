from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.idea import Idea, IdeaStatus
from app.models.idea_pair import IdeaPair, PairStatus
from app.models.document import Document
from app.models.master_doc import MasterDoc, MasterDocHistory
from app.models.notification import Notification, NotificationType
from app.services.ai_service import merge_two_ideas
from app.models.workspace_settings import WorkspaceSettings

router = APIRouter(prefix="/merge-queue", tags=["merge-queue"])


def _pair_out(pair: IdeaPair, idea_a: Idea, idea_b: Idea, doc_a_name: str, doc_b_name: str) -> dict:
    return {
        "pair_id": pair.id,
        "status": pair.status,
        "similarity_score": round(pair.similarity_score * 100, 1),
        "wording_match": pair.wording_match,
        "concept_match": pair.concept_match,
        "ai_recommendation": pair.ai_recommendation,
        "ai_reason": pair.ai_reason,
        "ai_confidence": pair.ai_confidence,
        "created_at": pair.created_at.isoformat(),
        "idea_a": {
            "id": idea_a.id,
            "summary": idea_a.summary,
            "full_text": idea_a.full_text[:300],
            "priority": idea_a.priority,
            "document_name": doc_a_name,
        },
        "idea_b": {
            "id": idea_b.id,
            "summary": idea_b.summary,
            "full_text": idea_b.full_text[:300],
            "priority": idea_b.priority,
            "document_name": doc_b_name,
        },
    }


@router.get("")
async def list_merge_queue(
    min_similarity: float = 0.0,
    document_id: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(IdeaPair).where(
        IdeaPair.user_id == current_user.id,
        IdeaPair.status == PairStatus.PENDING,
    )
    if min_similarity > 0:
        query = query.where(IdeaPair.similarity_score >= min_similarity / 100)

    query = query.order_by(IdeaPair.similarity_score.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    pairs = result.scalars().all()

    # Stats
    pending_count = await db.execute(
        select(func.count()).select_from(IdeaPair).where(
            IdeaPair.user_id == current_user.id, IdeaPair.status == PairStatus.PENDING
        )
    )
    resolved_today = await db.execute(
        select(func.count()).select_from(IdeaPair).where(
            IdeaPair.user_id == current_user.id,
            IdeaPair.status != PairStatus.PENDING,
            IdeaPair.resolved_at >= datetime.utcnow().replace(hour=0, minute=0, second=0),
        )
    )

    # Enrich pairs with idea and document data
    items = []
    for pair in pairs:
        idea_a_res = await db.execute(select(Idea).where(Idea.id == pair.idea_a_id))
        idea_b_res = await db.execute(select(Idea).where(Idea.id == pair.idea_b_id))
        idea_a = idea_a_res.scalar_one_or_none()
        idea_b = idea_b_res.scalar_one_or_none()

        if not idea_a or not idea_b:
            continue

        doc_a_res = await db.execute(select(Document).where(Document.id == idea_a.document_id))
        doc_b_res = await db.execute(select(Document).where(Document.id == idea_b.document_id))
        doc_a = doc_a_res.scalar_one_or_none()
        doc_b = doc_b_res.scalar_one_or_none()

        # Apply priority filter
        if priority:
            if idea_a.priority != priority and idea_b.priority != priority:
                continue

        items.append(_pair_out(
            pair, idea_a, idea_b,
            doc_a.name if doc_a else "Unknown",
            doc_b.name if doc_b else "Unknown",
        ))

    return {
        "items": items,
        "pending": pending_count.scalar(),
        "resolved_today": resolved_today.scalar(),
        "limit": limit,
        "offset": offset,
    }


@router.post("/{pair_id}/merge")
async def merge_pair(
    pair_id: str,
    body: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pair = await _get_pair(pair_id, current_user.id, db)

    idea_a_res = await db.execute(select(Idea).where(Idea.id == pair.idea_a_id))
    idea_b_res = await db.execute(select(Idea).where(Idea.id == pair.idea_b_id))
    idea_a = idea_a_res.scalar_one()
    idea_b = idea_b_res.scalar_one()

    # Get API key
    ws_res = await db.execute(select(WorkspaceSettings).where(WorkspaceSettings.user_id == current_user.id))
    ws = ws_res.scalar_one_or_none()
    api_key = ws.anthropic_api_key if ws else None

    # AI merges the text
    merged_text = await merge_two_ideas(idea_a.full_text, idea_b.full_text, api_key)

    # Update idea_a with merged content, mark idea_b as merged/removed
    keep_which = body.get("keep", "a")  # "a", "b", or "merge"

    if keep_which == "b":
        idea_b.status = IdeaStatus.UNIQUE
        idea_b.summary = idea_b.summary
        idea_a.status = IdeaStatus.MERGED
    elif keep_which == "merge":
        idea_a.full_text = merged_text
        idea_a.summary = idea_a.summary  # keep original summary
        idea_a.status = IdeaStatus.UNIQUE
        idea_b.status = IdeaStatus.MERGED
    else:  # keep a
        idea_a.status = IdeaStatus.UNIQUE
        idea_b.status = IdeaStatus.MERGED

    pair.status = PairStatus.MERGED
    pair.resolved_at = datetime.utcnow()

    # Log to master doc history if it exists
    master_res = await db.execute(select(MasterDoc).where(MasterDoc.user_id == current_user.id))
    master = master_res.scalar_one_or_none()
    if master:
        history = MasterDocHistory(
            master_doc_id=master.id,
            action=f"Merged ideas: '{idea_a.summary[:50]}' and '{idea_b.summary[:50]}'",
        )
        db.add(history)

    # Notification
    notif = Notification(
        user_id=current_user.id,
        type=NotificationType.MERGE_COMPLETE,
        title="Merge complete",
        body=f"Ideas merged: '{idea_a.summary[:60]}'",
        link="/master-doc",
    )
    db.add(notif)

    await db.commit()
    return {"message": "Merged successfully", "pair_id": pair_id}


@router.post("/{pair_id}/keep-both")
async def keep_both(
    pair_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pair = await _get_pair(pair_id, current_user.id, db)

    # Restore both ideas to unique
    await db.execute(
        update(Idea)
        .where(Idea.id.in_([pair.idea_a_id, pair.idea_b_id]))
        .values(status=IdeaStatus.UNIQUE)
    )

    pair.status = PairStatus.KEPT_BOTH
    pair.resolved_at = datetime.utcnow()
    await db.commit()
    return {"message": "Both ideas kept", "pair_id": pair_id}


@router.post("/{pair_id}/discard")
async def discard_duplicate(
    pair_id: str,
    body: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Discard idea_b (the duplicate), keep idea_a."""
    pair = await _get_pair(pair_id, current_user.id, db)

    discard_which = body.get("discard", "b")  # "a" or "b"

    if discard_which == "a":
        await db.execute(update(Idea).where(Idea.id == pair.idea_a_id).values(status=IdeaStatus.MERGED))
        await db.execute(update(Idea).where(Idea.id == pair.idea_b_id).values(status=IdeaStatus.UNIQUE))
    else:
        await db.execute(update(Idea).where(Idea.id == pair.idea_b_id).values(status=IdeaStatus.MERGED))
        await db.execute(update(Idea).where(Idea.id == pair.idea_a_id).values(status=IdeaStatus.UNIQUE))

    pair.status = PairStatus.DISCARDED
    pair.resolved_at = datetime.utcnow()
    await db.commit()
    return {"message": "Duplicate discarded", "pair_id": pair_id}


@router.post("/{pair_id}/flag-different")
async def flag_different(
    pair_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pair = await _get_pair(pair_id, current_user.id, db)

    await db.execute(
        update(Idea)
        .where(Idea.id.in_([pair.idea_a_id, pair.idea_b_id]))
        .values(status=IdeaStatus.UNIQUE)
    )

    pair.status = PairStatus.DIFFERENT
    pair.resolved_at = datetime.utcnow()
    await db.commit()
    return {"message": "Flagged as different ideas", "pair_id": pair_id}


async def _get_pair(pair_id: str, user_id: str, db: AsyncSession) -> IdeaPair:
    result = await db.execute(
        select(IdeaPair).where(
            IdeaPair.id == pair_id,
            IdeaPair.user_id == user_id,
        )
    )
    pair = result.scalar_one_or_none()
    if not pair:
        raise HTTPException(status_code=404, detail="Pair not found")
    if pair.status != PairStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"Pair already resolved: {pair.status}")
    return pair
