import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.document import Document, DocumentStatus
from app.models.idea import Idea
from app.services.file_parser import parse_file, count_words
from app.services.processor import process_document

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentOut(BaseModel):
    id: str
    name: str
    file_type: str
    tags: list
    priority: str
    status: str
    processing_step: Optional[str]
    error_message: Optional[str]
    idea_count: int
    duplicate_count: int
    word_count: int
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_doc(cls, doc: Document) -> "DocumentOut":
        return cls(
            id=doc.id,
            name=doc.name,
            file_type=doc.file_type,
            tags=doc.tags or [],
            priority=doc.priority,
            status=doc.status,
            processing_step=doc.processing_step,
            error_message=doc.error_message,
            idea_count=doc.idea_count,
            duplicate_count=doc.duplicate_count,
            word_count=doc.word_count,
            created_at=doc.created_at.isoformat(),
            updated_at=doc.updated_at.isoformat(),
        )


@router.post("/upload", status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    tags: str = Form("[]"),
    priority: str = Form("normal"),
    include_in_context: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    text, file_type = await parse_file(file)
    doc_name = name or file.filename or "Untitled"

    try:
        parsed_tags = json.loads(tags)
    except Exception:
        parsed_tags = []

    doc = Document(
        user_id=current_user.id,
        name=doc_name,
        file_type=file_type,
        original_text=text,
        tags=parsed_tags,
        priority=priority,
        include_in_context=include_in_context,
        status=DocumentStatus.PROCESSING,
        processing_step="uploading",
        word_count=count_words(text),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    background_tasks.add_task(process_document, doc.id, current_user.id)
    return DocumentOut.from_orm_doc(doc)


class PasteRequest(BaseModel):
    name: str
    content: str
    file_type: str = "txt"  # txt or md
    tags: list = []
    priority: str = "normal"
    include_in_context: bool = False


@router.post("/paste", status_code=201)
async def paste_document(
    body: PasteRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Document name is required")

    doc = Document(
        user_id=current_user.id,
        name=body.name.strip(),
        file_type=body.file_type,
        original_text=body.content,
        tags=body.tags,
        priority=body.priority,
        include_in_context=body.include_in_context,
        status=DocumentStatus.PROCESSING,
        processing_step="uploading",
        word_count=count_words(body.content),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    background_tasks.add_task(process_document, doc.id, current_user.id)
    return DocumentOut.from_orm_doc(doc)


@router.get("")
async def list_documents(
    tag: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Document).where(Document.user_id == current_user.id)

    if tag:
        query = query.where(Document.tags.contains([tag]))
    if status:
        query = query.where(Document.status == status)

    query = query.order_by(Document.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    docs = result.scalars().all()

    count_result = await db.execute(
        select(func.count()).select_from(Document).where(Document.user_id == current_user.id)
    )
    total = count_result.scalar()

    return {
        "items": [DocumentOut.from_orm_doc(d) for d in docs],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Load ideas
    ideas_result = await db.execute(
        select(Idea)
        .where(Idea.document_id == document_id)
        .order_by(Idea.section_index)
    )
    ideas = ideas_result.scalars().all()

    return {
        **DocumentOut.from_orm_doc(doc).model_dump(),
        "original_text": doc.original_text,
        "ideas": [
            {
                "id": i.id,
                "summary": i.summary,
                "full_text": i.full_text,
                "section_title": i.section_title,
                "section_index": i.section_index,
                "status": i.status,
                "priority": i.priority,
                "word_count": i.word_count,
            }
            for i in ideas
        ],
    }


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.delete(doc)
    await db.commit()


@router.post("/{document_id}/reprocess")
async def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == current_user.id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete existing ideas
    await db.execute(delete(Idea).where(Idea.document_id == document_id))

    doc.status = DocumentStatus.PROCESSING
    doc.processing_step = "uploading"
    doc.error_message = None
    doc.idea_count = 0
    doc.duplicate_count = 0
    await db.commit()

    background_tasks.add_task(process_document, doc.id, current_user.id)
    return {"message": "Reprocessing started"}


@router.get("/{document_id}/stream")
async def stream_progress(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """SSE endpoint — polls document status every second and streams to frontend."""

    async def event_generator():
        step_order = ["uploading", "chunking", "extracting", "detecting", "done", "failed"]
        last_step = None

        for _ in range(120):  # max 2 minutes
            result = await db.execute(
                select(Document).where(
                    Document.id == document_id,
                    Document.user_id == current_user.id,
                )
            )
            doc = result.scalar_one_or_none()

            if not doc:
                yield f"data: {json.dumps({'error': 'Document not found'})}\n\n"
                break

            current_step = doc.processing_step or "uploading"

            if current_step != last_step:
                last_step = current_step
                payload = {
                    "step": current_step,
                    "status": doc.status,
                    "idea_count": doc.idea_count,
                    "duplicate_count": doc.duplicate_count,
                    "error": doc.error_message,
                }
                yield f"data: {json.dumps(payload)}\n\n"

            if current_step in ("done", "failed"):
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
