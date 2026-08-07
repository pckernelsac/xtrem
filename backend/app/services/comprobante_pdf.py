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
from sunat_cpe.letras import monto_en_letras
from weasyprint import HTML

from app.core.config import settings
from app.core.fechas import TZ_NEGOCIO
from app.models.comprobante import ETIQUETAS_TIPO_COMPROBANTE, ComprobanteElectronico
from app.services import sunat_adaptador
from app.services.ficha_pdf import (
    BASE_DIR,
    EMPRESA,
    _asset_data_url,
    _env,
    _monto,
)
from app.services.venta_pdf import _cantidad

#: Códigos del catálogo 01 de SUNAT, que es lo que va en el QR.
TIPO_SUNAT = {"FACTURA": "01", "BOLETA": "03", "NOTA_CREDITO": "07"}

CERO = Decimal("0.00")

#: Catálogo 02 de SUNAT. Se imprime el nombre y el código: el nombre lo entiende
#: el cliente y el código es el que viaja en el XML.
MONEDAS = {"PEN": "Soles", "USD": "Dólares americanos", "EUR": "Euros"}


def _moneda(codigo: str) -> str:
    return f"{MONEDAS.get(codigo, codigo)} ({codigo})"


def _fecha_hora(comprobante: ComprobanteElectronico) -> str:
    """Fecha de emisión con la hora, en el huso del taller.

    La **fecha** sale de `fecha_emision`, que es la que tiene efecto tributario y
    la que viaja en el XML. La **hora** sale de `created_at`, que es cuando se
    emitió de verdad; se guarda en UTC, así que hay que traerla a Lima o un
    comprobante de la tarde aparecería emitido de madrugada.
    """
    fecha = comprobante.fecha_emision.strftime("%d/%m/%Y")
    creado = comprobante.created_at
    if creado is None:
        return fecha
    return f"{fecha} · {creado.astimezone(TZ_NEGOCIO).strftime('%H:%M')}"


def cadena_qr(comprobante: ComprobanteElectronico) -> str:
    """Cadena que exige SUNAT dentro del QR, con el pipe como separador.

    El orden y los campos los fija SUNAT y no admiten variación:

        RUC | TIPO | SERIE | NUMERO | IGV | TOTAL | FECHA | TIPO DOC | NUM DOC | HASH |

    El **código hash** es el `DigestValue` de la firma, y va al final. Sin él la
    cadena queda incompleta: es lo que permite verificar que el documento
    impreso se corresponde con el XML firmado, así que un QR sin hash no sirve
    para comprobar nada. La cadena termina en pipe, como en la especificación.

    El RUC sale del propio comprobante y no de la configuración: si el emisor
    cambiara, un documento antiguo debe seguir mostrando el RUC con el que se
    emitió.
    """
    campos = [
        ruc_emisor(comprobante),
        TIPO_SUNAT.get(comprobante.tipo.value, "01"),
        comprobante.serie,
        str(comprobante.numero),
        f"{comprobante.igv or CERO:.2f}",
        f"{comprobante.total or CERO:.2f}",
        comprobante.fecha_emision.strftime("%Y-%m-%d"),
        comprobante.cliente_tipo_documento,
        comprobante.cliente_numero_documento,
        comprobante.hash_cpe or "",
    ]
    return "|".join(campos) + "|"


def ruc_emisor(comprobante: ComprobanteElectronico) -> str:
    """RUC con el que se emitió, leído del XML firmado si está disponible.

    Cae a la configuración actual sólo si el comprobante no guarda el XML, que
    es el caso de los documentos anteriores a la emisión propia.
    """
    xml = comprobante.xml_firmado or ""
    marca = "<cbc:ID schemeID=\"6\""
    inicio = xml.find(marca)
    if inicio != -1:
        cierre = xml.find("</cbc:ID>", inicio)
        valor = xml[xml.find(">", inicio) + 1 : cierre].strip()
        if valor.isdigit() and len(valor) == 11:
            return valor
    return settings.EMISOR_RUC


def url_publica(comprobante: ComprobanteElectronico) -> str:
    """Enlace corto al PDF, el que se manda al cliente.

    Lo sirve `/c/{codigo}` generando el documento al vuelo. Vive aquí, y no
    repetido en cada sitio que lo necesita, porque ya cambió una vez: antes
    apuntaba al servidor del proveedor.
    """
    return f"{settings.PUBLIC_BASE_URL}/c/{comprobante.codigo_publico}"


def nombre_sunat(comprobante: ComprobanteElectronico) -> str:
    """Nombre normalizado del archivo: `RUC-TIPO-SERIE-CORRELATIVO`.

    Es la convención de SUNAT y la que espera el contador, con el correlativo a
    ocho dígitos. Sin ella, un año de comprobantes descargados no ordena ni se
    deja cruzar con lo que la propia SUNAT devuelve.
    """
    return "-".join(
        [
            ruc_emisor(comprobante),
            TIPO_SUNAT.get(comprobante.tipo.value, "01"),
            comprobante.serie,
            f"{comprobante.numero:08d}",
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


def _observaciones(comprobante: ComprobanteElectronico) -> list[str]:
    """Lo que va bajo «Términos y condiciones / Observaciones».

    Se antepone el número de servicio cuando la venta salió del taller: es lo
    que permite al cliente —y a quien atienda una garantía— atar la boleta con
    su reparación, que en papel son dos documentos sin relación aparente.
    """
    venta = comprobante.venta
    if venta is None:
        return []

    lineas = []
    if venta.ficha is not None:
        lineas.append(f"Servicio N° {venta.ficha.numero}")
    if venta.notas:
        lineas.append(venta.notas)
    return lineas


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
        "fecha": _fecha_hora(comprobante),
        "moneda": _moneda(comprobante.moneda),
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
        # El mismo texto que viaja en el XML: sale de la librería, no se
        # recalcula aquí, para que el papel no pueda discrepar del documento
        # firmado.
        "en_letras": monto_en_letras(comprobante.total or CERO, comprobante.moneda),
        # El XML declara siempre contado: en el mostrador se cobra al confirmar
        # la venta, y una emisión a crédito exigiría informar las cuotas.
        "forma_pago": "Contado",
        "observaciones": _observaciones(comprobante),
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
