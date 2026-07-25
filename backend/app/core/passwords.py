"""Política de contraseñas.

Se sigue el criterio del NIST: manda la longitud y se rechaza lo que ya está en
los diccionarios de ataque. No se exigen mayúsculas ni símbolos —esas reglas
empujan a `Password1!` y a apuntarla en un papel— sino que se descarta lo que
un atacante prueba en los primeros mil intentos.
"""

import re

LARGO_MINIMO = 8

#: Lo que de verdad se prueba primero contra un ERP peruano: claves de lista
#: universal más las que salen del nombre del propio negocio.
PROHIBIDAS = {
    "12345678",
    "123456789",
    "1234567890",
    "password",
    "password1",
    "passw0rd",
    "qwertyui",
    "qwerty123",
    "iloveyou",
    "princess",
    "abc12345",
    "contrasena",
    "contraseña",
    "administrador",
    "admin123",
    "admin1234",
    "zonaxtrema",
    "zonaxtrema1",
    "bicicleta",
    "huancayo",
}


def validar_password(valor: str) -> str:
    """Devuelve la contraseña si es aceptable; si no, lanza `ValueError`.

    Pensado para usarse desde un validador de Pydantic, que convierte el
    mensaje en un 422 legible para quien la está eligiendo.
    """
    if len(valor) < LARGO_MINIMO:
        raise ValueError(f"La contraseña debe tener al menos {LARGO_MINIMO} caracteres")

    normalizada = valor.strip().lower()

    if normalizada in PROHIBIDAS:
        raise ValueError("Esa contraseña es demasiado común: elige otra")

    # "aaaaaaaa", "11111111": pasan el largo pero no resisten nada.
    if len(set(valor)) < 3:
        raise ValueError("La contraseña repite siempre los mismos caracteres")

    # Secuencias de teclado o de dígitos corridos, en cualquier sentido.
    seguidos = "abcdefghijklmnopqrstuvwxyz0123456789qwertyuiopasdfghjklzxcvbnm"
    if normalizada in seguidos or normalizada in seguidos[::-1]:
        raise ValueError("La contraseña es una secuencia previsible: elige otra")

    # Sólo dígitos: un DNI o una fecha se adivinan por fuerza bruta en segundos.
    if re.fullmatch(r"\d+", valor):
        raise ValueError("La contraseña no puede ser sólo números")

    return valor
