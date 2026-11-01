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
from restaurant_management_system.restaurant.services import get_restaurant_name, set_restaurant_name

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SetupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class BootstrapRequest(SetupRequest):
    restaurant_name: str = Field(min_length=1, max_length=160, pattern=r"\S")


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
    is_active: bool = True
    restaurant_name: str | None = None

    model_config = {"from_attributes": True}


class StaffUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class StatusOut(BaseModel):
    has_users: bool


async def _user_out(session: AsyncSession, user: User) -> UserOut:
    out = UserOut.model_validate(user)
    out.restaurant_name = await get_restaurant_name(session)
    return out


async def _user_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(User)) or 0


@router.get("/status", response_model=StatusOut)
async def auth_status(session: AsyncSession = Depends(get_session)) -> StatusOut:
    return StatusOut(has_users=await _user_count(session) > 0)


@router.post("/bootstrap", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def bootstrap_owner(
    body: BootstrapRequest,
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
    await set_restaurant_name(session, body.restaurant_name)
    await session.commit()
    token = create_access_token(user.id, user.role, settings)
    return TokenOut(access_token=token, user=await _user_out(session, user))


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
    return TokenOut(access_token=token, user=await _user_out(session, user))


@router.get("/me", response_model=UserOut)
async def me(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> UserOut:
    return await _user_out(session, user)


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


@router.get(
    "/users",
    response_model=list[UserOut],
    dependencies=[Depends(require_roles(Role.OWNER))],
)
async def list_staff(session: AsyncSession = Depends(get_session)) -> list[User]:
    return list(await session.scalars(select(User).order_by(User.id)))


async def _active_owner_count(session: AsyncSession) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == Role.OWNER.value, User.is_active.is_(True))
        )
        or 0
    )


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_staff(
    user_id: int,
    body: StaffUpdate,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_roles(Role.OWNER)),
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")

    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    loses_owner = user.role == Role.OWNER.value and user.is_active and (
        changes.get("is_active") is False
        or ("role" in changes and changes["role"] != Role.OWNER)
    )
    if loses_owner:
        if user.id == actor.id:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "You cannot remove your own owner access"
            )
        if await _active_owner_count(session) <= 1:
            raise HTTPException(status.HTTP_409_CONFLICT, "At least one owner is required")
    if user.id == actor.id and changes.get("is_active") is False:
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot deactivate yourself")

    if "role" in changes:
        changes["role"] = changes["role"].value
    for field, value in changes.items():
        setattr(user, field, value)
    await session.commit()
    return user


@router.post(
    "/users/{user_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles(Role.OWNER))],
)
async def reset_staff_password(
    user_id: int, body: PasswordReset, session: AsyncSession = Depends(get_session)
) -> None:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")
    user.password_hash = await hash_password(body.password)
    await session.commit()
