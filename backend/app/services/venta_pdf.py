"""PDF de cotizaciones y notas de venta: hoja A4 y ticket de 80 mm.

Reutiliza la maquinaria del PDF de la ficha (entorno Jinja, assets embebidos y
la medición del alto del ticket) en vez de duplicarla: son los mismos dos
formatos de salida, sólo cambia el documento que se imprime.
"""

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from weasyprint import HTML

from app.core.config import settings
from app.models.venta import ETIQUETAS_ESTADO_VENTA, TipoVenta, Venta
from app.services.ficha_pdf import (
    ALTO_SONDA_MM,
    BASE_DIR,
    COLA_CORTE_MM,
    EMPRESA,
    _asset_data_url,
    _env,
    _medir_alto_mm,
    _monto,
)

LIMA = ZoneInfo("America/Lima")

#: Filas mínimas de la tabla en A4, para que la hoja no quede desbalanceada
#: cuando se cotizan una o dos líneas.
FILAS_MIN = 6

TITULOS = {
    TipoVenta.COTIZACION: "COTIZACIÓN",
    TipoVenta.VENTA: "NOTA DE VENTA",
}


def _fecha(dt: datetime | None) -> str:
    return dt.astimezone(LIMA).strftime("%d/%m/%Y %I:%M %p") if dt else ""


def _fecha_corta(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _cantidad(valor: Decimal) -> str:
    """1.000 -> "1"; 2.500 -> "2.5". El papel no lleva ceros de relleno."""
    texto = f"{valor:f}"
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


def _cliente(venta: Venta) -> dict[str, str]:
    c = venta.cliente
    if c is None:
        # Venta de mostrador: el papel no debe quedar con un hueco sin explicar.
        return {"nombre": "Público general", "documento": "", "telefono": "", "direccion": ""}
    return {
        "nombre": c.nombre,
        "documento": f"{c.tipo_documento.value} {c.numero_documento}",
        "telefono": c.telefono or "",
        "direccion": c.direccion or "",
    }


def _lineas(venta: Venta) -> list[dict[str, str]]:
    return [
        {
            "cantidad": _cantidad(i.cantidad),
            "descripcion": i.descripcion,
            "sku": i.producto.sku if i.producto else "",
            "precio": _monto(i.precio_unitario),
            "descuento": _monto(i.descuento) if i.descuento > 0 else "",
            "importe": _monto(i.subtotal),
        }
        for i in venta.items
    ]


def _contexto(venta: Venta) -> dict[str, object]:
    return {
        "v": venta,
        "empresa": EMPRESA,
        "logo": _asset_data_url("logo_zonaxtrema.png"),
        "titulo": TITULOS[venta.tipo],
        "es_cotizacion": venta.tipo is TipoVenta.COTIZACION,
        "estado_label": ETIQUETAS_ESTADO_VENTA[venta.estado.value],
        "cliente": _cliente(venta),
        "lineas": _lineas(venta),
        "fecha": _fecha(venta.created_at),
        "valido_hasta": _fecha_corta(venta.valido_hasta),
        "subtotal": _monto(venta.subtotal),
        "descuento": _monto(venta.descuento),
        "tiene_descuento": venta.descuento > Decimal("0"),
        "total": _monto(venta.total),
        "pagos": [
            {"metodo": p.metodo.value.title(), "monto": _monto(p.monto)} for p in venta.pagos
        ],
        "vendedor": venta.usuario.full_name if venta.usuario else "",
    }


def render_venta_pdf(venta: Venta) -> bytes:
    """Hoja A4, la que se entrega o se manda por correo."""
    contexto = _contexto(venta)
    filas = list(contexto["lineas"])  # type: ignore[arg-type]
    vacia = {"cantidad": "", "descripcion": "", "sku": "", "precio": "", "descuento": "", "importe": ""}
    filas += [vacia] * max(0, FILAS_MIN - len(filas))
    contexto["filas"] = filas

    html = _env().get_template("cotizacion.html").render(**contexto)
    return HTML(string=html, base_url=str(BASE_DIR)).write_pdf()


def render_venta_ticket(venta: Venta) -> bytes:
    """Ticket de 80 mm, el del mostrador.

    Igual que en la ficha, se renderiza dos veces: la primera sólo para medir
    el alto real y no gastar medio metro de papel en blanco por documento.
    """
    contexto = _contexto(venta)
    contexto.update(
        {
            "ancho_mm": settings.TICKET_ANCHO_MM,
            "margen_mm": settings.TICKET_MARGEN_MM,
        }
    )

    plantilla = _env().get_template("cotizacion_ticket.html")

    sonda = plantilla.render(**contexto, alto_mm=ALTO_SONDA_MM)
    alto = _medir_alto_mm(sonda) + settings.TICKET_MARGEN_MM + COLA_CORTE_MM

    final = plantilla.render(**contexto, alto_mm=round(alto, 1))
    return HTML(string=final, base_url=str(BASE_DIR)).write_pdf()
