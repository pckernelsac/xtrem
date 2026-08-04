"""Configuración de la facturación electrónica.

Permite cargar el certificado digital y las claves SOL sin tocar el despliegue,
que es lo que hace falta cuando el certificado caduca fuera de horario.

**Las claves no se devuelven nunca.** Se pueden reemplazar, no leer: la
respuesta sólo dice si están puestas. Guardarlas en la base ya es un riesgo
suficiente como para además exponerlas por una API.
"""

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.fechas import hoy_local
from app.db.session import get_db
from app.models.user import User
from app.schemas.configuracion import (
    ConfiguracionOut,
    ConfiguracionUpdate,
    LimpiezaOut,
    LimpiezaResultadoOut,
)
from app.services import configuracion_sunat, limpieza_pruebas

router = APIRouter(prefix="/configuracion", tags=["configuración"])

#: Un .pfx real ronda los pocos KB. Un archivo mucho mayor no es un certificado.
TAMANO_MAXIMO = 512 * 1024


def _enmascarar(valor: str | None) -> str | None:
    """Deja ver lo justo para reconocer el dato, no para reutilizarlo.

    El usuario SOL es la mitad de la credencial, así que tampoco se devuelve
    entero: basta con que quien administra reconozca cuál está puesto.
    """
    if not valor:
        return None
    if len(valor) <= 4:
        return "•" * len(valor)
    return f"{valor[:2]}{'•' * (len(valor) - 4)}{valor[-2:]}"


def _salida(db: Session, config) -> ConfiguracionOut:
    efectiva = configuracion_sunat.resolver(db)
    return ConfiguracionOut(
        tiene_certificado=config.tiene_certificado,
        certificado_nombre=config.certificado_nombre,
        certificado_vence=config.certificado_vence,
        certificado_emitido_a=config.certificado_emitido_a,
        certificado_cargado_at=config.certificado_cargado_at,
        dias_para_vencer=config.dias_para_vencer(hoy_local()),
        sol_usuario=_enmascarar(config.sol_usuario),
        tiene_sol_clave=bool(config.sol_clave),
        produccion=efectiva.produccion,
        ruc=efectiva.emisor.ruc,
        razon_social=efectiva.emisor.razon_social,
        nombre_comercial=efectiva.emisor.nombre_comercial,
        ubigeo=efectiva.emisor.direccion.ubigeo,
        direccion=efectiva.emisor.direccion.direccion,
        departamento=efectiva.emisor.direccion.departamento,
        provincia=efectiva.emisor.direccion.provincia,
        distrito=efectiva.emisor.direccion.distrito,
        serie_factura=efectiva.serie_factura,
        serie_boleta=efectiva.serie_boleta,
        serie_nc_factura=efectiva.serie_nc_factura,
        serie_nc_boleta=efectiva.serie_nc_boleta,
        declaracion_automatica=efectiva.declaracion_automatica,
        lista_para_emitir=efectiva.completa,
        actualizado_por=(
            config.actualizado_por.full_name if config.actualizado_por else None
        ),
        updated_at=config.updated_at,
    )


@router.get("/sunat", response_model=ConfiguracionOut)
def obtener(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("configuracion.ver")),
) -> ConfiguracionOut:
    return _salida(db, configuracion_sunat.obtener(db))


@router.put("/sunat", response_model=ConfiguracionOut)
def actualizar(
    data: ConfiguracionUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("configuracion.editar")),
) -> ConfiguracionOut:
    """Actualiza emisor, series y credenciales.

    La clave SOL sólo se toca si viene con contenido: el formulario no trae la
    actual —no se devuelve— y un campo vacío significa «déjala como está», no
    «bórrala».
    """
    config = configuracion_sunat.obtener(db)

    for campo in (
        "ruc", "razon_social", "nombre_comercial", "ubigeo", "direccion",
        "departamento", "provincia", "distrito", "serie_factura", "serie_boleta",
        "serie_nc_factura", "serie_nc_boleta",
    ):
        valor = getattr(data, campo)
        if valor is not None:
            setattr(config, campo, valor.strip() or None)

    if data.produccion is not None:
        config.produccion = data.produccion
    if data.declaracion_automatica is not None:
        config.declaracion_automatica = data.declaracion_automatica

    config.actualizado_por_id = actor.id
    db.commit()

    if data.sol_usuario is not None or data.sol_clave:
        configuracion_sunat.guardar_credenciales(
            db, data.sol_usuario, data.sol_clave, actor.id
        )

    db.refresh(config)
    return _salida(db, config)


@router.post("/sunat/certificado", response_model=ConfiguracionOut)
def subir_certificado(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("configuracion.editar")),
    archivo: UploadFile = File(description="Certificado digital .pfx o .p12"),
    clave: str = Form(description="Clave del certificado"),
) -> ConfiguracionOut:
    """Carga el certificado digital.

    Se valida abriéndolo con la clave **antes** de guardarlo: aceptar uno que no
    abre dejaría la facturación caída sin que nadie se entere hasta la siguiente
    emisión.
    """
    nombre = (archivo.filename or "certificado.pfx").lower()
    if not nombre.endswith((".pfx", ".p12")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El certificado debe ser un archivo .pfx o .p12",
        )

    contenido = archivo.file.read()
    if not contenido:
        raise HTTPException(status_code=422, detail="El archivo está vacío")
    if len(contenido) > TAMANO_MAXIMO:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El archivo es demasiado grande para ser un certificado",
        )

    config = configuracion_sunat.guardar_certificado(
        db, contenido, clave, archivo.filename or nombre, actor.id
    )
    return _salida(db, config)


# --------------------------------------------------------------------------
# Limpieza de documentos de prueba
#
# Probar deja rastro, y el registro de ventas del contador filtra por fecha y
# no por ambiente: sin retirarlos, los comprobantes de prueba acabarían
# declarados como válidos.
# --------------------------------------------------------------------------
@router.get("/sunat/documentos-prueba", response_model=LimpiezaOut)
def resumen_documentos_prueba(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("configuracion.ver")),
) -> dict:
    """Qué se borraría, sin borrar nada."""
    return limpieza_pruebas.resumen(db)


@router.delete("/sunat/documentos-prueba", response_model=LimpiezaResultadoOut)
def borrar_documentos_prueba(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("configuracion.editar")),
    confirmar: bool = Query(
        default=False,
        description="Debe ser true. Sin esto no se borra nada.",
    ),
) -> dict:
    """Retira los comprobantes emitidos contra el ambiente de pruebas.

    **No toca lo emitido en producción**: el filtro está en el servicio y no se
    puede pedir otra cosa desde aquí.

    La confirmación explícita es deliberada: el borrado no tiene vuelta atrás y
    una llamada accidental no debería bastar para dispararlo.
    """
    if not confirmar:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Falta la confirmación explícita para borrar",
        )
    return limpieza_pruebas.borrar(db, actor.id)
