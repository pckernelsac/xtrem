"""Consultas de reportes: ventas, productos y valor de inventario.

Los totales de venta se calculan cargando las ventas del rango y sumando en
Python: `Venta.total` es una propiedad (subtotal − descuento), no una columna,
y el volumen de una tienda de barrio lo permite sin problema. El ranking de
productos sí se agrega en SQL, donde el importe por línea es una expresión.
"""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.fechas import dia_local, rango_utc
from app.models.caja import MetodoPago
from app.models.inventario import Producto
from app.models.venta import EstadoVenta, TipoVenta, Venta, VentaItem

CERO = Decimal("0.00")


def _rango_utc(desde: date, hasta: date) -> tuple[datetime, datetime]:
    """[desde 00:00, hasta+1 00:00) en hora de Lima: incluye `hasta` completo."""
    ini, fin = rango_utc(desde, hasta)
    assert ini is not None and fin is not None  # ambos días son obligatorios aquí
    return ini, fin


def _ventas_confirmadas(db: Session, desde: date, hasta: date) -> list[Venta]:
    ini, fin = _rango_utc(desde, hasta)
    return list(
        db.scalars(
            select(Venta).where(
                Venta.tipo == TipoVenta.VENTA,
                Venta.estado == EstadoVenta.CONFIRMADA,
                Venta.created_at >= ini,
                Venta.created_at < fin,
            )
        )
        .unique()
        .all()
    )


def reporte_ventas(db: Session, desde: date, hasta: date) -> dict:
    ventas = _ventas_confirmadas(db, desde, hasta)

    total = sum((v.total for v in ventas), CERO)
    por_dia: dict[date, dict] = defaultdict(lambda: {"cantidad": 0, "total": CERO})
    por_metodo: dict[str, Decimal] = {m.value: CERO for m in MetodoPago}

    for v in ventas:
        dia = dia_local(v.created_at)
        por_dia[dia]["cantidad"] += 1
        por_dia[dia]["total"] += v.total
        for p in v.pagos:
            por_metodo[p.metodo.value] += p.monto

    # Serie continua día a día: los días sin ventas aparecen en cero, para que
    # el gráfico no mienta uniendo dos fechas separadas por huecos.
    dias = []
    cursor = desde
    while cursor <= hasta:
        d = por_dia.get(cursor, {"cantidad": 0, "total": CERO})
        dias.append(
            {"fecha": cursor.isoformat(), "cantidad": d["cantidad"], "total": str(d["total"])}
        )
        cursor += timedelta(days=1)

    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "cantidad": len(ventas),
        "total": str(total),
        "ticket_promedio": str((total / len(ventas)).quantize(CERO) if ventas else CERO),
        "por_dia": dias,
        "por_metodo": {k: str(v) for k, v in por_metodo.items() if v > CERO},
    }


def reporte_productos_vendidos(
    db: Session, desde: date, hasta: date, limite: int = 20
) -> dict:
    ini, fin = _rango_utc(desde, hasta)

    importe_linea = func.sum(
        VentaItem.cantidad * VentaItem.precio_unitario - VentaItem.descuento
    )
    filas = db.execute(
        select(
            VentaItem.producto_id,
            func.max(VentaItem.descripcion).label("descripcion"),
            func.sum(VentaItem.cantidad).label("cantidad"),
            importe_linea.label("importe"),
        )
        .join(Venta, Venta.id == VentaItem.venta_id)
        .where(
            Venta.tipo == TipoVenta.VENTA,
            Venta.estado == EstadoVenta.CONFIRMADA,
            Venta.created_at >= ini,
            Venta.created_at < fin,
        )
        .group_by(VentaItem.producto_id)
        .order_by(importe_linea.desc())
        .limit(limite)
    ).all()

    # El SKU se resuelve aparte: las líneas sueltas (sin producto) no lo tienen.
    ids = [f.producto_id for f in filas if f.producto_id]
    skus = {}
    if ids:
        skus = {
            p.id: p.sku
            for p in db.scalars(select(Producto).where(Producto.id.in_(ids))).all()
        }

    items = [
        {
            "sku": skus.get(f.producto_id),
            "descripcion": f.descripcion,
            "cantidad": str(Decimal(f.cantidad)),
            "importe": str(Decimal(f.importe or 0).quantize(CERO)),
        }
        for f in filas
    ]
    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "items": items,
    }


def reporte_inventario(db: Session) -> dict:
    """Foto del inventario ahora: valor total y productos que requieren atención."""
    productos = list(
        db.scalars(select(Producto).where(Producto.is_active.is_(True)).order_by(Producto.nombre))
        .unique()
        .all()
    )

    valor_total = sum((p.valor_stock for p in productos), CERO)
    alertas = [p for p in productos if p.sin_stock or p.bajo_minimo]

    return {
        "generado": datetime.now(UTC).isoformat(),
        "productos_activos": len(productos),
        "valor_total": str(valor_total),
        "sin_stock": sum(1 for p in productos if p.sin_stock),
        "bajo_minimo": sum(1 for p in productos if p.bajo_minimo and not p.sin_stock),
        "alertas": [
            {
                "sku": p.sku,
                "nombre": p.nombre,
                "stock_actual": str(p.stock_actual),
                "stock_minimo": str(p.stock_minimo),
                "estado": "SIN_STOCK" if p.sin_stock else "BAJO_MINIMO",
            }
            for p in alertas
        ],
    }
