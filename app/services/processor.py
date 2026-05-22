"""
Document processing pipeline.
Runs as a FastAPI BackgroundTask.
Progress is written to the document's processing_step column.
SSE endpoint polls this column to stream progress to frontend.

Pipeline:
1. Parse (already done before this — text is in DB)
2. Chunk document into sections
3. Extract ideas via Claude
4. Run TF-IDF similarity across ALL user ideas
5. Verify candidate pairs with Claude
6. Create IdeaPair records
7. Create notifications
8. Update document status
"""

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.database import AsyncSessionLocal
from app.models.document import Document, DocumentStatus
from app.models.idea import Idea, IdeaStatus
from app.models.idea_pair import IdeaPair, PairStatus
from app.models.notification import Notification, NotificationType
from app.models.workspace_settings import WorkspaceSettings
from app.services.chunker import chunk_document
from app.services.ai_service import extract_ideas_from_chunks, verify_similarity_pair
from app.services.similarity import find_similar_pairs, compute_similarity_score
from app.services.file_parser import count_words


async def _set_step(db: AsyncSession, document_id: str, step: str):
    await db.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(processing_step=step)
    )
    await db.commit()


async def process_document(document_id: str, user_id: str):
    """Entry point — called as BackgroundTask after document is created."""
    async with AsyncSessionLocal() as db:
        try:
            await _run_pipeline(db, document_id, user_id)
        except Exception as e:
            async with AsyncSessionLocal() as error_db:
                await error_db.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(
                        status=DocumentStatus.FAILED,
                        processing_step="failed",
                        error_message=str(e)[:500],
                    )
                )
                await error_db.commit()

                # Failure notification
                notif = Notification(
                    user_id=user_id,
                    type=NotificationType.PROCESSING_FAILED,
                    title="Processing failed",
                    body=f"Could not process document: {str(e)[:100]}",
                    link=f"/documents/{document_id}",
                    reference_id=document_id,
                )
                error_db.add(notif)
                await error_db.commit()


async def _run_pipeline(db: AsyncSession, document_id: str, user_id: str):
    # --- Load document ---
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        return

    # --- Load user API key ---
    settings_result = await db.execute(
        select(WorkspaceSettings).where(WorkspaceSettings.user_id == user_id)
    )
    workspace = settings_result.scalar_one_or_none()
    api_key = workspace.anthropic_api_key if workspace else None
    project_context = workspace.project_context if workspace else ""
    threshold = workspace.similarity_threshold if workspace else 0.75

    # --- Step 1: Chunk ---
    await _set_step(db, document_id, "chunking")
    chunks = chunk_document(doc.original_text, doc.file_type)
    chunks_data = [{"index": c.index, "title": c.title, "text": c.text} for c in chunks]

    # --- Step 2: Extract ideas ---
    await _set_step(db, document_id, "extracting")
    raw_ideas = await extract_ideas_from_chunks(chunks_data, project_context, api_key, model=workspace.selected_model if workspace else None)

    if not raw_ideas:
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status=DocumentStatus.READY, processing_step="done", idea_count=0)
        )
        await db.commit()
        return

    # --- Save ideas ---
    idea_objects = []
    for raw in raw_ideas:
        idea = Idea(
            document_id=document_id,
            user_id=user_id,
            summary=raw.get("summary", "")[:500],
            full_text=raw.get("full_text", ""),
            section_title=raw.get("section_title", ""),
            section_index=raw.get("section_index", 0),
            word_count=count_words(raw.get("full_text", "")),
            tags=doc.tags,
        )
        db.add(idea)
        idea_objects.append(idea)

    await db.flush()  # get IDs

    # --- Step 3: Detect duplicates ---
    await _set_step(db, document_id, "detecting")

    # Load ALL ideas for this user (cross-document similarity)
    all_ideas_result = await db.execute(
        select(Idea).where(
            Idea.user_id == user_id,
            Idea.status != IdeaStatus.MERGED,
        )
    )
    all_ideas = all_ideas_result.scalars().all()

    ideas_data = [{"id": i.id, "full_text": i.full_text} for i in all_ideas]
    candidate_pairs = find_similar_pairs(ideas_data, threshold=threshold)

    # Filter: only pairs involving the new document's ideas
    new_idea_ids = {i.id for i in idea_objects}
    new_pairs = [
        p for p in candidate_pairs
        if p["idea_a_id"] in new_idea_ids or p["idea_b_id"] in new_idea_ids
    ]

    # Check which pairs already exist
    duplicate_count = 0
    for pair_data in new_pairs:
        # Skip if pair already exists
        existing = await db.execute(
            select(IdeaPair).where(
                (
                    (IdeaPair.idea_a_id == pair_data["idea_a_id"]) &
                    (IdeaPair.idea_b_id == pair_data["idea_b_id"])
                ) | (
                    (IdeaPair.idea_a_id == pair_data["idea_b_id"]) &
                    (IdeaPair.idea_b_id == pair_data["idea_a_id"])
                )
            )
        )
        if existing.scalar_one_or_none():
            continue

        # Claude verification
        idea_a_obj = next((i for i in all_ideas if i.id == pair_data["idea_a_id"]), None)
        idea_b_obj = next((i for i in all_ideas if i.id == pair_data["idea_b_id"]), None)

        if not idea_a_obj or not idea_b_obj:
            continue

        verdict = await verify_similarity_pair(
            idea_a_obj.full_text,
            idea_b_obj.full_text,
            api_key,
            model=workspace.selected_model if workspace else None,
        )

        # Only create pair if Claude also agrees they're similar
        if verdict["concept_match"] >= 60:
            similarity_score = compute_similarity_score(
                verdict["wording_match"],
                verdict["concept_match"],
            )

            pair = IdeaPair(
                user_id=user_id,
                idea_a_id=pair_data["idea_a_id"],
                idea_b_id=pair_data["idea_b_id"],
                tfidf_score=pair_data["tfidf_score"],
                wording_match=verdict["wording_match"],
                concept_match=verdict["concept_match"],
                similarity_score=similarity_score,
                ai_recommendation=verdict["recommendation"],
                ai_reason=verdict["reason"],
                ai_confidence=verdict["confidence"],
                status=PairStatus.PENDING,
            )
            db.add(pair)

            # Mark both ideas as duplicate
            await db.execute(
                update(Idea)
                .where(Idea.id.in_([pair_data["idea_a_id"], pair_data["idea_b_id"]]))
                .values(status=IdeaStatus.DUPLICATE)
            )
            duplicate_count += 1

    # --- Update document counts ---
    final_status = DocumentStatus.HAS_DUPLICATES if duplicate_count > 0 else DocumentStatus.READY
    await db.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(
            status=final_status,
            processing_step="done",
            idea_count=len(idea_objects),
            duplicate_count=duplicate_count,
        )
    )

    # --- Notifications ---
    notif = Notification(
        user_id=user_id,
        type=NotificationType.PROCESSING_COMPLETE,
        title="Document processed",
        body=f"{doc.name} — {len(idea_objects)} ideas extracted, {duplicate_count} duplicates found",
        link=f"/documents/{document_id}",
        reference_id=document_id,
    )
    db.add(notif)

    if duplicate_count > 0:
        merge_notif = Notification(
            user_id=user_id,
            type=NotificationType.DUPLICATES_FOUND,
            title="Duplicates detected",
            body=f"{duplicate_count} new duplicate pair{'s' if duplicate_count > 1 else ''} found",
            link="/merge-queue",
            reference_id=document_id,
        )
        db.add(merge_notif)

    await db.commit()
