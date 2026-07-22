"""Armado de enlaces wa.me para compartir la ficha con el cliente.

No se envía nada desde el servidor: se construye el enlace y lo abre quien
atiende. Así no hace falta la API de WhatsApp Business ni un número verificado,
y el mensaje sale desde el teléfono de la tienda.
"""

import re
from urllib.parse import quote

from app.models.comprobante import ETIQUETAS_TIPO_COMPROBANTE, ComprobanteElectronico
from app.models.ficha import ETIQUETAS_ESTADO, Ficha

#: Perú. Los celulares son 9 dígitos y empiezan con 9.
CODIGO_PAIS = "51"
LARGO_NACIONAL = 9

#: Encabezado y pie comunes a todos los mensajes que salen al cliente.
ENCABEZADO = "*ZONA XTREMA BIKES & COMPONENTES*"
PIE = "_Av. San Carlos N° 177 - Huancayo_"


def normalizar_telefono(telefono: str | None) -> str | None:
    """Devuelve el número en formato internacional sin '+', o None si no sirve.

    Acepta lo que realmente se tipea en el mostrador: '987 654 321',
    '+51 987-654-321', '(051) 987654321'.
    """
    if not telefono:
        return None

    digitos = re.sub(r"\D", "", telefono)
    if not digitos:
        return None

    # Prefijo internacional escrito como 0051
    if digitos.startswith("00"):
        digitos = digitos[2:]

    if len(digitos) == LARGO_NACIONAL and digitos.startswith("9"):
        return CODIGO_PAIS + digitos

    if digitos.startswith(CODIGO_PAIS) and len(digitos) == len(CODIGO_PAIS) + LARGO_NACIONAL:
        return digitos

    # Fijos y números de otros países: se aceptan si tienen largo plausible,
    # pero no se les inventa un código de país.
    if 10 <= len(digitos) <= 15:
        return digitos

    return None


def mensaje_ficha(ficha: Ficha, url_pdf: str) -> str:
    """Mensaje que verá el cliente. Texto plano con formato de WhatsApp."""
    bici = " ".join(p for p in [ficha.bicicleta.marca, ficha.bicicleta.modelo] if p)
    estado = ETIQUETAS_ESTADO[ficha.estado.value]
    nombre_corto = ficha.cliente.nombre.split()[0].title()

    lineas = [
        ENCABEZADO,
        "",
        f"Hola {nombre_corto}, aquí está la ficha de tu bicicleta.",
        "",
        f"*Ficha N°:* {ficha.numero}",
        f"*Bicicleta:* {bici}",
        f"*Estado:* {estado}",
    ]

    if ficha.repuestos:
        lineas.append(f"*Repuestos:* S/ {ficha.total_repuestos:,.2f}")
    if ficha.garantia_dias:
        lineas.append(f"*Garantía:* {ficha.garantia_dias} días")

    lineas += [
        "",
        "Puedes ver y descargar tu ficha aquí:",
        url_pdf,
        "",
        PIE,
    ]
    return "\n".join(lineas)


def mensaje_comprobante(comprobante: ComprobanteElectronico, url_pdf: str) -> str:
    """Mensaje que acompaña al PDF del comprobante enviado al cliente."""
    tipo = ETIQUETAS_TIPO_COMPROBANTE.get(comprobante.tipo.value, "Comprobante")

    # La denominación puede ser el nombre real del cliente o "CLIENTES VARIOS"
    # en una boleta de mostrador; en ese caso se evita un saludo con nombre.
    primera = comprobante.cliente_denominacion.split()[0] if comprobante.cliente_denominacion else ""
    saludo = f"Hola {primera.title()}, " if primera and primera.upper() != "CLIENTES" else "Hola, "

    lineas = [
        ENCABEZADO,
        "",
        f"{saludo}aquí está tu comprobante electrónico.",
        "",
        f"*{tipo} N°:* {comprobante.numero_completo}",
        f"*Fecha:* {comprobante.fecha_emision.strftime('%d/%m/%Y')}",
    ]

    if comprobante.total is not None:
        lineas.append(f"*Total:* S/ {comprobante.total:,.2f}")

    lineas += [
        "",
        "Puedes ver y descargar tu comprobante aquí:",
        url_pdf,
        "",
        PIE,
    ]
    return "\n".join(lineas)


def enlace_whatsapp(telefono: str | None, mensaje: str) -> str:
    """Enlace wa.me. Sin teléfono devuelve el enlace de 'elegir contacto'."""
    texto = quote(mensaje, safe="")
    numero = normalizar_telefono(telefono)
    return f"https://wa.me/{numero}?text={texto}" if numero else f"https://wa.me/?text={texto}"
