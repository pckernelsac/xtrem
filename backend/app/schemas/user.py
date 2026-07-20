import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RoleBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    dni: str | None = Field(default=None, max_length=12)
    phone: str | None = Field(default=None, max_length=20)
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=72)
    role_id: uuid.UUID


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    dni: str | None = Field(default=None, max_length=12)
    phone: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None
    role_id: uuid.UUID | None = None
    password: str | None = Field(default=None, min_length=8, max_length=72)


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: RoleBrief
    last_login_at: datetime | None
    created_at: datetime


class MeOut(UserOut):
    """El usuario autenticado incluye sus permisos para que el front pinte la UI."""

    permission_codes: list[str]


class UserPage(BaseModel):
    items: list[UserOut]
    total: int
    page: int
    page_size: int
