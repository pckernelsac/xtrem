"""Puente entre los repuestos de una ficha y el stock del almacén.

El stock se descuenta cuando el repuesto se anota en la ficha, no al entregarla:
el técnico ya sacó la pieza del estante en ese momento. Si se esperara a la
entrega, el sistema mostraría existencias que físicamente ya no están y el
mostrador podría vender lo mismo dos veces.
"""

import uuid
from collections import defaultdict
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ficha import Ficha
from app.models.inventario import Producto, TipoMovimiento
from app.services.inventario import registrar_movimiento

CERO = Decimal("0")


def _referencia(ficha: Ficha) -> str:
    return f"FICHA-{ficha.numero}"


def _agrupar(lineas) -> dict[uuid.UUID, Decimal]:
    """Cantidad total por producto. Una ficha puede repetir el mismo producto
    en dos líneas distintas y el stock debe verlas como una sola."""
    totales: dict[uuid.UUID, Decimal] = defaultdict(lambda: CERO)
    for linea in lineas:
        producto_id = getattr(linea, "producto_id", None)
        if producto_id:
            totales[producto_id] += Decimal(str(linea.cantidad))
    return dict(totales)


def validar_productos(db: Session, lineas) -> None:
    """Falla temprano si una línea apunta a un producto inexistente o de baja."""
    ids = {l.producto_id for l in lineas if getattr(l, "producto_id", None)}
    if not ids:
        return

    encontrados = {
        p.id: p for p in db.scalars(select(Producto).where(Producto.id.in_(ids))).all()
    }

    for producto_id in ids:
        producto = encontrados.get(producto_id)
        if producto is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Uno de los repuestos apunta a un producto que no existe",
            )
        if not producto.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"El producto {producto.sku} está dado de baja y no se puede consumir",
            )


def sincronizar_consumo(
    db: Session,
    ficha: Ficha,
    lineas_nuevas,
    actor_id: uuid.UUID | None,
) -> None:
    """Ajusta el stock a la diferencia entre los repuestos guardados y los nuevos.

    Se trabaja por diferencia y no devolviendo todo para volver a descontarlo:
    así una edición que no toca los repuestos no genera movimientos de kardex
    falsos, y el libro sólo refleja consumo real.
    """
    anterior = _agrupar(ficha.repuestos)
    nuevo = _agrupar(lineas_nuevas)

    deltas = {
        pid: nuevo.get(pid, CERO) - anterior.get(pid, CERO)
        for pid in set(anterior) | set(nuevo)
    }
    deltas = {pid: d for pid, d in deltas.items() if d != CERO}
    if not deltas:
        return

    referencia = _referencia(ficha)

    # Orden fijo por id de producto: dos fichas que tocan los mismos productos
    # a la vez tomarían los bloqueos en orden distinto y podrían interbloquearse.
    # Las devoluciones van primero: liberan stock que las salidas puedan necesitar.
    for producto_id in sorted(deltas, key=str):
        delta = deltas[producto_id]
        if delta < CERO:
            registrar_movimiento(
                db,
                producto_id,
                TipoMovimiento.ENTRADA,
                -delta,
                usuario_id=actor_id,
                motivo=f"Devolución de repuesto — ficha {ficha.numero}",
                referencia=referencia,
            )

    for producto_id in sorted(deltas, key=str):
        delta = deltas[producto_id]
        if delta > CERO:
            registrar_movimiento(
                db,
                producto_id,
                TipoMovimiento.SALIDA,
                delta,
                usuario_id=actor_id,
                motivo=f"Consumo en taller — ficha {ficha.numero}",
                referencia=referencia,
            )


def devolver_todo(db: Session, ficha: Ficha, actor_id: uuid.UUID | None, motivo: str) -> None:
    """Reintegra al almacén todos los repuestos enlazados de la ficha.

    Se usa al cancelar: las piezas que no llegaron a montarse vuelven al
    estante, y el kardex deja constancia de por qué.
    """
    totales = _agrupar(ficha.repuestos)
    referencia = _referencia(ficha)

    for producto_id in sorted(totales, key=str):
        cantidad = totales[producto_id]
        if cantidad > CERO:
            registrar_movimiento(
                db,
                producto_id,
                TipoMovimiento.ENTRADA,
                cantidad,
                usuario_id=actor_id,
                motivo=motivo,
                referencia=referencia,
            )
