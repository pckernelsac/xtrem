import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models.auditoria import RegistroAuditoria
from app.models.user import User
from app.services.notificaciones import calcular

router = APIRouter(tags=["sistema"])


# --------------------------------------------------------------- Notificaciones
class Notificacion(BaseModel):
    tipo: str
    nivel: str
    titulo: str
    detalle: str
    enlace: str
    cantidad: int


class NotificacionesOut(BaseModel):
    total: int
    alertas: list[Notificacion]


@router.get("/notificaciones", response_model=NotificacionesOut, tags=["sistema"])
def notificaciones(
    db: Session = Depends(get_db),
    usuario: User = Depends(get_current_user),
) -> NotificacionesOut:
    """Alertas accionables del negocio, filtradas por los permisos del usuario."""
    alertas = calcular(db, usuario)
    return NotificacionesOut(
        total=sum(a["cantidad"] for a in alertas),
        alertas=[Notificacion(**a) for a in alertas],
    )


# --------------------------------------------------------------- Auditoría
class RegistroOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    usuario_email: str | None
    metodo: str
    ruta: str
    entidad: str | None
    status_code: int
    duracion_ms: int
    ip: str | None

    @field_validator("ip", mode="before")
    @classmethod
    def ip_a_texto(cls, v):
        # psycopg entrega la columna INET como objeto ipaddress, no como str.
        return str(v) if v is not None else None


class AuditoriaPage(BaseModel):
    items: list[RegistroOut]
    total: int
    page: int
    page_size: int


@router.get("/auditoria", response_model=AuditoriaPage, tags=["auditoría"])
def auditoria(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("auditoria.ver")),
    entidad: str | None = Query(default=None, description="Filtra por módulo"),
    usuario_email: str | None = Query(default=None),
    solo_errores: bool = Query(default=False, description="Sólo respuestas 4xx/5xx"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> AuditoriaPage:
    stmt = select(RegistroAuditoria)

    if entidad:
        stmt = stmt.where(RegistroAuditoria.entidad == entidad)
    if usuario_email:
        stmt = stmt.where(
            func.lower(RegistroAuditoria.usuario_email).like(f"%{usuario_email.lower()}%")
        )
    if solo_errores:
        stmt = stmt.where(RegistroAuditoria.status_code >= 400)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(RegistroAuditoria.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return AuditoriaPage(
        items=[RegistroOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
