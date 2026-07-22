import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import bearer_scheme, get_current_user, require_permission
from app.core.config import settings
from app.core.security import create_print_token, decode_token
from app.db.session import get_db
from app.models.comprobante import ComprobanteElectronico, EstadoComprobante, TipoComprobante
from app.models.user import User
from app.models.venta import Venta
from app.schemas.comprobante import (
    AnularComprobanteIn,
    CompartirComprobanteOut,
    ComprobanteDetail,
    ComprobanteOut,
    ComprobantePage,
    ConteoComprobantes,
    EmitirIn,
)
from app.services import factpro_client
from app.services.facturacion import (
    anular_comprobante,
    consultar_estado,
    emitir_desde_venta,
)
from app.services.facturacion_export import exportar_comprobantes_excel
from app.services.whatsapp import enlace_whatsapp, mensaje_comprobante, normalizar_telefono

router = APIRouter(prefix="/facturacion", tags=["facturación"])


def _get(db: Session, comprobante_id: uuid.UUID) -> ComprobanteElectronico:
    comprobante = db.get(ComprobanteElectronico, comprobante_id)
    if comprobante is None:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")
    return comprobante


def _url_pdf_publica(comprobante: ComprobanteElectronico) -> str:
    """URL del PDF servida por NUESTRO dominio, firmada con un token de impresión.

    Así el cliente nunca ve el enlace de FactPro (que expone su dominio y el
    RUC del emisor): abre una URL nuestra que proxea el archivo.
    """
    token, _ = create_print_token(str(comprobante.id))
    return (
        f"{settings.PUBLIC_BASE_URL}{settings.API_V1_PREFIX}"
        f"/facturacion/documentos/{comprobante.id}/pdf?t={token}"
    )


def _autorizar_comprobante(
    comprobante_id: uuid.UUID,
    db: Session,
    credentials: HTTPAuthorizationCredentials | None,
    token: str | None,
) -> ComprobanteElectronico:
    """Permite servir el PDF con sesión iniciada O con el token de impresión.

    El token va en la query porque el navegador no manda cabeceras al abrir el
    enlace pegado en WhatsApp. Sólo habilita ese comprobante: se compara el
    `sub` del token contra el id pedido.
    """
    if token:
        payload = decode_token(token, expected_type="print")
        if payload is None or payload.get("sub") != str(comprobante_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El enlace no es válido o ya expiró",
            )
        return _get(db, comprobante_id)

    usuario = get_current_user(credentials=credentials, db=db)
    if not usuario.has_permission("facturacion.ver"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permiso requerido: facturacion.ver",
        )
    return _get(db, comprobante_id)


@router.get("/conteos", response_model=ConteoComprobantes)
def conteos(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("facturacion.ver")),
    tipo: TipoComprobante | None = Query(default=None),
) -> ConteoComprobantes:
    stmt = select(ComprobanteElectronico.estado, func.count(ComprobanteElectronico.id))
    if tipo:
        stmt = stmt.where(ComprobanteElectronico.tipo == tipo)

    filas = db.execute(stmt.group_by(ComprobanteElectronico.estado)).all()
    por_estado = {e.value: 0 for e in EstadoComprobante}
    for estado, cantidad in filas:
        por_estado[estado.value] = cantidad

    return ConteoComprobantes(
        todas=sum(por_estado.values()),
        por_estado=por_estado,
        modo_simulacion=settings.factpro_simulado,
    )


@router.get("/documentos", response_model=ComprobantePage)
def list_documentos(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("facturacion.ver")),
    search: str | None = Query(default=None, description="Serie-número o receptor"),
    tipo: TipoComprobante | None = Query(default=None),
    estado: EstadoComprobante | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> ComprobantePage:
    stmt = select(ComprobanteElectronico)

    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(ComprobanteElectronico.serie).like(like),
                func.lower(ComprobanteElectronico.cliente_denominacion).like(like),
                ComprobanteElectronico.cliente_numero_documento.like(f"%{search.strip()}%"),
            )
        )
    if tipo:
        stmt = stmt.where(ComprobanteElectronico.tipo == tipo)
    if estado:
        stmt = stmt.where(ComprobanteElectronico.estado == estado)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        db.scalars(
            stmt.order_by(ComprobanteElectronico.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .unique()
        .all()
    )

    return ComprobantePage(
        items=[ComprobanteOut.model_validate(c) for c in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/documentos/export")
def exportar_documentos(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("facturacion.ver")),
    desde: date = Query(description="Primer día del periodo (fecha de emisión)"),
    hasta: date = Query(description="Último día del periodo, incluido"),
    tipo: TipoComprobante | None = Query(default=None),
    estado: EstadoComprobante | None = Query(default=None),
) -> Response:
    """Registro de ventas del periodo en Excel, para el contador.

    Va por fecha de emisión —no por fecha de creación— porque es la que declara
    el periodo ante SUNAT.
    """
    if hasta < desde:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La fecha final no puede ser anterior a la inicial",
        )

    stmt = select(ComprobanteElectronico).where(
        ComprobanteElectronico.fecha_emision >= desde,
        ComprobanteElectronico.fecha_emision <= hasta,
    )
    if tipo:
        stmt = stmt.where(ComprobanteElectronico.tipo == tipo)
    if estado:
        stmt = stmt.where(ComprobanteElectronico.estado == estado)

    filas = list(
        db.scalars(
            stmt.order_by(
                ComprobanteElectronico.fecha_emision,
                ComprobanteElectronico.serie,
                ComprobanteElectronico.numero,
            )
        )
        .unique()
        .all()
    )

    contenido = exportar_comprobantes_excel(filas, desde, hasta)
    nombre = f"registro-ventas-{desde}-{hasta}.xlsx"
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/documentos/{comprobante_id}", response_model=ComprobanteDetail)
def get_documento(
    comprobante_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("facturacion.ver")),
) -> ComprobanteElectronico:
    return _get(db, comprobante_id)


@router.post("/emitir", response_model=ComprobanteDetail, status_code=status.HTTP_201_CREATED)
def emitir(
    data: EmitirIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("facturacion.emitir")),
) -> ComprobanteElectronico:
    """Emite factura o boleta a partir de una venta confirmada.

    El tipo lo determina el receptor: factura si tiene RUC, boleta en cualquier
    otro caso.
    """
    venta = db.get(Venta, data.venta_id)
    if venta is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    return emitir_desde_venta(db, venta, actor.id)


@router.post("/documentos/{comprobante_id}/whatsapp", response_model=CompartirComprobanteOut)
def compartir_whatsapp(
    comprobante_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("facturacion.ver")),
    telefono: str | None = Query(
        default=None, description="Sobrescribe el teléfono del cliente"
    ),
) -> CompartirComprobanteOut:
    """Arma el enlace de WhatsApp para enviar el PDF del comprobante al cliente.

    No envía nada desde el servidor: devuelve el `wa.me` que abre quien atiende,
    igual que al compartir una ficha. El enlace del PDF apunta a NUESTRO dominio
    y proxea el archivo de FactPro, para no exponer su URL al cliente.
    """
    comprobante = _get(db, comprobante_id)
    if not comprobante.pdf_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El comprobante aún no tiene PDF disponible para compartir",
        )

    # Sin override, se toma el teléfono del cliente de la venta que originó el
    # comprobante; una boleta de mostrador puede no tener cliente registrado.
    destino = telefono
    if not destino and comprobante.venta and comprobante.venta.cliente:
        destino = comprobante.venta.cliente.telefono

    url_pdf = _url_pdf_publica(comprobante)
    mensaje = mensaje_comprobante(comprobante, url_pdf)
    return CompartirComprobanteOut(
        url_pdf=url_pdf,
        telefono=normalizar_telefono(destino),
        whatsapp_url=enlace_whatsapp(destino, mensaje),
        mensaje=mensaje,
    )


@router.get("/documentos/{comprobante_id}/pdf")
def descargar_pdf(
    comprobante_id: uuid.UUID,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    token: str | None = Query(default=None, alias="t", description="Token de impresión"),
) -> Response:
    """Sirve el PDF del comprobante a través de nuestro dominio.

    Proxea el archivo que aloja FactPro para que el enlace compartido no revele
    su URL. Se abre con sesión iniciada o con el token de impresión del enlace.
    """
    comprobante = _autorizar_comprobante(comprobante_id, db, credentials, token)
    if not comprobante.pdf_url:
        raise HTTPException(status_code=404, detail="El comprobante no tiene PDF disponible")

    try:
        contenido = factpro_client.descargar_archivo(comprobante.pdf_url)
    except factpro_client.FactProError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo obtener el PDF: {exc.mensaje}",
        ) from exc

    nombre = f"{comprobante.tipo.value.lower()}-{comprobante.numero_completo}.pdf"
    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )


@router.post("/documentos/{comprobante_id}/anular", response_model=ComprobanteDetail)
def anular(
    comprobante_id: uuid.UUID,
    data: AnularComprobanteIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("facturacion.anular")),
) -> ComprobanteElectronico:
    """Comunica la baja del comprobante a SUNAT. No revierte la venta."""
    comprobante = _get(db, comprobante_id)
    return anular_comprobante(db, comprobante, data.motivo, actor.id)


@router.post("/documentos/{comprobante_id}/consultar", response_model=ComprobanteDetail)
def consultar(
    comprobante_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("facturacion.ver")),
) -> ComprobanteElectronico:
    """Refresca el estado del comprobante contra SUNAT."""
    comprobante = _get(db, comprobante_id)
    return consultar_estado(db, comprobante)
