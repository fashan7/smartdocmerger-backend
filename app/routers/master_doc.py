from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.master_doc import MasterDoc, MasterDocSection, MasterDocIdea, MasterDocHistory
from app.models.idea import Idea

router = APIRouter(prefix="/master-doc", tags=["master-doc"])


async def _get_or_create_master_doc(user_id: str, db: AsyncSession) -> MasterDoc:
    result = await db.execute(select(MasterDoc).where(MasterDoc.user_id == user_id))
    master = result.scalar_one_or_none()
    if not master:
        master = MasterDoc(user_id=user_id)
        db.add(master)
        await db.commit()
        await db.refresh(master)
    return master


@router.get("")
async def get_master_doc(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    master = await _get_or_create_master_doc(current_user.id, db)

    # Load sections with ideas
    sections_result = await db.execute(
        select(MasterDocSection)
        .where(MasterDocSection.master_doc_id == master.id)
        .order_by(MasterDocSection.position)
    )
    sections = sections_result.scalars().all()

    sections_out = []
    for section in sections:
        entries_result = await db.execute(
            select(MasterDocIdea)
            .where(MasterDocIdea.section_id == section.id)
            .order_by(MasterDocIdea.position)
        )
        entries = entries_result.scalars().all()

        ideas_out = []
        for entry in entries:
            idea_result = await db.execute(select(Idea).where(Idea.id == entry.idea_id))
            idea = idea_result.scalar_one_or_none()
            if idea:
                ideas_out.append({
                    "entry_id": entry.id,
                    "idea_id": idea.id,
                    "summary": idea.summary,
                    "full_text": idea.full_text,
                    "position": entry.position,
                    "source_document_id": idea.document_id,
                })

        sections_out.append({
            "id": section.id,
            "title": section.title,
            "position": section.position,
            "idea_count": len(ideas_out),
            "ideas": ideas_out,
        })

    # Recent history
    history_result = await db.execute(
        select(MasterDocHistory)
        .where(MasterDocHistory.master_doc_id == master.id)
        .order_by(MasterDocHistory.created_at.desc())
        .limit(20)
    )
    history = history_result.scalars().all()

    return {
        "id": master.id,
        "title": master.title,
        "description": master.description,
        "tags": master.tags or [],
        "word_count": master.word_count,
        "updated_at": master.updated_at.isoformat(),
        "sections": sections_out,
        "history": [
            {"id": h.id, "action": h.action, "created_at": h.created_at.isoformat()}
            for h in history
        ],
    }


class MasterDocUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list] = None


@router.patch("")
async def update_master_doc(
    body: MasterDocUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    master = await _get_or_create_master_doc(current_user.id, db)

    if body.title is not None:
        master.title = body.title
    if body.description is not None:
        master.description = body.description
    if body.tags is not None:
        master.tags = body.tags

    await db.commit()
    return {"message": "Updated"}


class SectionCreate(BaseModel):
    title: str
    position: Optional[int] = None


@router.post("/sections", status_code=201)
async def create_section(
    body: SectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    master = await _get_or_create_master_doc(current_user.id, db)

    # Default position = end
    if body.position is None:
        count_result = await db.execute(
            select(func.count()).select_from(MasterDocSection)
            .where(MasterDocSection.master_doc_id == master.id)
        )
        body.position = count_result.scalar() or 0

    section = MasterDocSection(
        master_doc_id=master.id,
        title=body.title,
        position=body.position,
    )
    db.add(section)
    await db.commit()
    await db.refresh(section)
    return {"id": section.id, "title": section.title, "position": section.position}


@router.patch("/sections/{section_id}")
async def update_section(
    section_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    section = await _get_section(section_id, current_user.id, db)

    if "title" in body:
        section.title = body["title"]
    if "position" in body:
        section.position = body["position"]

    await db.commit()
    return {"message": "Section updated"}


@router.delete("/sections/{section_id}", status_code=204)
async def delete_section(
    section_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    section = await _get_section(section_id, current_user.id, db)
    await db.delete(section)
    await db.commit()


class AddIdeaToSection(BaseModel):
    idea_id: str
    position: Optional[int] = None


@router.post("/sections/{section_id}/ideas", status_code=201)
async def add_idea_to_section(
    section_id: str,
    body: AddIdeaToSection,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    section = await _get_section(section_id, current_user.id, db)

    # Verify idea belongs to user
    idea_result = await db.execute(
        select(Idea).where(Idea.id == body.idea_id, Idea.user_id == current_user.id)
    )
    idea = idea_result.scalar_one_or_none()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea not found")

    if body.position is None:
        count_result = await db.execute(
            select(func.count()).select_from(MasterDocIdea)
            .where(MasterDocIdea.section_id == section_id)
        )
        body.position = count_result.scalar() or 0

    entry = MasterDocIdea(
        section_id=section_id,
        idea_id=body.idea_id,
        position=body.position,
    )
    db.add(entry)

    # Log history
    master_result = await db.execute(select(MasterDoc).where(MasterDoc.user_id == current_user.id))
    master = master_result.scalar_one_or_none()
    if master:
        history = MasterDocHistory(
            master_doc_id=master.id,
            action=f"Added idea to section '{section.title}': '{idea.summary[:60]}'",
        )
        db.add(history)

    await db.commit()
    return {"message": "Idea added to section"}


@router.delete("/sections/{section_id}/ideas/{entry_id}", status_code=204)
async def remove_idea_from_section(
    section_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MasterDocIdea).where(MasterDocIdea.id == entry_id, MasterDocIdea.section_id == section_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    await db.delete(entry)
    await db.commit()


@router.get("/export/md", response_class=PlainTextResponse)
async def export_markdown(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    master = await _get_or_create_master_doc(current_user.id, db)
    sections_result = await db.execute(
        select(MasterDocSection)
        .where(MasterDocSection.master_doc_id == master.id)
        .order_by(MasterDocSection.position)
    )
    sections = sections_result.scalars().all()

    lines = [f"# {master.title}", ""]
    if master.description:
        lines += [master.description, ""]

    for section in sections:
        lines.append(f"## {section.title}")
        lines.append("")

        entries_result = await db.execute(
            select(MasterDocIdea)
            .where(MasterDocIdea.section_id == section.id)
            .order_by(MasterDocIdea.position)
        )
        entries = entries_result.scalars().all()

        for entry in entries:
            idea_result = await db.execute(select(Idea).where(Idea.id == entry.idea_id))
            idea = idea_result.scalar_one_or_none()
            if idea:
                lines.append(idea.full_text)
                lines.append("")

    return "\n".join(lines)


async def _get_section(section_id: str, user_id: str, db: AsyncSession) -> MasterDocSection:
    result = await db.execute(
        select(MasterDocSection)
        .join(MasterDoc, MasterDoc.id == MasterDocSection.master_doc_id)
        .where(MasterDocSection.id == section_id, MasterDoc.user_id == user_id)
    )
    section = result.scalar_one_or_none()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return section
