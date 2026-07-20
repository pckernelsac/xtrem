import uuid

from pydantic import BaseModel, ConfigDict, Field


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    module: str
    description: str


class RoleBase(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    description: str | None = None


class RoleCreate(RoleBase):
    permission_codes: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=64)
    description: str | None = None
    permission_codes: list[str] | None = None


class RoleOut(RoleBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    is_system: bool
    permission_codes: list[str]
    users_count: int = 0
