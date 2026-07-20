"""Reglas de movimiento de stock.

Todo cambio de existencias pasa por aquí: es el único lugar que escribe
`productos.stock_actual`, y siempre deja su asiento en el kardex.
"""

import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, lazyload

from app.models.inventario import MovimientoKardex, Producto, TipoMovimiento

CERO = Decimal("0")


def _bloquear_producto(db: Session, producto_id: uuid.UUID) -> Producto:
    """Carga el producto con bloqueo de fila.

    SELECT ... FOR UPDATE serializa los movimientos sobre el mismo producto.
    Sin esto, dos salidas simultáneas leerían el mismo stock inicial y la
    segunda escribiría un saldo que ignora a la primera.

    Se anula el `lazy="joined"` de la categoría: ese LEFT OUTER JOIN hace que
    Postgres rechace el bloqueo con "FOR UPDATE cannot be applied to the
    nullable side of an outer join". Aquí sólo interesa la fila del producto.
    """
    producto = db.scalar(
        select(Producto)
        .where(Producto.id == producto_id)
        .options(lazyload(Producto.categoria))
        .with_for_update()
    )
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return producto


def bloquear_productos(db: Session, producto_ids) -> None:
    """Toma el bloqueo exclusivo de varios productos, en orden fijo.

    Hay que llamarlo ANTES de insertar filas que referencien esos productos
    por clave foránea. Un INSERT con FK toma un FOR KEY SHARE sobre la fila
    referenciada; si después se intenta subir a FOR UPDATE, dos transacciones
    concurrentes que ya tienen el compartido se quedan esperando la una a la
    otra y Postgres aborta una con "deadlock detected".

    El orden por id evita el otro deadlock clásico: dos transacciones que
    tocan los mismos productos en secuencia distinta.
    """
    ids = sorted({pid for pid in producto_ids if pid}, key=str)
    for producto_id in ids:
        _bloquear_producto(db, producto_id)


def registrar_movimiento(
    db: Session,
    producto_id: uuid.UUID,
    tipo: TipoMovimiento,
    cantidad: Decimal,
    *,
    usuario_id: uuid.UUID | None = None,
    costo_unitario: Decimal | None = None,
    motivo: str | None = None,
    referencia: str | None = None,
) -> MovimientoKardex | None:
    """Aplica un movimiento y devuelve el asiento del kardex.

    `cantidad` siempre es positiva; el signo lo pone `tipo`. En un AJUSTE,
    `cantidad` es el stock contado, no la diferencia: quien hace inventario
    físico anota lo que ve en el estante, no una resta.

    Devuelve `None` si el ítem es un servicio: vender o consumir mano de obra
    no mueve existencias. El no-op vive aquí, en el único punto que escribe
    stock, para que ninguna vía (venta, ficha, importación) tenga que acordarse
    de filtrar servicios y termine bloqueando una venta legítima.
    """
    if cantidad < CERO:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La cantidad no puede ser negativa",
        )
    if tipo is not TipoMovimiento.AJUSTE and cantidad == CERO:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La cantidad debe ser mayor que cero",
        )

    producto = _bloquear_producto(db, producto_id)
    if producto.es_servicio:
        return None

    anterior = producto.stock_actual

    if tipo is TipoMovimiento.ENTRADA:
        posterior = anterior + cantidad
        movida = cantidad
    elif tipo is TipoMovimiento.SALIDA:
        if cantidad > anterior:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Stock insuficiente de {producto.sku}: hay {anterior:g} "
                    f"{producto.unidad.value.lower()} y se intentan retirar {cantidad:g}"
                ),
            )
        posterior = anterior - cantidad
        movida = cantidad
    else:  # AJUSTE
        posterior = cantidad
        movida = abs(posterior - anterior)
        if movida == CERO:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El stock contado es igual al registrado; no hay ajuste que hacer",
            )

    producto.stock_actual = posterior

    asiento = MovimientoKardex(
        producto_id=producto.id,
        tipo=tipo,
        cantidad=movida,
        stock_anterior=anterior,
        stock_posterior=posterior,
        costo_unitario=costo_unitario,
        motivo=motivo,
        referencia=referencia,
        usuario_id=usuario_id,
    )
    db.add(asiento)

    # Una entrada actualiza el costo de reposición: es el precio al que
    # realmente se está comprando hoy.
    if tipo is TipoMovimiento.ENTRADA and costo_unitario and costo_unitario > CERO:
        producto.precio_compra = costo_unitario

    db.flush()
    return asiento


def recalcular_stock(db: Session, producto: Producto) -> Decimal:
    """Suma el kardex desde cero. Sirve para auditar el saldo denormalizado."""
    saldo = CERO
    movimientos = db.scalars(
        select(MovimientoKardex)
        .where(MovimientoKardex.producto_id == producto.id)
        .order_by(MovimientoKardex.created_at, MovimientoKardex.id)
    ).all()

    for m in movimientos:
        if m.tipo is TipoMovimiento.ENTRADA:
            saldo += m.cantidad
        elif m.tipo is TipoMovimiento.SALIDA:
            saldo -= m.cantidad
        else:
            saldo = m.stock_posterior

    return saldo
