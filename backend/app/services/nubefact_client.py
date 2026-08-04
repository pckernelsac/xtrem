"""Cliente HTTP de Nubefact, con modo simulación.

Nubefact expone **una sola URL** (la RUTA del cliente, con su UUID) para las
cuatro operaciones; lo que las distingue es el campo `operacion` del cuerpo. La
cabecera de autorización lleva el token **pelado**, sin el prefijo `Bearer` que
usaba FactPro.

Sin ruta y token configurados (`settings.factpro_simulado`) no se llama a la
API real: se devuelve una respuesta con la misma forma que la de Nubefact para
que el resto del sistema funcione y se pueda verificar de punta a punta.
"""

import base64
import hashlib
import secrets
from typing import Any

import httpx

from app.core.config import settings
from app.services.nubefact_catalogos import MENSAJES_ERROR

OPERACION_GENERAR = "generar_comprobante"
OPERACION_CONSULTAR = "consultar_comprobante"
OPERACION_ANULAR = "generar_anulacion"
OPERACION_CONSULTAR_ANULACION = "consultar_anulacion"


class NubefactError(Exception):
    """Error de negocio devuelto por Nubefact, o de transporte."""

    def __init__(self, mensaje: str, respuesta: dict | None = None, codigo: int | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.respuesta = respuesta or {}
        #: Código de error de Nubefact (10..51), si lo hubo.
        self.codigo = codigo


def _headers() -> dict[str, str]:
    # OJO: sin "Bearer". Nubefact espera el token tal cual en Authorization.
    return {
        "Content-Type": "application/json",
        "Authorization": settings.NUBEFACT_TOKEN,
    }


def _post(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        resp = httpx.post(
            settings.NUBEFACT_RUTA,
            json=payload,
            headers=_headers(),
            timeout=settings.NUBEFACT_TIMEOUT_SEGUNDOS,
        )
    except httpx.HTTPError as exc:
        raise NubefactError(f"No se pudo contactar a Nubefact: {exc}") from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise NubefactError(
            f"Nubefact devolvió una respuesta no-JSON (HTTP {resp.status_code})"
        ) from exc

    # Nubefact no manda un campo de éxito: el error se reconoce por `errors`.
    if data.get("errors"):
        codigo = data.get("codigo")
        detalle = str(data["errors"])
        # Se antepone el mensaje propio cuando el código es conocido, pero se
        # conserva el texto de Nubefact: suele decir qué campo falló.
        conocido = MENSAJES_ERROR.get(codigo) if isinstance(codigo, int) else None
        mensaje = f"{conocido}: {detalle}" if conocido else detalle
        raise NubefactError(mensaje, data, codigo if isinstance(codigo, int) else None)

    if resp.status_code >= 400:
        raise NubefactError(f"Nubefact respondió HTTP {resp.status_code}", data)

    return data


# --------------------------------------------------------------------------
# Simulación
# --------------------------------------------------------------------------
def _enlace_simulado(serie: str, numero: int) -> str:
    return f"https://www.nubefact.com/cpe/SIMULADO-{serie}-{numero}"


def _simular_emision(payload: dict[str, Any]) -> dict[str, Any]:
    """Respuesta simulada de una emisión, con la forma real de Nubefact.

    Se marca aceptada de una vez: sin SUNAT no hay cola que consultar después.
    """
    serie, numero = payload["serie"], payload["numero"]
    enlace = _enlace_simulado(serie, numero)
    firma = hashlib.sha1(f"{serie}-{numero}".encode()).digest()  # noqa: S324 - demo

    return {
        "tipo_de_comprobante": payload["tipo_de_comprobante"],
        "serie": serie,
        "numero": numero,
        "enlace": enlace,
        "enlace_del_pdf": f"{enlace}.pdf",
        "enlace_del_xml": f"{enlace}.xml",
        "enlace_del_cdr": f"{enlace}.cdr",
        "aceptada_por_sunat": True,
        "sunat_description": "SIMULACIÓN: documento aceptado sin envío a SUNAT",
        "sunat_note": None,
        "sunat_responsecode": "0",
        "sunat_soap_error": "",
        "cadena_para_codigo_qr": (
            f"{settings.EMISOR_RUC}|{payload['tipo_de_comprobante']}|{serie}|{numero}|"
            f"{payload.get('total_igv', 0)}|{payload.get('total', 0)}|"
            f"{payload.get('fecha_de_emision', '')}"
        ),
        "codigo_hash": base64.b64encode(firma).decode(),
        "_simulado": True,
    }


def _simular_anulacion(serie: str, numero: int) -> dict[str, Any]:
    enlace = _enlace_simulado(serie, numero)
    return {
        "numero": numero,
        "enlace": enlace,
        "sunat_ticket_numero": secrets.randbelow(10**13),
        "aceptada_por_sunat": True,
        "sunat_description": "SIMULACIÓN: baja aceptada sin envío a SUNAT",
        "sunat_note": None,
        "sunat_responsecode": "0",
        "sunat_soap_error": "",
        "enlace_del_pdf": f"{enlace}.pdf",
        "_simulado": True,
    }


def _simular_consulta(serie: str, numero: int) -> dict[str, Any]:
    respuesta = _simular_emision(
        {"serie": serie, "numero": numero, "tipo_de_comprobante": 2}
    )
    respuesta["anulado"] = False
    return respuesta


# --------------------------------------------------------------------------
# API pública
# --------------------------------------------------------------------------
def emitir(payload: dict[str, Any]) -> dict[str, Any]:
    """Genera factura, boleta o nota. El payload ya viene armado y numerado."""
    if settings.factpro_simulado:
        return _simular_emision(payload)
    return _post({**payload, "operacion": OPERACION_GENERAR})


def anular(tipo_comprobante: int, serie: str, numero: int, motivo: str) -> dict[str, Any]:
    if settings.factpro_simulado:
        return _simular_anulacion(serie, numero)
    return _post(
        {
            "operacion": OPERACION_ANULAR,
            "tipo_de_comprobante": tipo_comprobante,
            "serie": serie,
            "numero": numero,
            # Nubefact acepta hasta 100 caracteres en el motivo.
            "motivo": motivo[:100],
        }
    )


def consultar(tipo_comprobante: int, serie: str, numero: int) -> dict[str, Any]:
    if settings.factpro_simulado:
        return _simular_consulta(serie, numero)
    return _post(
        {
            "operacion": OPERACION_CONSULTAR,
            "tipo_de_comprobante": tipo_comprobante,
            "serie": serie,
            "numero": numero,
        }
    )


def consultar_anulacion(tipo_comprobante: int, serie: str, numero: int) -> dict[str, Any]:
    """Estado de la comunicación de baja: SUNAT la procesa en diferido."""
    if settings.factpro_simulado:
        return _simular_anulacion(serie, numero)
    return _post(
        {
            "operacion": OPERACION_CONSULTAR_ANULACION,
            "tipo_de_comprobante": tipo_comprobante,
            "serie": serie,
            "numero": numero,
        }
    )


def descargar_archivo(url: str) -> bytes:
    """Descarga un PDF/XML/CDR alojado por Nubefact y devuelve sus bytes.

    Sirve para reexponer el PDF por nuestro dominio (/c/{codigo}) sin revelar
    al cliente la URL del proveedor. Los enlaces son públicos, así que no
    llevan la cabecera de autorización.
    """
    try:
        resp = httpx.get(url, timeout=settings.NUBEFACT_TIMEOUT_SEGUNDOS, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise NubefactError(f"No se pudo descargar el archivo de Nubefact: {exc}") from exc
    return resp.content
