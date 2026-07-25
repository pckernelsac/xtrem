from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.passwords import validar_password


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    #: El tope de 72 no es arbitrario: bcrypt ignora lo que pase de ahí, y
    #: aceptar más daría la falsa impresión de que una clave larguísima protege.
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def _politica(cls, v: str) -> str:
        return validar_password(v)
