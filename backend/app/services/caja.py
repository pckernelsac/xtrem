"""Reglas del cajón: apertura, movimientos y arqueo de cierre."""

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.caja import (
    EstadoCaja,
    METODOS_EFECTIVO,
    MetodoPago,
    MovimientoCaja,
    SesionCaja,
    TipoMovimientoCaja,
)

CERO = Decimal("0.00")


def siguiente_numero_caja(db: Session) -> str:
    valor = db.scalar(text("SELECT nextval('caja_numero_seq')"))
    return f"C-{valor:06d}"


def sesion_abierta(db: Session) -> SesionCaja | None:
    """La sesión abierta, si la hay.

    Hay un solo cajón físico en la tienda, así que sólo puede haber una sesión
    abierta a la vez. Permitir varias haría que dos cobros en efectivo se
    contaran en arqueos distintos.
    """
    return db.scalar(select(SesionCaja).where(SesionCaja.estado == EstadoCaja.ABIERTA))


def exigir_sesion_abierta(db: Session) -> SesionCaja:
    sesion = sesion_abierta(db)
    if sesion is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No hay una caja abierta. Abre la caja antes de cobrar en efectivo.",
        )
    return sesion


def abrir_caja(
    db: Session, monto_inicial: Decimal, usuario_id: uuid.UUID | None, observaciones: str | None
) -> SesionCaja:
    if sesion_abierta(db) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya hay una caja abierta; ciérrala antes de abrir otra",
        )
    if monto_inicial < CERO:
        raise HTTPException(status_code=422, detail="El monto inicial no puede ser negativo")

    sesion = SesionCaja(
        numero=siguiente_numero_caja(db),
        monto_inicial=monto_inicial,
        usuario_apertura_id=usuario_id,
        observaciones=observaciones,
    )
    db.add(sesion)
    db.flush()
    return sesion


def registrar_movimiento_caja(
    db: Session,
    sesion: SesionCaja,
    tipo: TipoMovimientoCaja,
    metodo: MetodoPago,
    monto: Decimal,
    concepto: str,
    usuario_id: uuid.UUID | None = None,
    referencia: str | None = None,
) -> MovimientoCaja:
    if monto <= CERO:
        raise HTTPException(status_code=422, detail="El monto debe ser mayor que cero")
    if sesion.estado is EstadoCaja.CERRADA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La caja {sesion.numero} ya está cerrada",
        )

    movimiento = MovimientoCaja(
        sesion_id=sesion.id,
        tipo=tipo,
        metodo=metodo,
        monto=monto,
        concepto=concepto,
        referencia=referencia,
        usuario_id=usuario_id,
    )
    db.add(movimiento)
    db.flush()
    return movimiento


def totales_por_metodo(db: Session, sesion: SesionCaja) -> dict[str, dict[str, Decimal]]:
    """Ingresos y egresos agrupados por método de pago."""
    filas = db.execute(
        select(
            MovimientoCaja.metodo,
            MovimientoCaja.tipo,
            func.coalesce(func.sum(MovimientoCaja.monto), 0),
        )
        .where(MovimientoCaja.sesion_id == sesion.id)
        .group_by(MovimientoCaja.metodo, MovimientoCaja.tipo)
    ).all()

    totales: dict[str, dict[str, Decimal]] = {
        m.value: {"ingresos": CERO, "egresos": CERO} for m in MetodoPago
    }
    for metodo, tipo, suma in filas:
        clave = "ingresos" if tipo is TipoMovimientoCaja.INGRESO else "egresos"
        totales[metodo.value][clave] = Decimal(suma)

    return totales


def efectivo_esperado(db: Session, sesion: SesionCaja) -> Decimal:
    """Lo que debería haber en el cajón.

    Sólo cuenta efectivo: Yape, Plin, tarjeta y transferencia no pasan por el
    cajón físico, así que sumarlos haría que el arqueo nunca cuadre.
    """
    filas = db.execute(
        select(MovimientoCaja.tipo, func.coalesce(func.sum(MovimientoCaja.monto), 0))
        .where(
            MovimientoCaja.sesion_id == sesion.id,
            MovimientoCaja.metodo.in_(METODOS_EFECTIVO),
        )
        .group_by(MovimientoCaja.tipo)
    ).all()

    saldo = sesion.monto_inicial
    for tipo, suma in filas:
        if tipo is TipoMovimientoCaja.INGRESO:
            saldo += Decimal(suma)
        else:
            saldo -= Decimal(suma)
    return saldo


def cerrar_caja(
    db: Session,
    sesion: SesionCaja,
    monto_declarado: Decimal,
    usuario_id: uuid.UUID | None,
    observaciones: str | None,
) -> SesionCaja:
    if sesion.estado is EstadoCaja.CERRADA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="La caja ya está cerrada"
        )
    if monto_declarado < CERO:
        raise HTTPException(status_code=422, detail="El monto contado no puede ser negativo")

    # El esperado se congela: si mañana se anula una venta de hoy, el arqueo
    # de hoy debe seguir mostrando lo que realmente se contó contra lo que
    # correspondía en ese momento.
    sesion.monto_esperado = efectivo_esperado(db, sesion)
    sesion.monto_declarado = monto_declarado
    sesion.estado = EstadoCaja.CERRADA
    sesion.fecha_cierre = func.now()
    sesion.usuario_cierre_id = usuario_id
    if observaciones:
        sesion.observaciones = (
            f"{sesion.observaciones}\n{observaciones}" if sesion.observaciones else observaciones
        )

    db.flush()
    return sesion
