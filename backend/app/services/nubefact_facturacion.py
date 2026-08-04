"""Traducción entre una venta del ERP y el JSON de Nubefact.

Aquí vive la diferencia de fondo con FactPro. FactPro recibía los precios de
mostrador (con IGV) y desglosaba el impuesto por su cuenta; Nubefact exige el
desglose ya hecho —valor unitario sin IGV, subtotal, IGV y total por línea, más
los totales de cabecera— y **valida que la suma de las líneas cuadre con los
totales**. Un céntimo de diferencia es un comprobante rechazado.
"""

from decimal import ROUND_HALF_UP, Decimal

from app.core.config import settings
from app.core.fechas import hoy_local
from app.models.cliente import TipoDocumento
from app.models.comprobante import ComprobanteElectronico, EstadoComprobante, TipoComprobante
from app.models.inventario import TipoItem
from app.models.venta import Venta, VentaItem
from app.services.nubefact_catalogos import (
    DENOMINACION_SIN_CLIENTE,
    MONEDA_SOLES,
    NUM_DOC_SIN_CLIENTE,
    SUNAT_TRANSACTION_VENTA_INTERNA,
    TIPO_COMPROBANTE,
    TIPO_DOC_CLIENTE,
    TIPO_DOC_SIN_CLIENTE,
    TIPO_IGV_GRAVADO,
    TIPO_NOTA_CREDITO_ANULACION,
    UNIDAD_PRODUCTO,
    UNIDAD_SERVICIO,
)

CERO = Decimal("0.00")
CENTIMO = Decimal("0.01")

#: IGV general. El ERP sólo maneja operaciones gravadas.
IGV_TASA = Decimal("0.18")
IGV_PORCENTAJE = Decimal("18.00")

#: Nubefact acepta hasta 10 decimales en los unitarios. Se usan todos: con
#: cantidades mayores que 1, redondear el unitario a 2 haría que
#: `unitario × cantidad` ya no diera el subtotal y el comprobante sería rechazado.
DECIMALES_UNITARIO = Decimal("0.0000000001")


def _dos(valor: Decimal) -> Decimal:
    return valor.quantize(CENTIMO, rounding=ROUND_HALF_UP)


def _unitario(valor: Decimal) -> Decimal:
    return valor.quantize(DECIMALES_UNITARIO, rounding=ROUND_HALF_UP)


def _totales_de_linea(venta: Venta) -> list[Decimal]:
    """Importe final (con IGV) de cada línea, ya con el descuento global repartido.

    El descuento global de la venta no tiene campo propio en el comprobante
    simple, así que se prorratea entre las líneas en proporción a su importe. El
    residuo del redondeo se carga a la línea más grande, de modo que la suma sea
    **exactamente** `venta.total`: si no, la cabecera no cuadraría con el detalle.

    Sin este prorrateo, una venta con descuento global viajaría a SUNAT por un
    importe mayor al que se cobró.
    """
    brutos = [i.subtotal for i in venta.items]
    suma_bruta = sum(brutos, CERO)
    objetivo = venta.total

    if suma_bruta <= CERO:
        return [CERO for _ in brutos]
    if objetivo == suma_bruta:
        return [_dos(b) for b in brutos]

    repartidos = [_dos(b * objetivo / suma_bruta) for b in brutos]

    # El reparto proporcional casi nunca suma justo: el resto va a la línea de
    # mayor importe, que es donde menos se nota y nunca la deja en negativo.
    resto = objetivo - sum(repartidos, CERO)
    if resto != CERO:
        mayor = max(range(len(repartidos)), key=lambda i: repartidos[i])
        repartidos[mayor] = _dos(repartidos[mayor] + resto)

    return repartidos


def _unidad(item: VentaItem) -> str:
    """NIU para bienes, ZZ para servicios. Sin producto enlazado se asume bien."""
    if item.producto is not None and item.producto.tipo is TipoItem.SERVICIO:
        return UNIDAD_SERVICIO
    return UNIDAD_PRODUCTO


def _item_json(item: VentaItem, total_linea: Decimal) -> dict:
    """Una línea del comprobante, desglosada a partir de su importe final.

    Se parte del total (lo que paga el cliente) y de ahí se saca la base: al
    revés —calcular la base y multiplicar— el redondeo haría que el total de la
    línea no coincidiera con el cobrado.
    """
    subtotal = _dos(total_linea / (Decimal("1") + IGV_TASA))
    igv = total_linea - subtotal  # por diferencia: las tres cifras cuadran siempre

    cantidad = item.cantidad if item.cantidad > CERO else Decimal("1")

    # El detalle libre se anexa a la descripción: SUNAT no tiene campo aparte.
    descripcion = f"{item.descripcion} - {item.detalle}" if item.detalle else item.descripcion

    return {
        "unidad_de_medida": _unidad(item),
        "codigo": item.producto.sku if item.producto else "",
        "descripcion": descripcion[:250],
        "cantidad": float(cantidad),
        "valor_unitario": float(_unitario(subtotal / cantidad)),
        "precio_unitario": float(_unitario(total_linea / cantidad)),
        # El descuento ya está aplicado dentro del importe de la línea. Mandarlo
        # además por separado lo descontaría dos veces.
        "descuento": "",
        "subtotal": float(subtotal),
        "tipo_de_igv": TIPO_IGV_GRAVADO,
        "igv": float(igv),
        "total": float(total_linea),
        "anticipo_regularizacion": False,
        "anticipo_documento_serie": "",
        "anticipo_documento_numero": "",
    }


def _datos_cliente(venta: Venta) -> dict:
    """Identidad del receptor. Sin cliente, boleta a 'clientes varios'."""
    if venta.cliente is None:
        return {
            "cliente_tipo_de_documento": TIPO_DOC_SIN_CLIENTE,
            "cliente_numero_de_documento": NUM_DOC_SIN_CLIENTE,
            "cliente_denominacion": DENOMINACION_SIN_CLIENTE,
            "cliente_direccion": "",
            "cliente_email": "",
        }
    c = venta.cliente
    return {
        "cliente_tipo_de_documento": TIPO_DOC_CLIENTE.get(c.tipo_documento, "1"),
        "cliente_numero_de_documento": c.numero_documento,
        "cliente_denominacion": c.nombre[:100],
        "cliente_direccion": (c.direccion or "")[:100],
        "cliente_email": c.email or "",
    }


def codigo_unico(tipo: TipoComprobante, serie: str, numero: int) -> str:
    """Identificador propio para que Nubefact rechace duplicados.

    Si un envío se pierde después de que Nubefact lo registrara, el reintento
    con el mismo código devuelve el error 23 («ya existe») en vez de emitir el
    documento dos veces con números distintos.
    """
    return f"{TIPO_COMPROBANTE[tipo.value]}-{serie}-{numero}"


def construir_payload(venta: Venta, tipo: TipoComprobante, serie: str, numero: int) -> dict:
    """Arma el JSON de emisión. `numero` lo asigna el ERP: Nubefact no numera."""
    totales_linea = _totales_de_linea(venta)
    items = [_item_json(i, t) for i, t in zip(venta.items, totales_linea, strict=True)]

    total_gravada = _dos(sum((Decimal(str(i["subtotal"])) for i in items), CERO))
    total_igv = _dos(sum((Decimal(str(i["igv"])) for i in items), CERO))
    total = _dos(sum((Decimal(str(i["total"])) for i in items), CERO))

    return {
        "tipo_de_comprobante": TIPO_COMPROBANTE[tipo.value],
        "serie": serie,
        "numero": numero,
        "sunat_transaction": SUNAT_TRANSACTION_VENTA_INTERNA,
        **_datos_cliente(venta),
        # Día de Lima y formato DD-MM-AAAA, que es el que exige Nubefact. Con la
        # fecha del servidor, una boleta de las 8 p. m. viajaría fechada mañana.
        "fecha_de_emision": hoy_local().strftime("%d-%m-%Y"),
        "moneda": MONEDA_SOLES,
        "porcentaje_de_igv": float(IGV_PORCENTAJE),
        "total_gravada": float(total_gravada),
        "total_igv": float(total_igv),
        "total": float(total),
        "detraccion": False,
        "observaciones": (venta.notas or "")[:1000],
        "enviar_automaticamente_a_la_sunat": True,
        "enviar_automaticamente_al_cliente": False,
        "formato_de_pdf": "",
        "codigo_unico": codigo_unico(tipo, serie, numero),
        "items": items,
    }


def construir_payload_nota_credito(
    comprobante: ComprobanteElectronico, serie: str, numero: int, motivo: str
) -> dict:
    """Nota de crédito que anula un comprobante ya aceptado por SUNAT."""
    venta = comprobante.venta
    if venta is None:
        raise ValueError("El comprobante no tiene venta asociada")

    payload = construir_payload(venta, TipoComprobante.NOTA_CREDITO, serie, numero)
    payload.update(
        {
            "documento_que_se_modifica_tipo": TIPO_COMPROBANTE[comprobante.tipo.value],
            "documento_que_se_modifica_serie": comprobante.serie,
            "documento_que_se_modifica_numero": comprobante.numero,
            "tipo_de_nota_de_credito": TIPO_NOTA_CREDITO_ANULACION,
            "observaciones": motivo[:1000],
        }
    )
    return payload


# --------------------------------------------------------------------------
# Lectura de la respuesta
# --------------------------------------------------------------------------
def _enlace_pdf(respuesta: dict) -> str | None:
    """URL del PDF.

    `enlace_del_pdf` puede venir vacío; la doc indica que en ese caso se
    construye añadiendo `.pdf` al `enlace`. Sin este respaldo, el enlace público
    que se manda por WhatsApp (/c/{codigo}) quedaría roto.
    """
    directo = (respuesta.get("enlace_del_pdf") or "").strip()
    if directo:
        return directo
    enlace = (respuesta.get("enlace") or "").strip()
    return f"{enlace}.pdf" if enlace else None


def estado_desde_respuesta(respuesta: dict) -> EstadoComprobante:
    """Traduce la respuesta de Nubefact al estado local del comprobante.

    Nubefact no devuelve el `tipo_estado` numérico de SUNAT que usaba FactPro,
    sino un booleano. `aceptada_por_sunat: false` sin error de transporte
    significa que está en cola, no que haya fallado.
    """
    if respuesta.get("aceptada_por_sunat"):
        return EstadoComprobante.ACEPTADO
    if (respuesta.get("sunat_soap_error") or "").strip():
        return EstadoComprobante.ERROR
    return EstadoComprobante.REGISTRADO


def aplicar_respuesta(comprobante: ComprobanteElectronico, respuesta: dict) -> None:
    """Vuelca la respuesta de Nubefact sobre el comprobante."""
    comprobante.respuesta = respuesta
    comprobante.es_simulado = bool(respuesta.get("_simulado"))
    comprobante.estado = estado_desde_respuesta(respuesta)

    comprobante.hash_cpe = respuesta.get("codigo_hash")
    comprobante.qr = respuesta.get("cadena_para_codigo_qr")

    # `sunat_responsecode` es el código de respuesta de SUNAT ("0" = aceptado).
    codigo = respuesta.get("sunat_responsecode")
    comprobante.tipo_estado_sunat = str(codigo)[:4] if codigo is not None else None

    descripcion = respuesta.get("sunat_description") or respuesta.get("sunat_note") or ""
    comprobante.descripcion_estado_sunat = str(descripcion)[:300] or None

    comprobante.pdf_url = _enlace_pdf(respuesta)
    comprobante.xml_url = (respuesta.get("enlace_del_xml") or "").strip() or None
    comprobante.cdr_url = (respuesta.get("enlace_del_cdr") or "").strip() or None

    error = (respuesta.get("sunat_soap_error") or "").strip()
    comprobante.mensaje_error = error or None


def es_ruc(venta: Venta) -> bool:
    return bool(venta.cliente and venta.cliente.tipo_documento is TipoDocumento.RUC)


def serie_para(tipo: TipoComprobante, sobre_factura: bool = False) -> str:
    """Serie configurada para cada tipo de documento.

    Nubefact exige 4 caracteres y que las notas empiecen por la misma letra que
    el documento que modifican: F para facturas, B para boletas.
    """
    if tipo is TipoComprobante.FACTURA:
        return settings.SERIE_FACTURA
    if tipo is TipoComprobante.BOLETA:
        return settings.SERIE_BOLETA
    return settings.SERIE_NC_FACTURA if sobre_factura else settings.SERIE_NC_BOLETA
