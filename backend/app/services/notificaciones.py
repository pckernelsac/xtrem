"""Notificaciones accionables: alertas que el usuario debería atender ahora.

Se calculan en vivo (no hay tabla de notificaciones): reflejan el estado actual
del negocio. Cada alerta respeta los permisos de quien pregunta —a un cajero no
se le avisa de stock bajo si no ve el inventario.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.fechas import hoy_local
from app.models.caja import EstadoCaja, SesionCaja
from app.models.ficha import EstadoFicha, Ficha
from app.models.inventario import Producto
from app.models.user import User
from app.models.venta import EstadoVenta, TipoVenta, Venta

#: Una caja lleva demasiado tiempo abierta: probablemente se olvidó cerrarla.
HORAS_CAJA_ABIERTA = 16


def _alerta(tipo: str, nivel: str, titulo: str, detalle: str, enlace: str, cantidad: int) -> dict:
    return {
        "tipo": tipo,
        "nivel": nivel,  # info | warning | danger
        "titulo": titulo,
        "detalle": detalle,
        "enlace": enlace,
        "cantidad": cantidad,
    }


def calcular(db: Session, usuario: User) -> list[dict]:
    permisos = set(usuario.permission_codes)
    alertas: list[dict] = []

    # --- Inventario: bajo mínimo / sin stock ---
    if "inventario.ver" in permisos:
        sin_stock = (
            db.scalar(
                select(func.count(Producto.id)).where(
                    Producto.is_active.is_(True), Producto.stock_actual <= 0
                )
            )
            or 0
        )
        bajo_minimo = (
            db.scalar(
                select(func.count(Producto.id)).where(
                    Producto.is_active.is_(True),
                    Producto.stock_minimo > 0,
                    Producto.stock_actual > 0,
                    Producto.stock_actual <= Producto.stock_minimo,
                )
            )
            or 0
        )
        if sin_stock:
            alertas.append(
                _alerta(
                    "sin_stock", "danger", "Productos agotados",
                    f"{sin_stock} producto(s) sin stock",
                    "/inventario?tab=alertas", sin_stock,
                )
            )
        if bajo_minimo:
            alertas.append(
                _alerta(
                    "bajo_minimo", "warning", "Stock bajo",
                    f"{bajo_minimo} producto(s) por debajo del mínimo",
                    "/inventario?tab=alertas", bajo_minimo,
                )
            )

    # --- Taller: fichas listas para entregar ---
    if "fichas.ver" in permisos:
        listas = (
            db.scalar(
                select(func.count(Ficha.id)).where(
                    Ficha.estado == EstadoFicha.LISTA_PARA_ENTREGAR
                )
            )
            or 0
        )
        if listas:
            alertas.append(
                _alerta(
                    "fichas_listas", "info", "Bicicletas listas",
                    f"{listas} ficha(s) lista(s) para entregar",
                    "/fichas?estado=LISTA_PARA_ENTREGAR", listas,
                )
            )

    # --- Ventas: cotizaciones pendientes o vencidas ---
    if "ventas.ver" in permisos:
        hoy = hoy_local()
        pendientes = list(
            db.scalars(
                select(Venta).where(
                    Venta.tipo == TipoVenta.COTIZACION,
                    Venta.estado == EstadoVenta.PENDIENTE,
                )
            ).all()
        )
        vencidas = [v for v in pendientes if v.valido_hasta and v.valido_hasta < hoy]
        if vencidas:
            alertas.append(
                _alerta(
                    "cotizaciones_vencidas", "warning", "Cotizaciones vencidas",
                    f"{len(vencidas)} cotización(es) pasaron su fecha de validez",
                    "/cotizaciones?estado=PENDIENTE", len(vencidas),
                )
            )

    # --- Caja abierta demasiado tiempo ---
    if "caja.ver" in permisos:
        sesion = db.scalar(select(SesionCaja).where(SesionCaja.estado == EstadoCaja.ABIERTA))
        if sesion is not None:
            horas = (datetime.now(UTC) - sesion.fecha_apertura).total_seconds() / 3600
            if horas >= HORAS_CAJA_ABIERTA:
                alertas.append(
                    _alerta(
                        "caja_sin_cerrar", "warning", "Caja sin cerrar",
                        f"La caja {sesion.numero} lleva más de {HORAS_CAJA_ABIERTA} h abierta",
                        "/caja", 1,
                    )
                )

    # --- Facturación: comprobantes con error ---
    if "facturacion.ver" in permisos:
        from app.models.comprobante import ComprobanteElectronico, EstadoComprobante

        con_error = (
            db.scalar(
                select(func.count(ComprobanteElectronico.id)).where(
                    ComprobanteElectronico.estado.in_(
                        [EstadoComprobante.ERROR, EstadoComprobante.RECHAZADO]
                    )
                )
            )
            or 0
        )
        if con_error:
            alertas.append(
                _alerta(
                    "comprobantes_error", "danger", "Comprobantes con problemas",
                    f"{con_error} comprobante(s) con error o rechazados por SUNAT",
                    "/documentos", con_error,
                )
            )

    return alertas
