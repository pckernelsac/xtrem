"""Convertir un servicio (ficha) entregado en una venta facturable.

La ficha ya descontó su stock y ya cobró el adelanto en recepción. Aquí sólo se
arma la venta que respalda el comprobante y se cobra el saldo en caja, sin volver
a tocar el inventario ni recontar el adelanto.
"""

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.caja import MetodoPago, TipoMovimientoCaja
from app.models.ficha import Ficha
from app.models.venta import EstadoVenta, PagoVenta, TipoVenta, Venta, VentaItem
from app.schemas.ficha import PagoServicioIn
from app.services.caja import (
    exigir_sesion_abierta,
    registrar_movimiento_caja,
    sesion_abierta,
)
from app.services.venta import siguiente_numero

CERO = Decimal("0.00")
CENTIMO = Decimal("0.01")


def _items_desde_ficha(ficha: Ficha) -> list[VentaItem]:
    """Repuestos + mano de obra como líneas de venta.

    Los ítems van SIN `producto_id`: el stock ya lo movió la ficha, y dejarlo
    enlazado haría que confirmar o anular la venta lo descontara o devolviera de
    nuevo. El comprobante sólo necesita la descripción y el importe.
    """
    items: list[VentaItem] = []
    orden = 0
    for r in ficha.repuestos:
        items.append(
            VentaItem(
                orden=orden,
                producto_id=None,
                descripcion=r.descripcion,
                cantidad=r.cantidad,
                precio_unitario=r.precio_unitario,
                descuento=CERO,
            )
        )
        orden += 1

    if ficha.costo_servicio and ficha.costo_servicio > CERO:
        items.append(
            VentaItem(
                orden=orden,
                producto_id=None,
                descripcion="Servicio / mano de obra",
                cantidad=Decimal("1"),
                precio_unitario=ficha.costo_servicio,
                descuento=CERO,
            )
        )
    return items


def crear_venta_desde_ficha(
    db: Session,
    ficha: Ficha,
    pagos_saldo: list[PagoServicioIn],
    actor_id: uuid.UUID | None,
) -> Venta:
    """Crea la venta confirmada que respalda el comprobante del servicio."""
    saldo = ficha.saldo
    adelanto = ficha.adelanto or CERO

    total_pagos_saldo = sum((p.monto for p in pagos_saldo), CERO)
    if abs(total_pagos_saldo - saldo) > CENTIMO:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"El cobro suma S/ {total_pagos_saldo:.2f} y el saldo es S/ {saldo:.2f}",
        )

    # El efectivo del saldo entra al cajón físico y exige caja abierta. Los
    # métodos digitales no la exigen, pero se anotan en la sesión abierta si
    # existe, igual que en una venta normal.
    hay_efectivo = any(p.metodo is MetodoPago.EFECTIVO for p in pagos_saldo)
    sesion = exigir_sesion_abierta(db) if hay_efectivo else sesion_abierta(db)

    venta = Venta(
        numero=siguiente_numero(db, TipoVenta.VENTA),
        tipo=TipoVenta.VENTA,
        estado=EstadoVenta.CONFIRMADA,
        cliente_id=ficha.cliente_id,
        ficha_id=ficha.id,
        sesion_caja_id=sesion.id if sesion else None,
        usuario_id=actor_id,
        notas=f"Servicio N° {ficha.numero}",
    )
    venta.items = _items_desde_ficha(ficha)

    # El adelanto ya se cobró y se contó en caja al recibir: se registra como
    # pago de la venta para que quede pagada, pero SIN nuevo movimiento de caja.
    if adelanto > CERO:
        venta.pagos.append(
            PagoVenta(
                metodo=ficha.adelanto_metodo or MetodoPago.EFECTIVO,
                monto=adelanto,
                referencia=f"Adelanto {ficha.numero}",
            )
        )

    # El saldo sí se cobra ahora: pago de la venta + movimiento en caja.
    for p in pagos_saldo:
        venta.pagos.append(
            PagoVenta(metodo=p.metodo, monto=p.monto, referencia=p.referencia)
        )
        if sesion is not None:
            registrar_movimiento_caja(
                db,
                sesion,
                TipoMovimientoCaja.INGRESO,
                p.metodo,
                p.monto,
                concepto=f"Cobro servicio {ficha.numero} · venta {venta.numero}",
                usuario_id=actor_id,
                referencia=venta.numero,
            )

    db.add(venta)
    db.flush()
    return venta
