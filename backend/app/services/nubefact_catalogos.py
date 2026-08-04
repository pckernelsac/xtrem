"""Mapeos entre el dominio del ERP y los catálogos que espera Nubefact.

A diferencia de FactPro —que usaba un catálogo de tipo de documento propio—,
Nubefact sigue el **catálogo 06 de SUNAT** para el documento del cliente. Los
tipos de comprobante, en cambio, sí son un código propio (1..4) y no el catálogo
01 de SUNAT ("01", "03", "07").
"""

from app.models.cliente import TipoDocumento
from app.models.comprobante import TipoComprobante

#: Catálogo 06 de SUNAT, tal como lo documenta Nubefact.
TIPO_DOC_CLIENTE: dict[TipoDocumento, str] = {
    TipoDocumento.DNI: "1",
    TipoDocumento.RUC: "6",
    TipoDocumento.CE: "4",
    TipoDocumento.PASAPORTE: "7",
}

#: Venta de mostrador sin identificar al cliente. Nubefact tiene un código
#: propio para esto ("-" = VARIOS, ventas menores a S/ 700), así que no hace
#: falta el apaño de FactPro de mandar un DNI de ceros.
TIPO_DOC_SIN_CLIENTE = "-"
NUM_DOC_SIN_CLIENTE = "00000000"
DENOMINACION_SIN_CLIENTE = "CLIENTES VARIOS"

#: Código de comprobante de Nubefact (NO es el catálogo 01 de SUNAT).
TIPO_COMPROBANTE: dict[str, int] = {
    TipoComprobante.FACTURA.value: 1,
    TipoComprobante.BOLETA.value: 2,
    TipoComprobante.NOTA_CREDITO.value: 3,
}

#: Tipo de operación. 1 = venta interna, que es todo lo que hace el taller.
SUNAT_TRANSACTION_VENTA_INTERNA = 1

#: Moneda. 1 = soles.
MONEDA_SOLES = 1

#: tipo_de_igv 1 = Gravado, operación onerosa. El ERP sólo maneja ventas
#: gravadas; exonerado (8) o inafecto (9) se agregarían aquí.
TIPO_IGV_GRAVADO = 1

#: Unidad de medida (catálogo 03 de SUNAT). NIU = producto, ZZ = servicio.
UNIDAD_PRODUCTO = "NIU"
UNIDAD_SERVICIO = "ZZ"

#: Tipo de nota de crédito. 1 = anulación de la operación.
TIPO_NOTA_CREDITO_ANULACION = 1

#: Códigos de error que devuelve Nubefact en el campo `codigo`.
ERROR_TOKEN = 10
ERROR_RUTA = 11
ERROR_CONTENT_TYPE = 12
ERROR_FORMATO = 20
ERROR_OPERACION = 21
ERROR_FUERA_DE_PLAZO = 22
ERROR_YA_EXISTE = 23
ERROR_NO_EXISTE = 24
ERROR_INTERNO = 40
ERROR_CUENTA_SUSPENDIDA = 50
ERROR_CUENTA_IMPAGA = 51

#: Mensajes en castellano de mostrador para los errores que puede ver el
#: usuario. El resto se muestra tal como lo manda Nubefact.
MENSAJES_ERROR: dict[int, str] = {
    ERROR_TOKEN: "El token de Nubefact es incorrecto o fue eliminado",
    ERROR_RUTA: "La ruta de Nubefact no es correcta; revísala en su panel (API-Integración)",
    ERROR_CONTENT_TYPE: "Solicitud mal formada: falta el Content-Type",
    ERROR_FUERA_DE_PLAZO: "El comprobante se envió fuera del plazo que permite SUNAT",
    ERROR_YA_EXISTE: "Ese comprobante ya fue registrado en Nubefact",
    ERROR_NO_EXISTE: "El comprobante no existe en Nubefact",
    ERROR_CUENTA_SUSPENDIDA: "La cuenta de Nubefact está suspendida",
    ERROR_CUENTA_IMPAGA: "La cuenta de Nubefact está suspendida por falta de pago",
}
