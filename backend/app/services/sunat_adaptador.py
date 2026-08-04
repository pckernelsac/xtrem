"""Traduce una venta del ERP al comprobante que entiende `sunat_cpe`.

Es la única pieza que conoce a la vez el modelo del negocio y el de la
facturación. Todo lo demás —UBL, firma, envío— vive en la librería, que no sabe
nada de ventas, cajas ni fichas.

El descuento global de la venta se prorratea aquí porque el comprobante no tiene
un campo para él: sin repartirlo, el documento viajaría a SUNAT por un importe
mayor al que se cobró.
"""

from decimal import ROUND_HALF_UP, Decimal

from sunat_cpe import (
    Comprobante,
    Direccion,
    Emisor,
    Linea,
    Receptor,
    Referencia,
    TipoDocumento,
    TipoDocumentoIdentidad,
)
from sunat_cpe.catalogos import MotivoNotaCredito

from app.core.config import settings
from app.core.fechas import hoy_local
from app.models.cliente import TipoDocumento as TipoDocumentoCliente
from app.models.comprobante import ComprobanteElectronico, TipoComprobante
from app.models.inventario import TipoItem
from app.models.venta import Venta, VentaItem

CERO = Decimal("0.00")
CENTIMO = Decimal("0.01")

#: Catálogo 06 de SUNAT. El ERP guarda el tipo con su propio enum.
TIPO_DOCUMENTO_RECEPTOR = {
    TipoDocumentoCliente.DNI: TipoDocumentoIdentidad.DNI,
    TipoDocumentoCliente.RUC: TipoDocumentoIdentidad.RUC,
    TipoDocumentoCliente.CE: TipoDocumentoIdentidad.CARNET_EXTRANJERIA,
    TipoDocumentoCliente.PASAPORTE: TipoDocumentoIdentidad.PASAPORTE,
}

TIPO_COMPROBANTE = {
    TipoComprobante.FACTURA: TipoDocumento.FACTURA,
    TipoComprobante.BOLETA: TipoDocumento.BOLETA,
    TipoComprobante.NOTA_CREDITO: TipoDocumento.NOTA_CREDITO,
}

#: Venta de mostrador sin identificar al cliente.
DOC_SIN_CLIENTE = "00000000"
NOMBRE_SIN_CLIENTE = "CLIENTES VARIOS"


def _dos(valor: Decimal) -> Decimal:
    return valor.quantize(CENTIMO, rounding=ROUND_HALF_UP)


def emisor_configurado() -> Emisor:
    return Emisor(
        ruc=settings.EMISOR_RUC,
        razon_social=settings.EMISOR_RAZON_SOCIAL,
        nombre_comercial=settings.EMISOR_NOMBRE_COMERCIAL or settings.EMISOR_RAZON_SOCIAL,
        direccion=Direccion(
            ubigeo=settings.EMISOR_UBIGEO,
            direccion=settings.EMISOR_DIRECCION,
            departamento=settings.EMISOR_DEPARTAMENTO,
            provincia=settings.EMISOR_PROVINCIA,
            distrito=settings.EMISOR_DISTRITO,
        ),
    )


def receptor_de(venta: Venta) -> Receptor:
    """Identidad del receptor. Sin cliente, boleta a 'clientes varios'."""
    if venta.cliente is None:
        return Receptor(
            tipo_documento=TipoDocumentoIdentidad.SIN_DOCUMENTO,
            numero_documento=DOC_SIN_CLIENTE,
            razon_social=NOMBRE_SIN_CLIENTE,
        )
    c = venta.cliente
    return Receptor(
        tipo_documento=TIPO_DOCUMENTO_RECEPTOR.get(
            c.tipo_documento, TipoDocumentoIdentidad.DNI
        ),
        numero_documento=c.numero_documento,
        razon_social=c.nombre,
        direccion=c.direccion or "",
        email=c.email or "",
    )


def _totales_de_linea(venta: Venta) -> list[Decimal]:
    """Importe final de cada línea, con el descuento global ya repartido.

    El reparto es proporcional al importe, y el residuo del redondeo se carga a
    la línea mayor para que la suma dé **exactamente** `venta.total`. Si no, la
    cabecera del comprobante no cuadraría con su detalle y SUNAT lo rechazaría.
    """
    brutos = [i.subtotal for i in venta.items]
    suma = sum(brutos, CERO)
    objetivo = venta.total

    if suma <= CERO:
        return [CERO for _ in brutos]
    if objetivo == suma:
        return [_dos(b) for b in brutos]

    repartidos = [_dos(b * objetivo / suma) for b in brutos]
    resto = objetivo - sum(repartidos, CERO)
    if resto != CERO:
        mayor = max(range(len(repartidos)), key=lambda i: repartidos[i])
        repartidos[mayor] = _dos(repartidos[mayor] + resto)
    return repartidos


def _unidad(item: VentaItem) -> str:
    """NIU para bienes, ZZ para servicios."""
    if item.producto is not None and item.producto.tipo is TipoItem.SERVICIO:
        return "ZZ"
    return "NIU"


def _linea(item: VentaItem, total: Decimal) -> Linea:
    """Convierte una línea de venta.

    Se pasa el precio unitario ya con el descuento aplicado, en vez de mandar el
    descuento por separado: el importe final de la línea es el que manda, y así
    no hay dos sitios donde el redondeo pueda discrepar.
    """
    cantidad = item.cantidad if item.cantidad > CERO else Decimal("1")
    descripcion = f"{item.descripcion} - {item.detalle}" if item.detalle else item.descripcion

    # La división puede dar un decimal periódico (102.88 / 3). Se acota a los
    # diez decimales que admite SUNAT: con esa precisión, cantidad × unitario
    # sigue redondeando al importe exacto de la línea.
    unitario = (total / cantidad).quantize(
        Decimal("0.0000000001"), rounding=ROUND_HALF_UP
    )

    return Linea(
        codigo=item.producto.sku if item.producto else "",
        descripcion=descripcion[:500],
        unidad=_unidad(item),
        cantidad=cantidad,
        precio_unitario=unitario,
    )


def comprobante_de_venta(
    venta: Venta, tipo: TipoComprobante, serie: str, correlativo: int
) -> Comprobante:
    """Arma el comprobante a partir de la venta. El correlativo lo da el ERP."""
    totales = _totales_de_linea(venta)
    return Comprobante(
        tipo=TIPO_COMPROBANTE[tipo],
        serie=serie,
        correlativo=correlativo,
        fecha_emision=hoy_local(),
        emisor=emisor_configurado(),
        receptor=receptor_de(venta),
        lineas=[_linea(item, total) for item, total in zip(venta.items, totales, strict=True)],
        observaciones=(venta.notas or "")[:500],
    )


def nota_de_credito(
    comprobante: ComprobanteElectronico, serie: str, correlativo: int, motivo: str
) -> Comprobante:
    """Nota de crédito que anula un comprobante ya aceptado por SUNAT."""
    venta = comprobante.venta
    if venta is None:
        raise ValueError("El comprobante no tiene venta asociada")

    nota = comprobante_de_venta(venta, TipoComprobante.NOTA_CREDITO, serie, correlativo)
    nota.referencia = Referencia(
        tipo_documento=TIPO_COMPROBANTE[comprobante.tipo],
        serie_numero=comprobante.numero_completo,
    )
    nota.motivo_nota = MotivoNotaCredito.ANULACION_OPERACION.value
    nota.observaciones = motivo[:500]
    return nota
