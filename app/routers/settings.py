from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.workspace_settings import WorkspaceSettings
from app.services.ai_service import validate_api_key

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsOut(BaseModel):
    workspace_name: str
    project_context: Optional[str]
    default_priority: str
    selected_model: str
    similarity_threshold: float
    has_anthropic_key: bool
    has_openai_key: bool
    anthropic_key_valid: Optional[bool]
    openai_key_valid: Optional[bool]


async def _get_or_create_settings(user_id: str, db: AsyncSession) -> WorkspaceSettings:
    result = await db.execute(select(WorkspaceSettings).where(WorkspaceSettings.user_id == user_id))
    ws = result.scalar_one_or_none()
    if not ws:
        ws = WorkspaceSettings(user_id=user_id)
        db.add(ws)
        await db.commit()
        await db.refresh(ws)
    return ws


@router.get("", response_model=SettingsOut)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = await _get_or_create_settings(current_user.id, db)
    return SettingsOut(
        workspace_name=ws.workspace_name,
        project_context=ws.project_context,
        default_priority=ws.default_priority,
        selected_model=ws.selected_model,
        similarity_threshold=ws.similarity_threshold,
        has_anthropic_key=bool(ws.anthropic_api_key),
        has_openai_key=bool(ws.openai_api_key),
        anthropic_key_valid=ws.anthropic_key_valid,
        openai_key_valid=ws.openai_key_valid,
    )


class SettingsUpdate(BaseModel):
    workspace_name: Optional[str] = None
    project_context: Optional[str] = None
    default_priority: Optional[str] = None
    selected_model: Optional[str] = None
    similarity_threshold: Optional[float] = None
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None


@router.patch("")
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ws = await _get_or_create_settings(current_user.id, db)

    if body.workspace_name is not None:
        ws.workspace_name = body.workspace_name
    if body.project_context is not None:
        ws.project_context = body.project_context
    if body.default_priority is not None:
        ws.default_priority = body.default_priority
    if body.selected_model is not None:
        ws.selected_model = body.selected_model
    if body.similarity_threshold is not None:
        if not 0.5 <= body.similarity_threshold <= 1.0:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Threshold must be between 0.5 and 1.0")
        ws.similarity_threshold = body.similarity_threshold
    if body.anthropic_api_key is not None:
        ws.anthropic_api_key = body.anthropic_api_key
        ws.anthropic_key_valid = None  # reset until validated
    if body.openai_api_key is not None:
        ws.openai_api_key = body.openai_api_key
        ws.openai_key_valid = None

    await db.commit()
    return {"message": "Settings saved"}


@router.post("/validate-key")
async def validate_key(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    provider = body.get("provider", "anthropic")
    ws = await _get_or_create_settings(current_user.id, db)

    if provider == "anthropic":
        key = ws.anthropic_api_key
        if not key:
            return {"valid": False, "error": "No API key saved"}
        is_valid = await validate_api_key(key)
        ws.anthropic_key_valid = is_valid
    else:
        return {"valid": False, "error": "Unknown provider"}

    await db.commit()
    return {
        "valid": is_valid,
        "provider": provider,
        "message": "API key is valid" if is_valid else "API key is invalid or has no access",
    }
