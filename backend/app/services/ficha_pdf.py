"""Render del PDF de la ficha de mantenimiento.

Replica el formato impreso de Zona Xtrema (zona.jpeg) con WeasyPrint.
La plantilla vive en `app/templates/ficha.html` y los assets de marca en
`app/assets/`.
"""

import base64
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import qrcode
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image
from weasyprint import HTML
from weasyprint.formatting_structure import boxes

from app.core.config import settings
from app.models.ficha import ETIQUETAS_ESTADO, ETIQUETAS_SERVICIO, Ficha

PREFIJO_PNG = "data:image/png;base64,"

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
ASSETS_DIR = BASE_DIR / "assets"

LIMA = ZoneInfo("America/Lima")

#: Filas mínimas de la tabla de repuestos, para que el PDF conserve el aspecto
#: del formulario impreso aunque se usen pocos repuestos.
FILAS_REPUESTOS_MIN = 8

#: Datos de contacto tomados de la papelería de la tienda (proforma).
EMPRESA = {
    "razon_social": "Zona Xtrema Bikes & Componentes",
    "ruc": "10431869662",
    "direccion": "Av. San Carlos N° 177 - Huancayo",
    "telefono": "969 127 107",
    "web": "www.zonaxtrema.pe",
    "facebook": "Zona Xtrema Oficial",
    "instagram": "@zonaxtrema.bikes",
}


@lru_cache(maxsize=8)
def _asset_data_url(nombre: str) -> str:
    """Los assets se embeben en base64: WeasyPrint no debe salir a buscar
    archivos por red ni depender de rutas absolutas del contenedor."""
    ruta = ASSETS_DIR / nombre
    datos = base64.b64encode(ruta.read_bytes()).decode()
    return f"data:image/png;base64,{datos}"


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
    )


def _partes_fecha(dt: datetime | None) -> dict[str, object]:
    """Descompone la fecha en el formato del papel: DD / MM / AAAA y HH:MM AM/PM."""
    if dt is None:
        return {"fecha": "", "hora": "", "am": False, "pm": False}

    local = dt.astimezone(LIMA)
    return {
        "fecha": local.strftime("%d / %m / %Y"),
        "hora": local.strftime("%I:%M"),
        "am": local.hour < 12,
        "pm": local.hour >= 12,
    }


def _monto(valor: Decimal) -> str:
    return f"{valor:,.2f}"


def _tiempo_texto(minutos: int | None) -> str:
    if not minutos:
        return ""
    horas, mins = divmod(minutos, 60)
    if horas and mins:
        return f"{horas} h {mins} min"
    if horas:
        return f"{horas} h"
    return f"{mins} min"


def _contexto(ficha: Ficha) -> dict[str, object]:
    marcados = set(ficha.servicios or [])

    # El orden de las dos columnas replica el de la ficha impresa.
    col1 = [
        "MANTENIMIENTO_GENERAL",
        "MANTENIMIENTO_COMPLETO",
        "AJUSTE_FRENOS",
        "AJUSTE_CAMBIOS",
        "LIMPIEZA_LUBRICACION",
    ]
    col2 = ["CAMBIO_COMPONENTES", "ALINEACION_RUEDAS", "REVISION_SUSPENSION"]

    def _items(codigos: list[str]) -> list[dict[str, object]]:
        return [
            {
                "label": ETIQUETAS_SERVICIO[c].upper(),
                "marcado": c in marcados,
            }
            for c in codigos
        ]

    filas = [
        {
            "cantidad": f"{r.cantidad:g}",
            "descripcion": r.descripcion,
            "marca": r.marca or "",
            "precio": _monto(r.precio_unitario),
        }
        for r in ficha.repuestos
    ]
    # Se rellena con filas vacías hasta completar el alto del formulario.
    filas += [{"cantidad": "", "descripcion": "", "marca": "", "precio": ""}] * max(
        0, FILAS_REPUESTOS_MIN - len(filas)
    )

    return {
        "f": ficha,
        "empresa": EMPRESA,
        "logo": _asset_data_url("logo_zonaxtrema.png"),
        "emblema": _asset_data_url("emblema_x.png"),
        "iconos": _asset_data_url("iconos_taller.png"),
        "recepcion": _partes_fecha(ficha.fecha_recepcion),
        "entrega": _partes_fecha(ficha.fecha_entrega),
        "servicios_col1": _items(col1),
        "servicios_col2": _items(col2),
        "filas_repuestos": filas,
        "total_repuestos": _monto(ficha.total_repuestos),
        "costo_servicio": _monto(ficha.costo_servicio),
        "adelanto": _monto(ficha.adelanto),
        "saldo": _monto(ficha.saldo),
        "tiene_mano_obra": bool(ficha.costo_servicio and ficha.costo_servicio > 0),
        "tiene_adelanto": bool(ficha.adelanto and ficha.adelanto > 0),
        # Total del servicio: repuestos + mano de obra.
        "total": _monto(ficha.total),
        "tiempo_texto": _tiempo_texto(ficha.tiempo_invertido_min),
    }


def _firma_utilizable(data_url: str | None) -> str | None:
    """Descarta una firma que no se pueda decodificar.

    La validación al guardar ya rechaza PNG inválidos, pero un registro viejo
    o corrupto no debe impedir imprimir la ficha: es preferible un PDF sin el
    trazo que un 500 que deja al taller sin documento de entrega.
    """
    if not data_url or not data_url.startswith(PREFIJO_PNG):
        return None
    try:
        crudo = base64.b64decode(data_url[len(PREFIJO_PNG) :], validate=True)
        with Image.open(BytesIO(crudo)) as img:
            img.load()
    except Exception:
        return None
    return data_url


def render_ficha_pdf(ficha: Ficha, url_publica: str | None = None) -> bytes:
    contexto = _contexto(ficha)
    contexto["firma_cliente"] = _firma_utilizable(ficha.firma_cliente)
    contexto["firma_tecnico"] = _firma_utilizable(ficha.firma_tecnico)
    contexto["qr"] = _qr_data_url(url_publica) if url_publica else None
    # Se imprime junto al QR por si la cámara no lo lee: el cliente lo dicta.
    contexto["codigo_publico"] = ficha.codigo_publico if url_publica else None

    html = _env().get_template("ficha.html").render(**contexto)
    return HTML(string=html, base_url=str(BASE_DIR)).write_pdf()


# ---------------------------------------------------------------------------
# Ticket para impresora térmica de 80 mm
# ---------------------------------------------------------------------------

#: Alto de la primera pasada. Sólo sirve para medir: debe superar cualquier
#: ticket real para que el contenido no se corte antes de medirlo.
ALTO_SONDA_MM = 3000

#: Margen inferior extra para que la cuchilla no corte sobre el texto.
COLA_CORTE_MM = 6


def _qr_data_url(texto: str) -> str:
    """QR sin bordes de color: la térmica sólo imprime negro."""
    qr = qrcode.QRCode(version=None, box_size=8, border=2)
    qr.add_data(texto)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _medir_alto_mm(html_str: str) -> float:
    """Alto real del contenido, en milímetros.

    WeasyPrint no acepta `size: 80mm auto` (descarta la regla y cae a A4), así
    que el ticket se renderiza dos veces: la primera sobre una página larguísima
    sólo para medir dónde termina el contenido, la segunda ya con el alto justo.
    Sin esto, cada ticket saldría con decenas de centímetros de papel en blanco.
    """
    doc = HTML(string=html_str, base_url=str(BASE_DIR)).render()
    fondo = 0.0

    def recorrer(caja) -> None:
        nonlocal fondo
        if isinstance(caja, (boxes.LineBox, boxes.TextBox, boxes.ReplacedBox)):
            fondo = max(fondo, caja.position_y + caja.height)
        for hijo in getattr(caja, "children", []) or []:
            recorrer(hijo)

    recorrer(doc.pages[0]._page_box)
    return fondo / 96 * 25.4  # px CSS -> mm


def render_ficha_ticket(ficha: Ficha, url_publica: str | None = None) -> bytes:
    base = _contexto(ficha)
    base.update(
        {
            "ancho_mm": settings.TICKET_ANCHO_MM,
            "margen_mm": settings.TICKET_MARGEN_MM,
            "estado_label": ETIQUETAS_ESTADO[ficha.estado.value],
            "bici_desc": ficha.bicicleta.descripcion if ficha.bicicleta else None,
            "servicios": [ETIQUETAS_SERVICIO.get(s, s) for s in (ficha.servicios or [])],
            "repuestos": [
                {
                    "cantidad": f"{r.cantidad:g}",
                    "descripcion": r.descripcion,
                    "marca": r.marca or "",
                    "subtotal": _monto(r.subtotal),
                }
                for r in ficha.repuestos
            ],
            "firma_cliente": _firma_utilizable(ficha.firma_cliente),
            "firma_tecnico": _firma_utilizable(ficha.firma_tecnico),
            "qr": _qr_data_url(url_publica) if url_publica else None,
            # Se imprime bajo el QR: si la cámara no lee el código (papel
            # arrugado, poca luz), el cliente puede dictarlo por teléfono.
            "codigo_publico": ficha.codigo_publico if url_publica else None,
        }
    )

    plantilla = _env().get_template("ticket.html")

    sonda = plantilla.render(**base, alto_mm=ALTO_SONDA_MM)
    alto = _medir_alto_mm(sonda) + settings.TICKET_MARGEN_MM + COLA_CORTE_MM

    final = plantilla.render(**base, alto_mm=round(alto, 1))
    return HTML(string=final, base_url=str(BASE_DIR)).write_pdf()
