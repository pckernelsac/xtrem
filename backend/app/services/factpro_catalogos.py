"""Mapeos entre el dominio del ERP y los catálogos que espera FactPro/SUNAT.

FactPro usa un catálogo de tipo de documento PROPIO que NO coincide con el
catálogo 06 de SUNAT (p.ej. usa 4 para RUC, no 6). Verificado emitiendo contra
la API real:
  - DNI  -> "1"  (boleta real emitida y aceptada)
  - RUC  -> "4"  (factura real emitida y aceptada; "6" da "tipo incorrecto")
  - CE / PASAPORTE: aún SIN confirmar contra emisión real. Códigos plausibles
    (7 es pasaporte en SUNAT y FactPro lo acepta como tipo válido), pero deben
    verificarse antes de facturar a un extranjero.
"""

from app.models.cliente import TipoDocumento

TIPO_DOC_CLIENTE: dict[TipoDocumento, str] = {
    TipoDocumento.DNI: "1",   # confirmado
    TipoDocumento.RUC: "4",   # confirmado
    TipoDocumento.CE: "3",    # sin confirmar
    TipoDocumento.PASAPORTE: "7",  # sin confirmar
}

# Boleta a "clientes varios" (venta de mostrador sin identificar).
# FactPro NO acepta el "0" del catálogo SUNAT aquí: exige tipo DNI ("1") con
# número de ceros. Confirmado contra la API real (el "0" da "tipo incorrecto").
TIPO_DOC_SIN_CLIENTE = "1"
NUM_DOC_SIN_CLIENTE = "00000000"

# Catálogo SUNAT 01 — tipo de comprobante.
TIPO_COMPROBANTE_SUNAT = {
    "FACTURA": "01",
    "BOLETA": "03",
    "NOTA_CREDITO": "07",
}

# tipo_tax de FactPro: 1 = gravado (IGV 18%). El ERP hoy sólo maneja ventas
# gravadas; exonerado/inafecto/gratuito se agregarían aquí.
TIPO_TAX_GRAVADO = "1"

# Unidad de medida por defecto (SUNAT 03): NIU = unidad de bien.
UNIDAD_POR_DEFECTO = "NIU"

# tipo_nota (SUNAT 09) para nota de crédito. 01 = anulación de la operación.
TIPO_NOTA_ANULACION = "01"

# Códigos de estado que devuelve SUNAT/FactPro en `tipo_estado`.
ESTADO_SUNAT_REGISTRADO = "01"
ESTADO_SUNAT_ENVIADO = "03"
ESTADO_SUNAT_ANULADO = "04"
ESTADO_SUNAT_ACEPTADO = "05"
ESTADO_SUNAT_RECHAZADO = "06"
