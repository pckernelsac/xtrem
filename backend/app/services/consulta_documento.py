"""Consulta de datos de una persona (RENIEC) o empresa (SUNAT) por documento.

Usa la API de consultas de FactPro (`consultas.factpro.la`), que es un producto
aparte del de facturación y tiene **su propio token** (`FACTPRO_CONSULTAS_TOKEN`).
Sin ese token configurado, el servicio responde 503 con un mensaje claro.

La normalización de la respuesta es defensiva: la doc de FactPro sólo mostraba el
campo `nombres` para DNI, pero RENIEC suele separar apellidos; se arma el nombre
con lo que venga.
"""

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

TIMEOUT = 15.0


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.FACTPRO_CONSULTAS_TOKEN}"}


def _exigir_configurado() -> None:
    if not settings.consulta_documento_disponible:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "La consulta de DNI/RUC no está configurada. Activa el producto "
                "'Consulta RUC y DNI' en FactPro y define FACTPRO_CONSULTAS_TOKEN."
            ),
        )


def _get(ruta: str) -> dict:
    url = f"{settings.FACTPRO_CONSULTAS_URL}{ruta}"
    try:
        resp = httpx.get(url, headers=_headers(), timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo contactar el servicio de consultas: {exc}",
        ) from exc

    if resp.status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="El token de consultas es inválido o el producto no está activo en FactPro",
        )
    # FactPro responde 500 "Ocurrió un error" cuando el documento no existe en
    # el padrón (verificado). Para el usuario es un "no encontrado", no un error
    # técnico; se traduce a 404 con un mensaje accionable.
    if resp.status_code in (404, 500):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró ese documento en RENIEC/SUNAT. Verifica el número.",
        )
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"El servicio de consultas respondió {resp.status_code}",
        )

    try:
        return resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="El servicio de consultas devolvió una respuesta no válida",
        ) from exc


#: Partículas que van pegadas al apellido y no lo dan por terminado:
#: "DE LA CRUZ" es un apellido, no tres. Se listan sin tilde porque se comparan
#: contra el texto del padrón, que viene en mayúsculas y sin acentuar.
PARTICULAS = {
    "DE", "DEL", "LA", "LAS", "LOS", "DA", "DAS", "DI", "DO", "DOS",
    "VAN", "VON", "MC", "MAC", "SAN", "SANTA", "VDA",
}


def _partir_padron(completo: str) -> tuple[str, str]:
    """Parte un nombre en orden de padrón en (nombres de pila, apellidos).

    RENIEC entrega "APELLIDO_PATERNO APELLIDO_MATERNO NOMBRES" en una sola
    cadena, así que los dos primeros apellidos se leen de izquierda a derecha y
    lo que sobra son los nombres de pila:

        "QUISPE MAMANI ROSA MARIA"    -> ("ROSA MARIA", "QUISPE MAMANI")
        "DE LA CRUZ QUISPE JOSE LUIS" -> ("JOSE LUIS", "DE LA CRUZ QUISPE")

    Devuelve ("", completo) cuando no se puede separar con seguridad —menos de
    tres palabras—, para dejar el nombre tal cual en vez de inventarse un corte.
    """
    palabras = completo.split()
    if len(palabras) < 3:
        return "", completo

    i = 0
    apellidos: list[str] = []
    for _ in range(2):  # paterno y materno
        # Las partículas se acumulan hasta llegar al apellido propiamente dicho.
        while i < len(palabras) and palabras[i].upper() in PARTICULAS:
            apellidos.append(palabras[i])
            i += 1
        if i >= len(palabras):
            break
        apellidos.append(palabras[i])
        i += 1

    nombres = palabras[i:]
    if not nombres or not apellidos:
        return "", completo
    return " ".join(nombres), " ".join(apellidos)


def _nombre_persona(data: dict) -> str:
    """Arma el nombre completo con los campos que existan.

    El orden es *nombres primero* ("ROSA QUISPE MAMANI"), no el del padrón
    ("QUISPE MAMANI ROSA"): así el nombre de pila queda al inicio y los saludos
    al cliente —WhatsApp, sobre todo— dicen el nombre y no el apellido.
    """
    ap_paterno = str(data.get("apellido_paterno") or data.get("apellidoPaterno") or "").strip()
    ap_materno = str(data.get("apellido_materno") or data.get("apellidoMaterno") or "").strip()

    for clave in ("nombres", "nombre", "nombre_completo", "nombreCompleto", "nombres_completos"):
        valor = str(data.get(clave) or "").strip()
        if not valor:
            continue
        if ap_paterno or ap_materno:
            # Vienen los apellidos aparte: `valor` son sólo los nombres de pila.
            return " ".join(p for p in (valor, ap_paterno, ap_materno) if p)
        # Un único campo con todo dentro, que es lo que devuelve hoy la API de
        # consultas de FactPro para DNI: hay que darle la vuelta.
        nombres, apellidos = _partir_padron(valor)
        return f"{nombres} {apellidos}" if nombres else valor

    return " ".join(p for p in (ap_paterno, ap_materno) if p)


def consultar_dni(dni: str) -> dict:
    """Devuelve el nombre de la persona por su DNI (8 dígitos)."""
    _exigir_configurado()
    dni = dni.strip()
    if not (dni.isdigit() and len(dni) == 8):
        raise HTTPException(status_code=422, detail="El DNI debe tener 8 dígitos")

    data = _get(f"/dni/{dni}")
    nombre = _nombre_persona(data)
    if not nombre:
        raise HTTPException(status_code=404, detail="No se encontró el DNI en RENIEC")
    return {"tipo_documento": "DNI", "numero_documento": dni, "nombre": nombre, "direccion": None}


def consultar_ruc(ruc: str) -> dict:
    """Devuelve la razón social y dirección de la empresa por su RUC (11 dígitos)."""
    _exigir_configurado()
    ruc = ruc.strip()
    if not (ruc.isdigit() and len(ruc) == 11):
        raise HTTPException(status_code=422, detail="El RUC debe tener 11 dígitos")

    data = _get(f"/ruc/{ruc}")
    razon = data.get("nombre") or data.get("razon_social") or data.get("razonSocial") or ""
    if not razon:
        raise HTTPException(status_code=404, detail="No se encontró el RUC en SUNAT")

    direccion = (
        data.get("direccion_completa") or data.get("direccionCompleta") or data.get("direccion")
    )
    return {
        "tipo_documento": "RUC",
        "numero_documento": ruc,
        "nombre": str(razon).strip(),
        "direccion": (str(direccion).strip() if direccion else None),
    }
