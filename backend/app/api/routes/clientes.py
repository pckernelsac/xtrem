import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.config import settings
from app.db.session import get_db
from app.models.bicicleta import Bicicleta
from app.models.cliente import Cliente, TipoDocumento
from app.models.ficha import Ficha
from app.models.user import User
from app.models.venta import Venta
from app.services.consulta_documento import consultar_dni, consultar_ruc
from app.schemas.cliente import (
    ClienteCreate,
    ClienteDetail,
    ClienteOut,
    ClientePage,
    ClienteUpdate,
    LONGITUD_DOCUMENTO,
)

router = APIRouter(prefix="/clientes", tags=["clientes"])


def _bicis_count(db: Session, cliente_id: uuid.UUID) -> int:
    return db.scalar(select(func.count(Bicicleta.id)).where(Bicicleta.cliente_id == cliente_id)) or 0


def _to_out(db: Session, c: Cliente) -> ClienteOut:
    return ClienteOut.model_validate(c).model_copy(
        update={"bicicletas_count": _bicis_count(db, c.id)}
    )


def _assert_documento_libre(
    db: Session,
    tipo: TipoDocumento,
    numero: str,
    exclude_id: uuid.UUID | None = None,
) -> None:
    stmt = select(Cliente).where(
        Cliente.tipo_documento == tipo, Cliente.numero_documento == numero
    )
    if exclude_id:
        stmt = stmt.where(Cliente.id != exclude_id)
    if db.scalar(stmt):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un cliente con {tipo.value} {numero}",
        )


@router.get("/consulta-documento/disponible")
def consulta_disponible(
    _: User = Depends(require_permission("clientes.ver")),
) -> dict[str, bool]:
    """Indica si el autocompletado por DNI/RUC está configurado (hay token)."""
    return {"disponible": settings.consulta_documento_disponible}


@router.get("/consulta-documento")
def consulta_documento(
    tipo: TipoDocumento = Query(description="DNI o RUC"),
    numero: str = Query(min_length=8, max_length=11),
    _: User = Depends(require_permission("clientes.crear")),
) -> dict:
    """Trae el nombre desde RENIEC (DNI) o la razón social desde SUNAT (RUC).

    Sólo para DNI y RUC; los demás tipos de documento no tienen padrón público.
    """
    if tipo is TipoDocumento.DNI:
        return consultar_dni(numero)
    if tipo is TipoDocumento.RUC:
        return consultar_ruc(numero)
    raise HTTPException(
        status_code=422,
        detail="Sólo se puede consultar DNI (RENIEC) o RUC (SUNAT)",
    )


@router.get("", response_model=ClientePage)
def list_clientes(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("clientes.ver")),
    search: str | None = Query(default=None, description="Nombre, documento, teléfono o correo"),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> ClientePage:
    stmt = select(Cliente)

    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Cliente.nombre).like(like),
                func.lower(Cliente.numero_documento).like(like),
                func.lower(func.coalesce(Cliente.telefono, "")).like(like),
                func.lower(func.coalesce(Cliente.email, "")).like(like),
            )
        )
    if is_active is not None:
        stmt = stmt.where(Cliente.is_active == is_active)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Cliente.nombre).offset((page - 1) * page_size).limit(page_size)
    ).all()

    return ClientePage(
        items=[_to_out(db, c) for c in rows], total=total, page=page, page_size=page_size
    )


@router.get("/{cliente_id}", response_model=ClienteDetail)
def get_cliente(
    cliente_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("clientes.ver")),
) -> ClienteDetail:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    return ClienteDetail.model_validate(cliente).model_copy(
        update={"bicicletas_count": len(cliente.bicicletas)}
    )


@router.post("", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
def create_cliente(
    data: ClienteCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("clientes.crear")),
) -> ClienteOut:
    _assert_documento_libre(db, data.tipo_documento, data.numero_documento)

    cliente = Cliente(**data.model_dump())
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return _to_out(db, cliente)


@router.patch("/{cliente_id}", response_model=ClienteOut)
def update_cliente(
    cliente_id: uuid.UUID,
    data: ClienteUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("clientes.editar")),
) -> ClienteOut:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    changes = data.model_dump(exclude_unset=True)

    # El tipo y el número se validan juntos: cambiar sólo uno de los dos
    # puede producir una combinación inválida (ej. RUC con 8 dígitos).
    if "tipo_documento" in changes or "numero_documento" in changes:
        tipo = changes.get("tipo_documento", cliente.tipo_documento)
        numero = str(changes.get("numero_documento", cliente.numero_documento)).strip().upper()

        if not numero.isalnum():
            raise HTTPException(
                status_code=422, detail="El número de documento sólo admite letras y números"
            )
        minimo, maximo = LONGITUD_DOCUMENTO[tipo]
        if not minimo <= len(numero) <= maximo:
            esperado = f"{minimo}" if minimo == maximo else f"entre {minimo} y {maximo}"
            raise HTTPException(
                status_code=422,
                detail=f"Un {tipo.value} debe tener {esperado} caracteres (recibido: {len(numero)})",
            )
        if tipo in (TipoDocumento.DNI, TipoDocumento.RUC) and not numero.isdigit():
            raise HTTPException(status_code=422, detail=f"Un {tipo.value} sólo admite dígitos")

        _assert_documento_libre(db, tipo, numero, exclude_id=cliente.id)
        changes["tipo_documento"] = tipo
        changes["numero_documento"] = numero

    for field, value in changes.items():
        setattr(cliente, field, value)

    # Archivar al dueño archiva sus bicicletas: no tiene sentido que sigan
    # apareciendo en el taller sin cliente al que devolvérselas. Restaurar NO
    # las devuelve en bloque, para no resucitar una que se archivó aparte.
    if changes.get("is_active") is False:
        for bici in cliente.bicicletas:
            bici.is_active = False

    db.commit()
    db.refresh(cliente)
    return _to_out(db, cliente)


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_cliente(
    cliente_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("clientes.eliminar")),
) -> None:
    """Borrado definitivo, sólo para el registro que nunca se usó.

    Archivar (`PATCH {is_active: false}`) es la vía normal: el cliente sale de
    los buscadores pero sus fichas y ventas lo siguen nombrando. Aquí se borra
    de verdad, y por eso se niega en cuanto exista un documento a su nombre.
    """
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    fichas = db.scalar(select(func.count()).select_from(Ficha).where(Ficha.cliente_id == cliente_id)) or 0
    ventas = db.scalar(select(func.count()).select_from(Venta).where(Venta.cliente_id == cliente_id)) or 0
    if fichas or ventas:
        usos = " y ".join(
            parte
            for parte in (
                f"{fichas} ficha(s)" if fichas else "",
                f"{ventas} venta(s)" if ventas else "",
            )
            if parte
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{cliente.nombre} tiene {usos} a su nombre; archívalo en vez de "
                "eliminarlo para no romper esos documentos"
            ),
        )

    # Sus bicicletas cuelgan con ON DELETE CASCADE. Sólo se llega aquí si
    # ninguna tiene ficha, así que no hay historial que se pierda.
    db.delete(cliente)
    db.commit()
