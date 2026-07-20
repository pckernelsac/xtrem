import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.bicicleta import Bicicleta
from app.models.cliente import Cliente
from app.models.ficha import ETIQUETAS_ESTADO, ETIQUETAS_SERVICIO, Ficha
from app.models.user import User
from app.schemas.bicicleta import (
    BicicletaCreate,
    BicicletaDetail,
    BicicletaOut,
    BicicletaPage,
    BicicletaUpdate,
    EventoHistorial,
)

router = APIRouter(prefix="/bicicletas", tags=["bicicletas"])


def _get_cliente_or_422(db: Session, cliente_id: uuid.UUID) -> Cliente:
    cliente = db.get(Cliente, cliente_id)
    if cliente is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El cliente indicado no existe",
        )
    return cliente


def _assert_serie_libre(db: Session, serie: str | None, exclude_id: uuid.UUID | None = None) -> None:
    if not serie:
        return
    stmt = select(Bicicleta).where(Bicicleta.numero_serie == serie)
    if exclude_id:
        stmt = stmt.where(Bicicleta.id != exclude_id)
    existente = db.scalar(stmt)
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El N° de serie {serie} ya está registrado a nombre de "
            f"{existente.cliente.nombre}",
        )


@router.get("", response_model=BicicletaPage)
def list_bicicletas(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("bicicletas.ver")),
    search: str | None = Query(default=None, description="Marca, modelo, serie o cliente"),
    cliente_id: uuid.UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> BicicletaPage:
    stmt = select(Bicicleta).join(Cliente)

    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Bicicleta.marca).like(like),
                func.lower(func.coalesce(Bicicleta.modelo, "")).like(like),
                func.lower(func.coalesce(Bicicleta.numero_serie, "")).like(like),
                func.lower(Cliente.nombre).like(like),
                func.lower(Cliente.numero_documento).like(like),
            )
        )
    if cliente_id:
        stmt = stmt.where(Bicicleta.cliente_id == cliente_id)
    if is_active is not None:
        stmt = stmt.where(Bicicleta.is_active == is_active)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Cliente.nombre, Bicicleta.marca)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()

    return BicicletaPage(
        items=[BicicletaOut.model_validate(b) for b in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{bicicleta_id}", response_model=BicicletaDetail)
def get_bicicleta(
    bicicleta_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("bicicletas.ver")),
) -> BicicletaDetail:
    bici = db.get(Bicicleta, bicicleta_id)
    if bici is None:
        raise HTTPException(status_code=404, detail="Bicicleta no encontrada")

    # Feed de historial: alta de la bici + sus fichas de taller.
    # Las ventas de repuestos (Fase 5) se sumarán a esta misma lista.
    historial = [
        EventoHistorial(
            fecha=bici.created_at,
            tipo="registro",
            titulo="Bicicleta registrada",
            detalle=f"Asociada a {bici.cliente.nombre}",
        )
    ]

    fichas = db.scalars(
        select(Ficha).where(Ficha.bicicleta_id == bici.id).order_by(Ficha.fecha_recepcion)
    ).unique().all()

    for f in fichas:
        servicios = ", ".join(ETIQUETAS_SERVICIO.get(s, s) for s in (f.servicios or []))
        historial.append(
            EventoHistorial(
                fecha=f.fecha_recepcion,
                tipo="ficha",
                titulo=f"Ficha N° {f.numero} · {ETIQUETAS_ESTADO[f.estado.value]}",
                detalle=servicios or f.servicio_otro or "Sin servicios marcados",
                referencia_id=f.id,
            )
        )
        if f.fecha_entrega:
            historial.append(
                EventoHistorial(
                    fecha=f.fecha_entrega,
                    tipo="entrega",
                    titulo=f"Entregada · Ficha N° {f.numero}",
                    detalle=(
                        f"Repuestos por S/ {f.total_repuestos:,.2f}"
                        if f.repuestos
                        else "Sin repuestos"
                    ),
                    referencia_id=f.id,
                )
            )

    historial.sort(key=lambda e: e.fecha)
    return BicicletaDetail.model_validate(bici).model_copy(update={"historial": historial})


@router.post("", response_model=BicicletaOut, status_code=status.HTTP_201_CREATED)
def create_bicicleta(
    data: BicicletaCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("bicicletas.crear")),
) -> BicicletaOut:
    _get_cliente_or_422(db, data.cliente_id)
    _assert_serie_libre(db, data.numero_serie)

    bici = Bicicleta(**data.model_dump())
    db.add(bici)
    db.commit()
    db.refresh(bici)
    return BicicletaOut.model_validate(bici)


@router.patch("/{bicicleta_id}", response_model=BicicletaOut)
def update_bicicleta(
    bicicleta_id: uuid.UUID,
    data: BicicletaUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("bicicletas.editar")),
) -> BicicletaOut:
    bici = db.get(Bicicleta, bicicleta_id)
    if bici is None:
        raise HTTPException(status_code=404, detail="Bicicleta no encontrada")

    changes = data.model_dump(exclude_unset=True)

    if "cliente_id" in changes:
        _get_cliente_or_422(db, changes["cliente_id"])
    if "numero_serie" in changes:
        _assert_serie_libre(db, changes["numero_serie"], exclude_id=bici.id)

    for field, value in changes.items():
        setattr(bici, field, value)

    db.commit()
    db.refresh(bici)
    return BicicletaOut.model_validate(bici)


@router.delete("/{bicicleta_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_bicicleta(
    bicicleta_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("bicicletas.eliminar")),
) -> None:
    """Borrado definitivo, sólo para la bici que nunca entró al taller.

    Archivar (`PATCH {is_active: false}`) es lo habitual —la bici vendida o
    que ya no vuelve— y conserva su historial de fichas.
    """
    bici = db.get(Bicicleta, bicicleta_id)
    if bici is None:
        raise HTTPException(status_code=404, detail="Bicicleta no encontrada")

    fichas = (
        db.scalar(select(func.count()).select_from(Ficha).where(Ficha.bicicleta_id == bicicleta_id))
        or 0
    )
    if fichas:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Esta bicicleta tiene {fichas} ficha(s) de taller; archívala en vez "
                "de eliminarla para no romper su historial"
            ),
        )

    db.delete(bici)
    db.commit()
