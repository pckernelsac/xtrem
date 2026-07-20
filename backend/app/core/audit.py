"""Middleware de auditoría: registra cada petición que cambia estado.

Se sitúa en la capa HTTP para no tener que instrumentar endpoint por endpoint:
toda operación POST/PATCH/PUT/DELETE queda registrada con su actor y resultado.
El actor se resuelve decodificando el JWT del header; nunca se lee el cuerpo de
la petición, así no se filtran contraseñas ni firmas al registro.
"""

import time
import uuid

from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.security import decode_token
from app.db.session import SessionLocal
from app.models.auditoria import RegistroAuditoria
from app.models.user import User

MUTANTES = {"POST", "PUT", "PATCH", "DELETE"}

#: Rutas que no aportan al rastro (el refresco de token es ruido de fondo).
IGNORAR = {"/api/v1/auth/refresh"}


def _entidad_de(ruta: str) -> str | None:
    """Extrae el módulo de la ruta: /api/v1/ventas/<id> -> 'ventas'."""
    partes = [p for p in ruta.split("/") if p]
    if len(partes) >= 3 and partes[0] == "api":
        return partes[2]
    if partes:
        return partes[0]
    return None


def _actor_id(request: Request) -> uuid.UUID | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    payload = decode_token(auth[7:], expected_type="access")
    if payload is None:
        return None
    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        return None


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method not in MUTANTES or request.url.path in IGNORAR:
            return await call_next(request)

        inicio = time.perf_counter()
        response = await call_next(request)
        duracion = int((time.perf_counter() - inicio) * 1000)

        # El registro nunca debe tumbar la petición del usuario: si falla el
        # log, se traga el error y se sirve la respuesta igual.
        try:
            usuario_id = _actor_id(request)
            with SessionLocal() as db:
                email = None
                if usuario_id is not None:
                    email = db.scalar(
                        select(User.email).where(User.id == usuario_id)
                    )
                db.add(
                    RegistroAuditoria(
                        usuario_id=usuario_id,
                        usuario_email=email,
                        metodo=request.method,
                        ruta=request.url.path,
                        entidad=_entidad_de(request.url.path),
                        status_code=response.status_code,
                        duracion_ms=duracion,
                        ip=request.client.host if request.client else None,
                    )
                )
                db.commit()
        except Exception:  # noqa: BLE001 - la auditoría no interrumpe el flujo
            pass

        return response
