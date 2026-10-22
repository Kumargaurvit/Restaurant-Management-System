from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurant_management_system.auth.dependencies import get_current_user, require_roles
from restaurant_management_system.auth.models import Role, User
from restaurant_management_system.auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from restaurant_management_system.config import Settings, get_settings
from restaurant_management_system.db.session import get_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SetupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class StaffCreate(SetupRequest):
    role: Role


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class StatusOut(BaseModel):
    has_users: bool


async def _user_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(User)) or 0


@router.get("/status", response_model=StatusOut)
async def auth_status(session: AsyncSession = Depends(get_session)) -> StatusOut:
    return StatusOut(has_users=await _user_count(session) > 0)


@router.post("/bootstrap", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def bootstrap_owner(
    body: SetupRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TokenOut:
    """Create the first owner account. Only works while no users exist."""
    if await _user_count(session) > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Setup already completed")

    user = User(
        name=body.name,
        email=body.email.lower(),
        password_hash=await hash_password(body.password),
        role=Role.OWNER.value,
    )
    session.add(user)
    await session.commit()
    token = create_access_token(user.id, user.role, settings)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> TokenOut:
    user = await session.scalar(select(User).where(User.email == body.email.lower()))
    valid = (
        user is not None
        and user.is_active
        and await verify_password(body.password, user.password_hash)
    )
    if not valid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    token = create_access_token(user.id, user.role, settings)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(Role.OWNER))],
)
async def create_staff(
    body: StaffCreate, session: AsyncSession = Depends(get_session)
) -> User:
    email = body.email.lower()
    if await session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already in use")

    user = User(
        name=body.name,
        email=email,
        password_hash=await hash_password(body.password),
        role=body.role.value,
    )
    session.add(user)
    await session.commit()
    return user
