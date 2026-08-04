"""Cifrado de los secretos que se guardan en la base.

El certificado digital y las claves SOL se pueden configurar desde la interfaz,
así que acaban en la base de datos. Guardarlos en claro sería regalar la firma
de la empresa a cualquiera que consiga un backup: con el `.pfx` y su clave se
pueden emitir comprobantes en nombre del emisor.

Se cifran con Fernet (AES-128 en CBC con HMAC), derivando la clave de
`SECRET_KEY`. Eso implica algo que conviene tener presente: **cambiar
`SECRET_KEY` deja ilegibles los secretos guardados** y hay que volver a
cargarlos. Es el precio de no añadir otra variable que administrar, y el aviso
está en el mensaje de error.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class ErrorDeCifrado(Exception):
    pass


def _clave() -> bytes:
    """Clave Fernet derivada del SECRET_KEY del despliegue.

    Se usa SHA-256 sobre el secreto con un dominio propio, para que la clave de
    cifrado no coincida con la que firma los JWT aunque salgan del mismo origen.
    """
    material = f"sunat-cpe-cifrado:{settings.SECRET_KEY}".encode()
    return base64.urlsafe_b64encode(hashlib.sha256(material).digest())


def cifrar(datos: bytes | str) -> bytes:
    if isinstance(datos, str):
        datos = datos.encode()
    return Fernet(_clave()).encrypt(datos)


def descifrar(token: bytes) -> bytes:
    try:
        return Fernet(_clave()).decrypt(token)
    except InvalidToken as exc:
        raise ErrorDeCifrado(
            "No se pudo descifrar el dato guardado. Suele significar que "
            "SECRET_KEY cambió después de guardarlo: vuelve a cargar el "
            "certificado y las claves desde Configuración."
        ) from exc


def descifrar_texto(token: bytes | None) -> str:
    return descifrar(token).decode() if token else ""
