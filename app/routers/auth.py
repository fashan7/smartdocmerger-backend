from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from app.database import get_db
from app.models.user import User
from app.models.workspace_settings import WorkspaceSettings
from app.core.security import hash_password, verify_password, create_access_token
from app.core.deps import get_current_user
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    full_name: str


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str

    class Config:
        from_attributes = True


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if settings.ENVIRONMENT != "development":
        raise HTTPException(status_code=403, detail="Public registration is closed. Contact your admin.")
    # Check duplicate email
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

    # Create default workspace settings
    ws = WorkspaceSettings(user_id=user.id)
    db.add(ws)

    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return AuthResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account is inactive")

    token = create_access_token(user.id)
    return AuthResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me")
async def update_profile(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if "full_name" in body:
        current_user.full_name = body["full_name"].strip()
    if "email" in body:
        existing = await db.execute(
            select(User).where(User.email == body["email"], User.id != current_user.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = body["email"]
    await db.commit()
    return {"message": "Profile updated"}


@router.post("/change-password")
async def change_password(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(body.get("current_password", ""), current_user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect current password")

    new_password = body.get("new_password", "")
    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")

    current_user.password_hash = hash_password(new_password)
    await db.commit()
    return {"message": "Password changed"}


@router.delete("/account")
async def delete_account(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.get("confirmation") != "DELETE":
        raise HTTPException(status_code=400, detail="Type DELETE to confirm")
    await db.delete(current_user)
    await db.commit()
    return {"message": "Account deleted"}
