"""Armado de enlaces wa.me para compartir la ficha con el cliente.

No se envía nada desde el servidor: se construye el enlace y lo abre quien
atiende. Así no hace falta la API de WhatsApp Business ni un número verificado,
y el mensaje sale desde el teléfono de la tienda.
"""

import re
from urllib.parse import quote

from app.models.comprobante import ETIQUETAS_TIPO_COMPROBANTE, ComprobanteElectronico
from app.models.ficha import Ficha

#: Perú. Los celulares son 9 dígitos y empiezan con 9.
CODIGO_PAIS = "51"
LARGO_NACIONAL = 9

#: Encabezado y pie comunes a todos los mensajes que salen al cliente.
ENCABEZADO = "*ZONA XTREMA BIKES & COMPONENTES*"
PIE = "_Av. San Carlos N° 177 - Huancayo_"

#: Tienda virtual, tal como se invita a visitarla en el mensaje del servicio.
TIENDA_URL = "https://zonaxtrema.pe"

#: Primeras palabras que no son un nombre de persona: aparecen en boletas de
#: mostrador ("CLIENTES VARIOS") y en razones sociales. Con ellas se saluda sin
#: nombre en vez de soltar un "Hola Clientes".
NO_ES_NOMBRE = {"CLIENTES", "CLIENTE", "VARIOS", "PUBLICO", "PÚBLICO", "SIN"}


def nombre_de_pila(nombre_completo: str | None) -> str:
    """Nombre con el que saludar al cliente, o "" si no hay uno utilizable.

    Los nombres se guardan con el nombre de pila delante ("Rosa Quispe
    Mamani"), así que basta la primera palabra. Ese orden lo respeta también la
    consulta a RENIEC, que devuelve los apellidos primero y se reordena al
    traerla; ver `services/consulta_documento.py`.
    """
    partes = (nombre_completo or "").split()
    if not partes:
        return ""
    primera = partes[0]
    return "" if primera.upper() in NO_ES_NOMBRE else primera.title()


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
    """Mensaje que verá el cliente. Texto plano con formato de WhatsApp.

    El detalle del servicio (número, estado, repuestos, garantía) ya no viaja
    en el chat: está completo al otro lado del enlace, que además se mantiene
    al día. Repetirlo aquí sólo alargaba el mensaje con datos que envejecen.
    """
    nombre_corto = nombre_de_pila(ficha.cliente.nombre)
    saludo = f"¡Hola, {nombre_corto}!" if nombre_corto else "¡Hola!"

    return "\n".join(
        [
            f"{saludo} 👋 En ZonaXtrema nos encanta acompañarte y "
            "queremos agradecerte por confiar en nosotros el cuidado de tu "
            "engreída. 🚲✨",
            "",
            "Te compartimos la ficha técnica completa de tu bicicleta. Recuerda "
            "que puedes hacer el seguimiento de tu servicio o pedido en el "
            "siguiente enlace:",
            f"👉 {url_pdf}",
            "",
            "También te invitamos a visitar nuestra tienda virtual:",
            f"👉 {TIENDA_URL}",
            "",
            "¡Muchas gracias por elegirnos! 🚴‍♂️",
        ]
    )


def mensaje_comprobante(comprobante: ComprobanteElectronico, url_pdf: str) -> str:
    """Mensaje que acompaña al PDF del comprobante enviado al cliente."""
    tipo = ETIQUETAS_TIPO_COMPROBANTE.get(comprobante.tipo.value, "Comprobante")

    # La denominación puede ser el nombre real del cliente o "CLIENTES VARIOS"
    # en una boleta de mostrador; en ese caso se evita un saludo con nombre.
    nombre = nombre_de_pila(comprobante.cliente_denominacion)
    saludo = f"Hola {nombre}, " if nombre else "Hola, "

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
    """Enlace de 'click to chat'. Sin teléfono deja elegir el contacto.

    Se usa `api.whatsapp.com/send` y no el acortador `wa.me`: el salto de
    redirección de wa.me estropea los caracteres fuera del plano básico —los
    emojis llegaban al chat como el carácter de reemplazo mientras que las
    tildes, que ocupan menos, pasaban intactas.
    """
    texto = quote(mensaje, safe="")
    numero = normalizar_telefono(telefono)
    base = "https://api.whatsapp.com/send"
    return f"{base}?phone={numero}&text={texto}" if numero else f"{base}?text={texto}"
