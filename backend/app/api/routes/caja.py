import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.fechas import rango_utc
from app.db.session import get_db
from app.models.caja import EstadoCaja, SesionCaja, TipoMovimientoCaja
from app.models.user import User
from app.models.venta import EstadoVenta, Venta
from app.schemas.caja import (
    AbrirCajaIn,
    ArqueoOut,
    CerrarCajaIn,
    MovimientoCajaIn,
    MovimientoCajaOut,
    SesionOut,
    SesionPage,
)
from app.services.caja import (
    abrir_caja,
    cerrar_caja,
    efectivo_esperado,
    registrar_movimiento_caja,
    sesion_abierta,
    totales_por_metodo,
)

router = APIRouter(prefix="/caja", tags=["caja"])


def _arqueo(db: Session, sesion: SesionCaja) -> ArqueoOut:
    ventas = (
        db.scalar(
            select(func.count(Venta.id)).where(
                Venta.sesion_caja_id == sesion.id,
                Venta.estado == EstadoVenta.CONFIRMADA,
            )
        )
        or 0
    )

    # Se parte de SesionOut y se agregan los calculados: validar ArqueoOut
    # directamente contra el ORM falla, porque esos campos no existen en el
    # modelo y `model_copy` corre después de la validación.
    return ArqueoOut(
        **SesionOut.model_validate(sesion).model_dump(),
        efectivo_esperado=efectivo_esperado(db, sesion),
        totales=totales_por_metodo(db, sesion),
        cantidad_ventas=ventas,
        movimientos=[
            MovimientoCajaOut.model_validate(m) for m in reversed(sesion.movimientos)
        ],
    )


@router.get("/actual", response_model=ArqueoOut | None)
def caja_actual(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("caja.ver")),
) -> ArqueoOut | None:
    """La sesión abierta con su arqueo en vivo, o null si la caja está cerrada."""
    sesion = sesion_abierta(db)
    return _arqueo(db, sesion) if sesion else None


@router.get("/sesiones", response_model=SesionPage)
def list_sesiones(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("caja.ver")),
    desde: date | None = Query(default=None, description="Fecha de apertura, inclusive"),
    hasta: date | None = Query(default=None, description="Fecha de apertura, inclusive"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=15, ge=1, le=200),
) -> SesionPage:
    stmt = select(SesionCaja)
    # Días del taller (Lima), no días UTC: una jornada abierta a las 8 p. m.
    # pertenece a ese día, no al siguiente.
    ini, fin = rango_utc(desde, hasta)
    if ini:
        stmt = stmt.where(SesionCaja.fecha_apertura >= ini)
    if fin:
        stmt = stmt.where(SesionCaja.fecha_apertura < fin)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(SesionCaja.fecha_apertura.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return SesionPage(
        items=[SesionOut.model_validate(s) for s in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/sesiones/{sesion_id}", response_model=ArqueoOut)
def get_sesion(
    sesion_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("caja.ver")),
) -> ArqueoOut:
    sesion = db.get(SesionCaja, sesion_id)
    if sesion is None:
        raise HTTPException(status_code=404, detail="Sesión de caja no encontrada")
    return _arqueo(db, sesion)


@router.post("/abrir", response_model=ArqueoOut, status_code=status.HTTP_201_CREATED)
def abrir(
    data: AbrirCajaIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("caja.abrir")),
) -> ArqueoOut:
    sesion = abrir_caja(db, data.monto_inicial, actor.id, data.observaciones)
    db.commit()
    db.refresh(sesion)
    return _arqueo(db, sesion)


@router.post("/cerrar", response_model=ArqueoOut)
def cerrar(
    data: CerrarCajaIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("caja.cerrar")),
) -> ArqueoOut:
    """Cierra con arqueo: se compara lo contado contra lo esperado."""
    sesion = sesion_abierta(db)
    if sesion is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="No hay ninguna caja abierta"
        )

    cerrar_caja(db, sesion, data.monto_declarado, actor.id, data.observaciones)
    db.commit()
    db.refresh(sesion)
    return _arqueo(db, sesion)


@router.post(
    "/movimientos", response_model=MovimientoCajaOut, status_code=status.HTTP_201_CREATED
)
def crear_movimiento(
    data: MovimientoCajaIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("caja.crear")),
):
    """Movimiento manual: retiro a banco, pago a proveedor, ingreso extra."""
    sesion = sesion_abierta(db)
    if sesion is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No hay una caja abierta para registrar el movimiento",
        )

    # Sacar más efectivo del que hay dejaría el cajón en negativo, que es un
    # error de captura y no un estado posible.
    if data.tipo is TipoMovimientoCaja.EGRESO and data.metodo.value == "EFECTIVO":
        disponible = efectivo_esperado(db, sesion)
        if data.monto > disponible:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sólo hay S/ {disponible:.2f} en efectivo en la caja",
            )

    movimiento = registrar_movimiento_caja(
        db,
        sesion,
        data.tipo,
        data.metodo,
        data.monto,
        concepto=data.concepto,
        usuario_id=actor.id,
    )
    db.commit()
    db.refresh(movimiento)
    return movimiento
