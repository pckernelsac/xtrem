"""Reglas de venta: stock, cobros y su reflejo en la caja.

Una venta confirmada toca tres cosas a la vez —inventario, cajón y pagos— y
las tres tienen que cuadrar o ninguna debe aplicarse. Por eso todo pasa por
aquí y no por el router.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.caja import (
    METODOS_EFECTIVO,
    MetodoPago,
    SesionCaja,
    TipoMovimientoCaja,
)
from app.models.inventario import Producto, TipoMovimiento
from app.models.venta import EstadoVenta, PagoVenta, TipoVenta, Venta, VentaItem
from app.services.caja import exigir_sesion_abierta, registrar_movimiento_caja, sesion_abierta
from app.services.inventario import bloquear_productos, registrar_movimiento

CERO = Decimal("0.00")
CENTIMO = Decimal("0.01")


def siguiente_numero(db: Session, tipo: TipoVenta) -> str:
    """Correlativos separados por tipo: las cotizaciones llevan su propia
    numeración, igual que el talonario de proformas en papel."""
    if tipo is TipoVenta.COTIZACION:
        valor = db.scalar(text("SELECT nextval('cotizacion_numero_seq')"))
        return f"COT-{valor:06d}"
    valor = db.scalar(text("SELECT nextval('venta_numero_seq')"))
    return f"V-{valor:06d}"


def validar_productos(db: Session, lineas) -> dict[uuid.UUID, Producto]:
    ids = {l.producto_id for l in lineas if getattr(l, "producto_id", None)}
    if not ids:
        return {}

    encontrados = {
        p.id: p for p in db.scalars(select(Producto).where(Producto.id.in_(ids))).all()
    }
    for producto_id in ids:
        producto = encontrados.get(producto_id)
        if producto is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Una de las líneas apunta a un producto que no existe",
            )
        if not producto.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"El producto {producto.sku} está dado de baja y no se puede vender",
            )
    return encontrados


def _agrupar(lineas) -> dict[uuid.UUID, Decimal]:
    totales: dict[uuid.UUID, Decimal] = defaultdict(lambda: CERO)
    for linea in lineas:
        producto_id = getattr(linea, "producto_id", None)
        if producto_id:
            totales[producto_id] += Decimal(str(linea.cantidad))
    return dict(totales)


def descontar_stock(db: Session, venta: Venta, actor_id: uuid.UUID | None) -> None:
    """Saca del almacén lo vendido. Orden fijo por id para no interbloquear."""
    for producto_id, cantidad in sorted(_agrupar(venta.items).items(), key=lambda x: str(x[0])):
        if cantidad > CERO:
            registrar_movimiento(
                db,
                producto_id,
                TipoMovimiento.SALIDA,
                cantidad,
                usuario_id=actor_id,
                motivo=f"Venta {venta.numero}",
                referencia=venta.numero,
            )


def devolver_stock(db: Session, venta: Venta, actor_id: uuid.UUID | None, motivo: str) -> None:
    for producto_id, cantidad in sorted(_agrupar(venta.items).items(), key=lambda x: str(x[0])):
        if cantidad > CERO:
            registrar_movimiento(
                db,
                producto_id,
                TipoMovimiento.ENTRADA,
                cantidad,
                usuario_id=actor_id,
                motivo=motivo,
                referencia=venta.numero,
            )


def validar_pagos(venta: Venta, pagos: list) -> None:
    """El cobro debe cubrir exactamente el total.

    Se admite un céntimo de holgura: repartir S/ 100.00 entre dos métodos puede
    dejar diferencias de redondeo que no son un error del cajero.
    """
    if not pagos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Una venta confirmada necesita al menos un pago",
        )

    total_pagos = sum((Decimal(str(p.monto)) for p in pagos), CERO)
    total = venta.total

    if abs(total_pagos - total) > CENTIMO:
        if total_pagos < total:
            detalle = f"El pago cubre S/ {total_pagos:.2f} de un total de S/ {total:.2f}"
        else:
            detalle = (
                f"El pago suma S/ {total_pagos:.2f} y el total es S/ {total:.2f}. "
                "Si el cliente paga con más, registra sólo el importe cobrado."
            )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detalle)


def requiere_caja(pagos: list) -> bool:
    return any(MetodoPago(p.metodo) in METODOS_EFECTIVO for p in pagos)


def registrar_cobros(
    db: Session,
    venta: Venta,
    pagos: list,
    sesion: SesionCaja | None,
    actor_id: uuid.UUID | None,
) -> None:
    """Crea los pagos y su reflejo en la caja.

    Los métodos digitales también entran al cajón como movimiento, pero el
    arqueo sólo cuenta el efectivo: así el reporte del día muestra cuánto
    entró por Yape sin desbalancear el conteo físico.
    """
    for p in pagos:
        venta.pagos.append(
            PagoVenta(
                metodo=MetodoPago(p.metodo),
                monto=Decimal(str(p.monto)),
                referencia=getattr(p, "referencia", None),
            )
        )

        if sesion is not None:
            registrar_movimiento_caja(
                db,
                sesion,
                TipoMovimientoCaja.INGRESO,
                MetodoPago(p.metodo),
                Decimal(str(p.monto)),
                concepto=f"Cobro venta {venta.numero}",
                usuario_id=actor_id,
                referencia=venta.numero,
            )


def confirmar_venta(
    db: Session,
    venta: Venta,
    pagos: list,
    actor_id: uuid.UUID | None,
) -> Venta:
    """Aplica stock, pagos y caja. Cualquier fallo aborta la transacción entera."""
    validar_pagos(venta, pagos)

    # El efectivo EXIGE caja abierta porque entra al cajón físico. Los métodos
    # digitales no la exigen, pero si hay una sesión abierta también se anotan
    # en ella: si no, el reporte del día no mostraría cuánto entró por Yape.
    sesion = exigir_sesion_abierta(db) if requiere_caja(pagos) else sesion_abierta(db)

    descontar_stock(db, venta, actor_id)
    registrar_cobros(db, venta, pagos, sesion, actor_id)

    venta.estado = EstadoVenta.CONFIRMADA
    venta.sesion_caja_id = sesion.id if sesion else None
    db.flush()
    return venta


def anular_venta(
    db: Session, venta: Venta, motivo: str | None, actor_id: uuid.UUID | None
) -> Venta:
    """Devuelve la mercadería y saca de la caja lo que se había cobrado."""
    if venta.estado is EstadoVenta.ANULADA:
        raise HTTPException(status_code=409, detail="La venta ya está anulada")
    if venta.tipo is TipoVenta.COTIZACION:
        raise HTTPException(
            status_code=409,
            detail="Una cotización no se anula: se marca como rechazada",
        )

    devolver_stock(db, venta, actor_id, f"Anulación de la venta {venta.numero}")

    # La devolución se registra en la caja abierta hoy, no en la sesión
    # original: esa jornada ya se arqueó y su cuadre no debe moverse.
    hay_efectivo = any(p.metodo in METODOS_EFECTIVO for p in venta.pagos)
    sesion = exigir_sesion_abierta(db) if hay_efectivo else sesion_abierta(db)

    if sesion is not None:
        # Se revierte cada método por separado para que el reporte del día no
        # quede mostrando un ingreso por Yape que en realidad se devolvió.
        por_metodo: dict[MetodoPago, Decimal] = defaultdict(lambda: CERO)
        for p in venta.pagos:
            por_metodo[p.metodo] += p.monto

        for metodo in sorted(por_metodo, key=lambda m: m.value):
            registrar_movimiento_caja(
                db,
                sesion,
                TipoMovimientoCaja.EGRESO,
                metodo,
                por_metodo[metodo],
                concepto=f"Devolución por anulación de {venta.numero}",
                usuario_id=actor_id,
                referencia=venta.numero,
            )

    venta.estado = EstadoVenta.ANULADA
    venta.fecha_anulacion = datetime.now(UTC)
    venta.motivo_anulacion = motivo
    db.flush()
    return venta


def reemplazar_items(db: Session, venta: Venta, lineas) -> None:
    validar_productos(db, lineas)

    # Se bloquean los productos ANTES de insertar las líneas: el INSERT toma
    # un lock compartido por la clave foránea, y subirlo después a exclusivo
    # provoca deadlock entre dos ventas simultáneas del mismo producto.
    bloquear_productos(db, [l.producto_id for l in lineas])

    venta.items.clear()
    db.flush()
    for i, linea in enumerate(lineas):
        venta.items.append(
            VentaItem(
                orden=i,
                producto_id=linea.producto_id,
                descripcion=linea.descripcion,
                cantidad=Decimal(str(linea.cantidad)),
                precio_unitario=Decimal(str(linea.precio_unitario)),
                descuento=Decimal(str(linea.descuento)),
            )
        )
    db.flush()
