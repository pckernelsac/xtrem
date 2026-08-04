"""Consulta de datos de una persona (RENIEC) o empresa (SUNAT) por documento.

Usa **APIsPERU** (`dniruc.apisperu.com`), un servicio independiente del
facturador: si el facturador se cae, el autocompletado del mostrador sigue en
pie. Antes esto colgaba de la API de consultas de FactPro, con el efecto de que
un problema del proveedor tumbaba las dos cosas a la vez.

Sin token configurado, el servicio responde 503 con un mensaje claro.

APIsPERU devuelve los apellidos **ya separados** del nombre de pila, así que no
hace falta partir la cadena del padrón como exigía FactPro; el reordenado
heurístico se conserva sólo para el proveedor viejo.
"""

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

TIMEOUT = 15.0


def _exigir_configurado() -> None:
    if not settings.consulta_documento_disponible:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "La consulta de DNI/RUC no está configurada. Regístrate en "
                "apisperu.com y define APISPERU_TOKEN."
            ),
        )


def _get(ruta: str) -> dict:
    """GET a APIsPERU. El token va en la query, que es como lo exige su API."""
    url = f"{settings.APISPERU_URL}{ruta}"
    try:
        resp = httpx.get(url, params={"token": settings.APISPERU_TOKEN}, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo contactar el servicio de consultas: {exc}",
        ) from exc

    if resp.status_code in (401, 403):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="El token de APIsPERU es inválido o expiró",
        )
    if resp.status_code == 404:
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
        data = resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="El servicio de consultas devolvió una respuesta no válida",
        ) from exc

    # APIsPERU responde 200 con {"success": false, "message": "..."} cuando el
    # documento no existe: para el mostrador eso es un "no encontrado", no un
    # fallo técnico.
    if isinstance(data, dict) and data.get("success") is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(data.get("message") or "No se encontró ese documento"),
        )
    return data


def _nombre_persona(data: dict) -> str:
    """Nombre completo con el nombre de pila **delante**.

    El orden importa: los saludos por WhatsApp toman la primera palabra, así que
    "ROSA QUISPE MAMANI" saluda por el nombre y "QUISPE MAMANI ROSA" saludaría
    por el apellido.
    """
    nombres = str(data.get("nombres") or "").strip()
    paterno = str(data.get("apellidoPaterno") or "").strip()
    materno = str(data.get("apellidoMaterno") or "").strip()
    return " ".join(p for p in (nombres, paterno, materno) if p)


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
    razon = str(data.get("razonSocial") or data.get("nombreComercial") or "").strip()
    if not razon:
        raise HTTPException(status_code=404, detail="No se encontró el RUC en SUNAT")

    # La dirección llega troceada; se arma la parte útil para el comprobante.
    partes = [
        str(data.get(c) or "").strip()
        for c in ("direccion", "distrito", "provincia", "departamento")
    ]
    direccion = " - ".join(p for p in partes if p)

    return {
        "tipo_documento": "RUC",
        "numero_documento": ruc,
        "nombre": razon,
        "direccion": direccion or None,
    }
