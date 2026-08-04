"""Representación impresa del comprobante electrónico.

Emitiendo directo a SUNAT ya nadie nos aloja un PDF, así que se genera aquí. No
es un problema sino lo contrario: el enlace que se manda por WhatsApp deja de
depender de que un tercero siga en pie, que es exactamente lo que se perdió
cuando el proveedor anterior dejó de responder.

SUNAT obliga a incluir un **código QR** con RUC, tipo, serie-número, IGV, total,
fecha, y tipo y número de documento del receptor, separados por `|`.
"""

from decimal import Decimal

import qrcode
from weasyprint import HTML

from app.core.config import settings
from app.models.comprobante import ETIQUETAS_TIPO_COMPROBANTE, ComprobanteElectronico
from app.services import sunat_adaptador
from app.services.ficha_pdf import (
    BASE_DIR,
    EMPRESA,
    _asset_data_url,
    _env,
    _monto,
)
from app.services.venta_pdf import LIMA, _cantidad

#: Códigos del catálogo 01 de SUNAT, que es lo que va en el QR.
TIPO_SUNAT = {"FACTURA": "01", "BOLETA": "03", "NOTA_CREDITO": "07"}

CERO = Decimal("0.00")


def cadena_qr(comprobante: ComprobanteElectronico) -> str:
    """Cadena que exige SUNAT dentro del QR, con el pipe como separador."""
    return "|".join(
        [
            settings.EMISOR_RUC,
            TIPO_SUNAT.get(comprobante.tipo.value, "01"),
            comprobante.serie,
            str(comprobante.numero),
            f"{comprobante.igv or CERO:.2f}",
            f"{comprobante.total or CERO:.2f}",
            comprobante.fecha_emision.strftime("%Y-%m-%d"),
            comprobante.cliente_tipo_documento,
            comprobante.cliente_numero_documento,
        ]
    )


def _qr_data_url(texto: str) -> str:
    """QR como data URI. Nivel de corrección Q, que es el que pide SUNAT."""
    import base64
    from io import BytesIO

    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=10, border=2
    )
    qr.add_data(texto)
    qr.make(fit=True)
    buffer = BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _lineas(comprobante: ComprobanteElectronico) -> list[dict[str, str]]:
    """Detalle del comprobante, tomado de la venta que lo originó.

    Los importes se reparten con el **mismo prorrateo del descuento global** que
    usó el XML. Sin eso, el papel mostraría las líneas sin descontar y el
    cliente que las sumara no llegaría al total impreso.

    Si la venta ya no existe, el documento se imprime sin detalle pero con sus
    importes, que son los congelados en el propio comprobante y los que tienen
    valor tributario.
    """
    venta = comprobante.venta
    if venta is None:
        return []

    totales = sunat_adaptador._totales_de_linea(venta)
    filas = []
    for item, total in zip(venta.items, totales, strict=True):
        cantidad = item.cantidad if item.cantidad > CERO else Decimal("1")
        filas.append(
            {
                "cantidad": _cantidad(item.cantidad),
                "descripcion": item.descripcion,
                "detalle": item.detalle or "",
                "codigo": item.producto.sku if item.producto else "",
                "precio": _monto(total / cantidad),
                "importe": _monto(total),
            }
        )
    return filas


def render_comprobante_pdf(comprobante: ComprobanteElectronico) -> bytes:
    """Hoja A4 del comprobante, la que recibe el cliente."""
    tipo = ETIQUETAS_TIPO_COMPROBANTE.get(comprobante.tipo.value, "Comprobante")
    cadena = cadena_qr(comprobante)

    empresa = {
        **EMPRESA,
        "razon_social": settings.EMISOR_RAZON_SOCIAL,
        "ruc": settings.EMISOR_RUC,
        "direccion": settings.EMISOR_DIRECCION or EMPRESA["direccion"],
    }

    contexto = {
        "empresa": empresa,
        "logo": _asset_data_url("logo_zonaxtrema.png"),
        "c": comprobante,
        "titulo": tipo.upper(),
        "numero": comprobante.numero_completo,
        "fecha": comprobante.fecha_emision.strftime("%d/%m/%Y"),
        "cliente": {
            "nombre": comprobante.cliente_denominacion,
            "documento": comprobante.cliente_numero_documento,
            "direccion": (
                comprobante.venta.cliente.direccion
                if comprobante.venta and comprobante.venta.cliente
                else ""
            ),
        },
        "lineas": _lineas(comprobante),
        "base": _monto(comprobante.base_imponible or CERO),
        "igv": _monto(comprobante.igv or CERO),
        "total": _monto(comprobante.total or CERO),
        "qr": _qr_data_url(cadena),
        "cadena_qr": cadena,
        "hash": comprobante.hash_cpe or "",
        "estado": comprobante.estado.value,
        "es_simulado": comprobante.es_simulado,
        "anulado": comprobante.baja_pendiente
        or comprobante.estado.value == "ANULADO",
        # Del propio comprobante, no del ajuste actual: un documento emitido
        # en pruebas lo sigue siendo aunque el sistema ya esté en producción.
        "emitido_en_pruebas": not comprobante.emitido_en_produccion,
    }

    html = _env().get_template("comprobante.html").render(**contexto)
    return HTML(string=html, base_url=str(BASE_DIR)).write_pdf()
