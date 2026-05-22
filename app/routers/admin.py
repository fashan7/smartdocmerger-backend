from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.database import get_db
from app.core.deps import get_current_user, require_admin
from app.models.user import User
from app.models.workspace_settings import WorkspaceSettings
from app.models.document import Document
from app.models.idea import Idea
from app.models.notification import Notification, NotificationType
from app.core.security import hash_password, create_access_token

router = APIRouter(prefix="/admin", tags=["admin"])


def _user_out(user: User, doc_count: int = 0, idea_count: int = 0) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
        "doc_count": doc_count,
        "idea_count": idea_count,
    }


# ── List all users ──────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()

    items = []
    for user in users:
        doc_result = await db.execute(
            select(func.count()).select_from(Document).where(Document.user_id == user.id)
        )
        idea_result = await db.execute(
            select(func.count()).select_from(Idea).where(Idea.user_id == user.id)
        )
        items.append(_user_out(
            user,
            doc_count=doc_result.scalar() or 0,
            idea_count=idea_result.scalar() or 0,
        ))

    return {
        "items": items,
        "total": len(items),
    }


# ── Create user (invite) ─────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    send_welcome: bool = True


@router.post("/users", status_code=201)
async def create_user(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = User(
        email=body.email,
        full_name=body.full_name.strip(),
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()

    # Default workspace settings
    ws = WorkspaceSettings(user_id=user.id)
    db.add(ws)

    # Welcome notification
    if body.send_welcome:
        notif = Notification(
            user_id=user.id,
            type=NotificationType.PROCESSING_COMPLETE,
            title="Welcome to SmartDocMerger",
            body=f"Your account was created by {admin.full_name}. Upload your first document to get started.",
            link="/dashboard",
        )
        db.add(notif)

    await db.commit()
    await db.refresh(user)

    return {
        **_user_out(user),
        "message": f"Account created for {body.email}",
    }


# ── Get single user ──────────────────────────────────────────────────────────

@router.get("/users/{user_id}")
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    doc_result = await db.execute(
        select(func.count()).select_from(Document).where(Document.user_id == user.id)
    )
    idea_result = await db.execute(
        select(func.count()).select_from(Idea).where(Idea.user_id == user.id)
    )

    return _user_out(
        user,
        doc_count=doc_result.scalar() or 0,
        idea_count=idea_result.scalar() or 0,
    )


# ── Update user ───────────────────────────────────────────────────────────────

class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent admin from deactivating themselves
    if body.is_active is False and user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    if body.full_name is not None:
        user.full_name = body.full_name.strip()

    if body.email is not None and body.email != user.email:
        existing = await db.execute(
            select(User).where(User.email == body.email, User.id != user_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already in use")
        user.email = body.email

    if body.is_active is not None:
        user.is_active = body.is_active

    await db.commit()
    return {"message": "User updated", **_user_out(user)}


# ── Reset user password ──────────────────────────────────────────────────────

class ResetPasswordRequest(BaseModel):
    new_password: str


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"message": f"Password reset for {user.email}"}


# ── Deactivate / reactivate ──────────────────────────────────────────────────

@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    user.is_active = False
    await db.commit()
    return {"message": f"{user.email} deactivated"}


@router.post("/users/{user_id}/reactivate")
async def reactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = True
    await db.commit()
    return {"message": f"{user.email} reactivated"}


# ── Delete user ───────────────────────────────────────────────────────────────

@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    await db.delete(user)
    await db.commit()


# ── Generate one-time login token (for password resets) ──────────────────────

@router.post("/users/{user_id}/generate-token")
async def generate_login_token(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Generates a short-lived login token for a user.
    Admin can send this to a team member who forgot their password
    instead of resetting it themselves.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    from datetime import timedelta
    token = create_access_token(user.id, expires_delta=timedelta(hours=24))

    return {
        "token": token,
        "email": user.email,
        "expires_in": "24 hours",
        "note": "Share this token securely. User can use it to log in once and change their password.",
    }


# ── Admin check ───────────────────────────────────────────────────────────────

@router.get("/me")
async def admin_check(admin: User = Depends(require_admin)):
    """Returns 200 if current user is admin, 403 otherwise."""
    return {
        "is_admin": True,
        "email": admin.email,
        "full_name": admin.full_name,
    }
