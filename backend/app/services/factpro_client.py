"""Cliente HTTP de FactPro, con modo simulación.

Sin token configurado (`settings.factpro_simulado`), no se llama a la API real:
se devuelve una respuesta con la misma forma que la de FactPro para que el
resto del sistema —persistencia, estados, vista de documentos— funcione y se
pueda verificar de punta a punta. Con token, se hace el POST efectivo.
"""

import base64
import hashlib
import secrets
from datetime import datetime
from typing import Any

import httpx

from app.core.config import settings
from app.services.factpro_catalogos import (
    ESTADO_SUNAT_ACEPTADO,
    ESTADO_SUNAT_ANULADO,
    ESTADO_SUNAT_REGISTRADO,
)


class FactProError(Exception):
    """Error de negocio devuelto por FactPro (exito=false) o de transporte."""

    def __init__(self, mensaje: str, respuesta: dict | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.respuesta = respuesta or {}


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.FACTPRO_TOKEN}",
    }


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{settings.FACTPRO_BASE_URL}{path}"
    try:
        resp = httpx.post(
            url, json=payload, headers=_headers(), timeout=settings.FACTPRO_TIMEOUT_SEGUNDOS
        )
    except httpx.HTTPError as exc:
        raise FactProError(f"No se pudo contactar a FactPro: {exc}") from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise FactProError(
            f"FactPro devolvió una respuesta no-JSON (HTTP {resp.status_code})"
        ) from exc

    if not data.get("exito", False):
        raise FactProError(_extraer_error(data), data)
    return data


def _extraer_error(data: dict[str, Any]) -> str:
    """Mensaje de error de FactPro.

    La API real devuelve `{"errors": [{"message": "..."}]}`; la doc mostraba
    un `mensaje` plano. Se contemplan ambas formas.
    """
    errores = data.get("errors")
    if isinstance(errores, list) and errores:
        mensajes = [e.get("message", "") for e in errores if isinstance(e, dict)]
        unido = "; ".join(m for m in mensajes if m)
        if unido:
            return unido
    return data.get("mensaje") or "FactPro rechazó el documento"


# --------------------------------------------------------------------------
# Simulación
# --------------------------------------------------------------------------
def _archivo_nombre(serie: str, numero: int, cod_comprobante: str) -> str:
    return f"{settings.EMISOR_RUC}-{cod_comprobante}-{serie}-{numero}"


def _simular_emision(payload: dict[str, Any], numero: int, cod_comprobante: str) -> dict[str, Any]:
    """Respuesta simulada de una emisión, con la forma real de FactPro.

    En simulación el documento se marca ACEPTADO de una vez: sin SUNAT no hay
    cola de procesamiento que consultar después.
    """
    serie = payload["serie"]
    archivo = _archivo_nombre(serie, numero, cod_comprobante)
    firma = hashlib.sha1(archivo.encode()).digest()  # noqa: S324 - hash de demo, no seguridad

    return {
        "exito": True,
        "mensaje": None,
        "data": {
            "numero": f"{serie}-{numero}",
            "archivo": archivo,
            "letras": "SIMULADO",
            "hash": base64.b64encode(firma).decode(),
            "qr": base64.b64encode(secrets.token_bytes(24)).decode(),
            "tipo_estado": ESTADO_SUNAT_ACEPTADO,
            "descripcion_estado": "ACEPTADO",
        },
        "archivos": {
            "pdf": f"{settings.FACTPRO_BASE_URL.replace('/api/v3', '')}/invoice/{archivo}.pdf",
            "xml": f"{settings.FACTPRO_BASE_URL.replace('/api/v3', '')}/invoice/{archivo}.xml",
            "cdr": f"{settings.FACTPRO_BASE_URL.replace('/api/v3', '')}/invoice/R-{archivo}.zip",
        },
        "eventos": [
            {
                "date": datetime.now().isoformat(sep=" "),
                "description": "SIMULACIÓN: documento aceptado sin envío a SUNAT",
            }
        ],
        "_simulado": True,
    }


def _simular_anulacion(serie: str, numero: int) -> dict[str, Any]:
    return {
        "exito": True,
        "mensaje": None,
        "data": {
            "numero": f"{serie}-{numero}",
            "tipo_estado": ESTADO_SUNAT_ANULADO,
            "descripcion_estado": "ANULADO",
        },
        "archivos": {},
        "_simulado": True,
    }


def _simular_consulta(serie: str, numero: int) -> dict[str, Any]:
    return {
        "exito": True,
        "mensaje": None,
        "data": {
            "numero": f"{serie}-{numero}",
            "tipo_estado": ESTADO_SUNAT_REGISTRADO,
            "descripcion_estado": "REGISTRADO",
        },
        "archivos": {},
        "_simulado": True,
    }


# --------------------------------------------------------------------------
# API pública
# --------------------------------------------------------------------------
def emitir(payload: dict[str, Any], numero_simulado: int, cod_comprobante: str) -> dict[str, Any]:
    """Envía un comprobante. `numero_simulado` sólo se usa en modo simulación
    (con SUNAT real, FactPro asigna el número)."""
    if settings.factpro_simulado:
        return _simular_emision(payload, numero_simulado, cod_comprobante)
    return _post(settings.FACTPRO_PATH_DOCUMENTOS, payload)


def anular(serie: str, numero: int, motivo: str) -> dict[str, Any]:
    if settings.factpro_simulado:
        return _simular_anulacion(serie, numero)
    return _post(
        settings.FACTPRO_PATH_ANULAR,
        {"serie": serie, "numero": str(numero), "motivo": motivo},
    )


def consultar(serie: str, numero: int) -> dict[str, Any]:
    if settings.factpro_simulado:
        return _simular_consulta(serie, numero)
    return _post(
        settings.FACTPRO_PATH_CONSULTA,
        {"serie": serie, "numero": numero},
    )


def descargar_archivo(url: str) -> bytes:
    """Descarga un archivo (PDF/XML/CDR) alojado por FactPro y devuelve sus bytes.

    Sirve para reexponer el PDF a través de nuestro propio dominio, sin
    revelar al cliente la URL de FactPro. Los enlaces de `/file/...` son
    públicos, así que no llevan la cabecera de autorización.
    """
    try:
        resp = httpx.get(
            url, timeout=settings.FACTPRO_TIMEOUT_SEGUNDOS, follow_redirects=True
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise FactProError(f"No se pudo descargar el archivo de FactPro: {exc}") from exc
    return resp.content
