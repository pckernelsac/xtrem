"""Resuelve la configuración de facturación: base de datos sobre entorno.

Hay dos orígenes y el orden importa. Lo que se carga desde la interfaz **manda**
sobre las variables de entorno; éstas quedan como valor inicial para el primer
arranque y como red de seguridad si la fila aún no existe.

Se resuelve en cada emisión y no al arrancar: cambiar el certificado desde la
aplicación tiene que surtir efecto sin reiniciar el contenedor, que es justo lo
que se busca al poder cargarlo desde ahí.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sunat_cpe import Certificado, Credenciales, Direccion, Emisor, ErrorDeFirma

from app.core.cifrado import ErrorDeCifrado, cifrar, descifrar, descifrar_texto
from app.core.config import settings
from app.models.configuracion import ID_CONFIGURACION, ConfiguracionSunat

#: Se avisa con este margen: renovar un certificado no es inmediato.
DIAS_AVISO_VENCIMIENTO = 30


@dataclass(frozen=True)
class ConfiguracionEfectiva:
    """Lo que realmente se usa al emitir, ya resueltos los dos orígenes."""

    certificado_bytes: bytes | None
    certificado_clave: str
    sol_usuario: str
    sol_clave: str
    produccion: bool
    emisor: Emisor
    serie_factura: str
    serie_boleta: str
    serie_nc_factura: str
    serie_nc_boleta: str
    declaracion_automatica: bool

    @property
    def completa(self) -> bool:
        """¿Se puede emitir de verdad, o toca modo simulación?"""
        return bool(
            self.certificado_bytes
            and self.certificado_clave
            and self.sol_usuario
            and self.sol_clave
        )


def obtener(db: Session) -> ConfiguracionSunat:
    """La fila de configuración, creándola vacía la primera vez."""
    config = db.get(ConfiguracionSunat, ID_CONFIGURACION)
    if config is None:
        config = ConfiguracionSunat(id=ID_CONFIGURACION)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _o(valor: str | None, respaldo: str) -> str:
    """Lo guardado si tiene contenido; si no, lo del entorno."""
    return (valor or "").strip() or respaldo


def _certificado_en_disco() -> Path | None:
    """Certificado montado en el contenedor, si lo hay.

    `.pfx` y `.p12` son el mismo formato PKCS#12 y las entidades certificadoras
    peruanas entregan indistintamente uno u otro. Si la ruta configurada no
    existe, se busca cualquiera de los dos en su carpeta: montar el certificado
    con el nombre correcto y que el sistema no lo vea por la extensión sería un
    fallo tonto de diagnosticar.
    """
    ruta = Path(settings.CERTIFICADO_RUTA)
    if ruta.is_file():
        return ruta

    carpeta = ruta.parent
    if not carpeta.is_dir():
        return None
    candidatos = sorted(
        p for p in carpeta.iterdir() if p.suffix.lower() in (".pfx", ".p12")
    )
    return candidatos[0] if candidatos else None


def resolver(db: Session) -> ConfiguracionEfectiva:
    config = obtener(db)

    certificado_bytes: bytes | None = None
    if config.certificado:
        certificado_bytes = descifrar(config.certificado)
    else:
        ruta = _certificado_en_disco()
        if ruta is not None:
            certificado_bytes = ruta.read_bytes()

    return ConfiguracionEfectiva(
        certificado_bytes=certificado_bytes,
        certificado_clave=(
            descifrar_texto(config.certificado_clave)
            if config.certificado_clave
            else settings.CERTIFICADO_CLAVE
        ),
        sol_usuario=_o(config.sol_usuario, settings.SOL_USUARIO),
        sol_clave=(
            descifrar_texto(config.sol_clave) if config.sol_clave else settings.SOL_CLAVE
        ),
        produccion=config.produccion if config.certificado else settings.SUNAT_PRODUCCION,
        emisor=Emisor(
            ruc=_o(config.ruc, settings.EMISOR_RUC),
            razon_social=_o(config.razon_social, settings.EMISOR_RAZON_SOCIAL),
            nombre_comercial=_o(
                config.nombre_comercial,
                settings.EMISOR_NOMBRE_COMERCIAL or settings.EMISOR_RAZON_SOCIAL,
            ),
            direccion=Direccion(
                ubigeo=_o(config.ubigeo, settings.EMISOR_UBIGEO),
                direccion=_o(config.direccion, settings.EMISOR_DIRECCION),
                departamento=_o(config.departamento, settings.EMISOR_DEPARTAMENTO),
                provincia=_o(config.provincia, settings.EMISOR_PROVINCIA),
                distrito=_o(config.distrito, settings.EMISOR_DISTRITO),
            ),
        ),
        serie_factura=_o(config.serie_factura, settings.SERIE_FACTURA),
        serie_boleta=_o(config.serie_boleta, settings.SERIE_BOLETA),
        serie_nc_factura=_o(config.serie_nc_factura, settings.SERIE_NC_FACTURA),
        serie_nc_boleta=_o(config.serie_nc_boleta, settings.SERIE_NC_BOLETA),
        declaracion_automatica=config.declaracion_automatica,
    )


def certificado_cargado(config: ConfiguracionEfectiva) -> Certificado:
    """Certificado listo para firmar, o un error que dice qué falta."""
    if not config.certificado_bytes:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No hay certificado digital cargado. Súbelo desde Configuración.",
        )
    try:
        return Certificado.desde_pfx(config.certificado_bytes, config.certificado_clave)
    except ErrorDeFirma as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"El certificado digital no se pudo abrir: {exc}",
        ) from exc
    except ErrorDeCifrado as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


def credenciales(config: ConfiguracionEfectiva) -> Credenciales:
    return Credenciales(
        ruc=config.emisor.ruc,
        usuario_sol=config.sol_usuario,
        clave_sol=config.sol_clave,
        produccion=config.produccion,
    )


def _datos_del_certificado(contenido: bytes, clave: str) -> tuple[date, str]:
    """Vencimiento y titular, leídos del propio archivo.

    Se extraen al cargarlo para poder avisar antes de que caduque y para
    comprobar de un vistazo que el certificado es el del emisor correcto.
    """
    try:
        _, cert, _ = pkcs12.load_key_and_certificates(contenido, clave.encode())
    except Exception as exc:  # noqa: BLE001 - se reexpone con contexto
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No se pudo abrir el certificado: revisa que la clave sea correcta. "
                f"({exc})"
            ),
        ) from exc

    if cert is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El archivo no contiene un certificado",
        )

    vence = cert.not_valid_after_utc.date()
    titular = cert.subject.rfc4514_string()[:300]
    return vence, titular


def guardar_certificado(
    db: Session, contenido: bytes, clave: str, nombre: str, actor_id: uuid.UUID | None
) -> ConfiguracionSunat:
    """Valida el `.pfx` y lo guarda cifrado.

    Se valida **antes** de guardar: aceptar un certificado que no abre dejaría
    la facturación caída sin que nadie se entere hasta la siguiente emisión.
    """
    vence, titular = _datos_del_certificado(contenido, clave)

    config = obtener(db)
    config.certificado = cifrar(contenido)
    config.certificado_clave = cifrar(clave)
    config.certificado_nombre = nombre[:200]
    config.certificado_vence = vence
    config.certificado_emitido_a = titular
    config.certificado_cargado_at = datetime.now(timezone.utc)
    config.actualizado_por_id = actor_id
    db.commit()
    db.refresh(config)
    return config


def guardar_credenciales(
    db: Session,
    usuario: str | None,
    clave: str | None,
    actor_id: uuid.UUID | None,
) -> ConfiguracionSunat:
    config = obtener(db)
    if usuario is not None:
        config.sol_usuario = usuario.strip() or None
    # Una clave vacía significa "no la cambies", no "bórrala": el formulario
    # nunca trae la actual, porque no se devuelve por la API.
    if clave:
        config.sol_clave = cifrar(clave)
    config.actualizado_por_id = actor_id
    db.commit()
    db.refresh(config)
    return config
