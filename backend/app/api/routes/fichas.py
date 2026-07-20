import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.api.deps import bearer_scheme, get_current_user, require_permission
from app.core.config import settings
from app.core.security import create_print_token, decode_token
from app.db.session import get_db
from app.models.bicicleta import Bicicleta
from app.models.cliente import Cliente
from app.models.ficha import (
    ESTADOS_FINALES,
    ETIQUETAS_ESTADO,
    EstadoFicha,
    Ficha,
    FichaEstadoLog,
    FichaRepuesto,
)
from app.models.user import User
from app.schemas.ficha import (
    CambioEstadoIn,
    CompartirOut,
    ConteoEstados,
    FichaCreate,
    FichaDetail,
    FichaOut,
    FichaPage,
    FichaUpdate,
    FirmaIn,
    RepuestoIn,
)
from app.services.ficha_inventario import devolver_todo, sincronizar_consumo, validar_productos
from app.services.ficha_pdf import render_ficha_pdf, render_ficha_ticket
from app.services.whatsapp import enlace_whatsapp, mensaje_ficha, normalizar_telefono

router = APIRouter(prefix="/fichas", tags=["fichas"])


def _siguiente_numero(db: Session) -> str:
    """Correlativo de 6 dígitos desde la secuencia de Postgres."""
    valor = db.scalar(text("SELECT nextval('ficha_numero_seq')"))
    return f"{valor:06d}"


def _url_publica(ficha: Ficha, con_expiracion: bool = False):
    """URL del PDF firmada con JWT, abrible sin sesión. Para WhatsApp."""
    token, expira = create_print_token(str(ficha.id))
    url = f"{settings.PUBLIC_BASE_URL}{settings.API_V1_PREFIX}/fichas/{ficha.id}/pdf?t={token}"
    return (url, expira) if con_expiracion else url


def _url_qr(ficha: Ficha) -> str:
    """URL corta para el QR del ticket.

    Va por el código corto y no por el JWT: el token deja un QR de versión 14
    (~0.34 mm por módulo en 26 mm), justo en el límite de una térmica de
    203 dpi. El código corto lo baja a versión 3 (~0.79 mm), con margen para
    papel gastado o cabezal sucio.
    """
    return f"{settings.PUBLIC_BASE_URL}/f/{ficha.codigo_publico}"


def _get_ficha(db: Session, ficha_id: uuid.UUID) -> Ficha:
    ficha = db.get(Ficha, ficha_id)
    if ficha is None:
        raise HTTPException(status_code=404, detail="Ficha no encontrada")
    return ficha


def _reemplazar_repuestos(
    db: Session,
    ficha: Ficha,
    filas: list[RepuestoIn],
    actor_id: uuid.UUID | None,
) -> None:
    """Reemplaza la tabla de repuestos y ajusta el stock por diferencia.

    El orden importa: la sincronización necesita comparar contra los repuestos
    que la ficha tenía, así que se calcula ANTES de vaciarlos.
    """
    validar_productos(db, filas)
    sincronizar_consumo(db, ficha, filas, actor_id)

    ficha.repuestos.clear()
    db.flush()
    for i, r in enumerate(filas):
        ficha.repuestos.append(
            FichaRepuesto(
                orden=i,
                cantidad=r.cantidad,
                descripcion=r.descripcion,
                marca=r.marca,
                precio_unitario=r.precio_unitario,
                producto_id=r.producto_id,
            )
        )


@router.get("/conteos", response_model=ConteoEstados)
def conteos(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("fichas.ver")),
    search: str | None = Query(default=None),
) -> ConteoEstados:
    """Contadores por estado para las tabs del listado."""
    # Sin las archivadas, para que el número de la pestaña cuadre con las filas.
    stmt = (
        select(Ficha.estado, func.count(Ficha.id))
        .join(Cliente)
        .join(Bicicleta)
        .where(Ficha.archivada_at.is_(None))
    )

    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                Ficha.numero.like(f"%{search.strip()}%"),
                func.lower(Cliente.nombre).like(like),
                func.lower(Bicicleta.marca).like(like),
            )
        )

    filas = db.execute(stmt.group_by(Ficha.estado)).all()
    por_estado = {e.value: 0 for e in EstadoFicha}
    for estado, cantidad in filas:
        por_estado[estado.value] = cantidad

    archivadas = (
        db.scalar(select(func.count()).select_from(Ficha).where(Ficha.archivada_at.is_not(None)))
        or 0
    )

    return ConteoEstados(
        todas=sum(por_estado.values()), por_estado=por_estado, archivadas=archivadas
    )


@router.get("", response_model=FichaPage)
def list_fichas(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("fichas.ver")),
    search: str | None = Query(default=None, description="N° de ficha, cliente o bicicleta"),
    estado: EstadoFicha | None = Query(default=None),
    cliente_id: uuid.UUID | None = Query(default=None),
    bicicleta_id: uuid.UUID | None = Query(default=None),
    archivadas: bool = Query(
        default=False, description="true devuelve sólo las archivadas, no las del tablero"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> FichaPage:
    # Lo archivado se excluye por defecto: cualquier consumidor que no sepa de
    # esta bandera sigue viendo el tablero del taller y no el archivo entero.
    stmt = select(Ficha).join(Cliente).join(Bicicleta)
    stmt = stmt.where(
        Ficha.archivada_at.is_not(None) if archivadas else Ficha.archivada_at.is_(None)
    )

    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                Ficha.numero.like(f"%{search.strip()}%"),
                func.lower(Cliente.nombre).like(like),
                func.lower(Cliente.numero_documento).like(like),
                func.lower(Bicicleta.marca).like(like),
                func.lower(func.coalesce(Bicicleta.numero_serie, "")).like(like),
            )
        )
    if estado:
        stmt = stmt.where(Ficha.estado == estado)
    if cliente_id:
        stmt = stmt.where(Ficha.cliente_id == cliente_id)
    if bicicleta_id:
        stmt = stmt.where(Ficha.bicicleta_id == bicicleta_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        db.scalars(
            stmt.order_by(Ficha.fecha_recepcion.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .unique()
        .all()
    )

    return FichaPage(
        items=[FichaOut.model_validate(f) for f in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{ficha_id}", response_model=FichaDetail)
def get_ficha(
    ficha_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("fichas.ver")),
) -> Ficha:
    return _get_ficha(db, ficha_id)


@router.post("", response_model=FichaDetail, status_code=status.HTTP_201_CREATED)
def create_ficha(
    data: FichaCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("fichas.crear")),
) -> Ficha:
    cliente = db.get(Cliente, data.cliente_id)
    if cliente is None:
        raise HTTPException(status_code=422, detail="El cliente indicado no existe")

    bici = db.get(Bicicleta, data.bicicleta_id)
    if bici is None:
        raise HTTPException(status_code=422, detail="La bicicleta indicada no existe")

    # La ficha impresa asume que la bici pertenece al cliente que la trae.
    # Aceptar una combinación cruzada produciría un PDF con datos incoherentes.
    if bici.cliente_id != cliente.id:
        raise HTTPException(
            status_code=422,
            detail=f"La bicicleta pertenece a {bici.cliente.nombre}, no a {cliente.nombre}",
        )

    ficha = Ficha(
        numero=_siguiente_numero(db),
        cliente_id=cliente.id,
        bicicleta_id=bici.id,
        estado=EstadoFicha.RECIBIDA,
        fecha_recepcion=data.fecha_recepcion or datetime.now(UTC),
        tecnico_recepcion_id=data.tecnico_recepcion_id or actor.id,
        tecnico_responsable_id=data.tecnico_responsable_id,
        canal_referencia=data.canal_referencia,
        servicios=[s.value for s in data.servicios],
        servicio_otro=data.servicio_otro,
        diagnostico_inicial=data.diagnostico_inicial,
        trabajo_realizado=data.trabajo_realizado,
        tiempo_invertido_min=data.tiempo_invertido_min,
        observaciones=data.observaciones,
        garantia_dias=data.garantia_dias,
    )
    db.add(ficha)
    db.flush()

    _reemplazar_repuestos(db, ficha, data.repuestos, actor.id)
    ficha.historial_estados.append(
        FichaEstadoLog(
            estado_anterior=None,
            estado_nuevo=EstadoFicha.RECIBIDA,
            usuario_id=actor.id,
            comentario="Ficha creada",
        )
    )

    db.commit()
    db.refresh(ficha)
    return ficha


@router.patch("/{ficha_id}", response_model=FichaDetail)
def update_ficha(
    ficha_id: uuid.UUID,
    data: FichaUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("fichas.editar")),
) -> Ficha:
    ficha = _get_ficha(db, ficha_id)

    # Una ficha entregada es el respaldo de lo que se cobró y se firmó:
    # editarla después cambiaría el documento que el cliente ya se llevó.
    if ficha.estado in ESTADOS_FINALES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La ficha está {ficha.estado.value} y ya no admite cambios",
        )

    changes = data.model_dump(exclude_unset=True)
    repuestos = changes.pop("repuestos", None)

    if "servicios" in changes and changes["servicios"] is not None:
        changes["servicios"] = [
            s.value if hasattr(s, "value") else s for s in changes["servicios"]
        ]

    for field, value in changes.items():
        setattr(ficha, field, value)

    if repuestos is not None:
        _reemplazar_repuestos(db, ficha, [RepuestoIn(**r) for r in repuestos], actor.id)

    db.commit()
    db.refresh(ficha)
    return ficha


@router.post("/{ficha_id}/estado", response_model=FichaDetail)
def cambiar_estado(
    ficha_id: uuid.UUID,
    data: CambioEstadoIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("fichas.cambiar_estado")),
) -> Ficha:
    ficha = _get_ficha(db, ficha_id)

    if ficha.estado == data.estado:
        raise HTTPException(status_code=409, detail="La ficha ya está en ese estado")
    if ficha.estado in ESTADOS_FINALES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La ficha está {ficha.estado.value}; crea una ficha nueva para reabrir el caso",
        )

    # Entregar sin firmas dejaría al taller sin constancia de la entrega,
    # que es justamente lo que la ficha firmada respalda.
    if data.estado == EstadoFicha.ENTREGADA and not ficha.esta_firmada:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registra la firma del cliente y del técnico antes de marcar la entrega",
        )

    anterior = ficha.estado
    ficha.estado = data.estado

    if data.estado == EstadoFicha.ENTREGADA:
        ficha.fecha_entrega = datetime.now(UTC)
        ficha.tecnico_entrega_id = ficha.tecnico_entrega_id or actor.id

    # Cancelar por esta vía debe devolver el stock igual que por DELETE:
    # si no, el resultado dependería de qué botón se usó.
    if data.estado == EstadoFicha.CANCELADA:
        devolver_todo(db, ficha, actor.id, f"Cancelación de la ficha {ficha.numero}")

    ficha.historial_estados.append(
        FichaEstadoLog(
            estado_anterior=anterior,
            estado_nuevo=data.estado,
            usuario_id=actor.id,
            comentario=data.comentario,
        )
    )

    db.commit()
    db.refresh(ficha)
    return ficha


@router.post("/{ficha_id}/firmas", response_model=FichaDetail)
def registrar_firmas(
    ficha_id: uuid.UUID,
    data: FirmaIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("fichas.firmar")),
) -> Ficha:
    ficha = _get_ficha(db, ficha_id)

    if ficha.estado in ESTADOS_FINALES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La ficha está {ficha.estado.value} y sus firmas ya no se modifican",
        )

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(ficha, field, value)

    if ficha.esta_firmada and ficha.fecha_firma is None:
        ficha.fecha_firma = datetime.now(UTC)

    db.commit()
    db.refresh(ficha)
    return ficha


def _autorizar_impresion(
    ficha_id: uuid.UUID,
    db: Session,
    credentials: HTTPAuthorizationCredentials | None,
    token: str | None,
) -> Ficha:
    """Permite imprimir con sesión iniciada O con un token de impresión.

    El token va en la query porque el navegador no manda cabeceras al abrir
    un enlace pegado desde WhatsApp. Sólo habilita esa ficha: se compara el
    `sub` del token contra el id pedido.
    """
    if token:
        payload = decode_token(token, expected_type="print")
        if payload is None or payload.get("sub") != str(ficha_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El enlace no es válido o ya expiró",
            )
        return _get_ficha(db, ficha_id)

    usuario = get_current_user(credentials=credentials, db=db)
    if not usuario.has_permission("fichas.imprimir"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Permiso requerido: fichas.imprimir"
        )
    return _get_ficha(db, ficha_id)


@router.get("/{ficha_id}/pdf")
def descargar_pdf(
    ficha_id: uuid.UUID,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    token: str | None = Query(default=None, alias="t", description="Token de impresión"),
    inline: bool = Query(default=True, description="true abre en el visor, false descarga"),
) -> Response:
    ficha = _autorizar_impresion(ficha_id, db, credentials, token)
    pdf = render_ficha_pdf(ficha)

    disposition = "inline" if inline else "attachment"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="ficha-{ficha.numero}.pdf"',
        },
    )


@router.get("/{ficha_id}/ticket")
def descargar_ticket(
    ficha_id: uuid.UUID,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    token: str | None = Query(default=None, alias="t"),
    con_qr: bool = Query(default=True, description="Incluye el QR al enlace público"),
) -> Response:
    """Ticket de 80 mm para impresora térmica, con alto ajustado al contenido."""
    ficha = _autorizar_impresion(ficha_id, db, credentials, token)

    pdf = render_ficha_ticket(ficha, url_publica=_url_qr(ficha) if con_qr else None)

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="ticket-{ficha.numero}.pdf"',
        },
    )


@router.post("/{ficha_id}/compartir", response_model=CompartirOut)
def compartir(
    ficha_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("fichas.imprimir")),
    telefono: str | None = Query(
        default=None, description="Sobrescribe el teléfono del cliente"
    ),
) -> CompartirOut:
    """Genera el enlace público de la ficha y el enlace de WhatsApp al cliente."""
    ficha = _get_ficha(db, ficha_id)

    url, expira = _url_publica(ficha, con_expiracion=True)
    destino = telefono or ficha.cliente.telefono
    mensaje = mensaje_ficha(ficha, url)

    return CompartirOut(
        url_pdf=url,
        expira_en=expira,
        telefono=normalizar_telefono(destino),
        whatsapp_url=enlace_whatsapp(destino, mensaje),
        mensaje=mensaje,
    )


@router.post("/{ficha_id}/archivar", response_model=FichaDetail)
def archivar_ficha(
    ficha_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("fichas.editar")),
) -> Ficha:
    """Saca la ficha del tablero del taller sin tocar su contenido.

    Sólo se archiva lo cerrado: una ficha en curso escondida del listado es
    trabajo que se pierde de vista, y ese es justo el error que el tablero
    existe para evitar.
    """
    ficha = _get_ficha(db, ficha_id)

    if ficha.estado not in ESTADOS_FINALES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"La ficha {ficha.numero} sigue en {ETIQUETAS_ESTADO[ficha.estado.value]}; "
                "sólo se archivan las entregadas o canceladas"
            ),
        )

    ficha.archivada_at = datetime.now(UTC)
    db.commit()
    db.refresh(ficha)
    return ficha


@router.post("/{ficha_id}/restaurar", response_model=FichaDetail)
def restaurar_ficha(
    ficha_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("fichas.editar")),
) -> Ficha:
    ficha = _get_ficha(db, ficha_id)
    ficha.archivada_at = None
    db.commit()
    db.refresh(ficha)
    return ficha


@router.delete("/{ficha_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancelar_ficha(
    ficha_id: uuid.UUID,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("fichas.eliminar")),
) -> None:
    """Las fichas no se borran: se cancelan, dejando traza de quién lo hizo."""
    ficha = _get_ficha(db, ficha_id)

    if ficha.estado in ESTADOS_FINALES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La ficha ya está {ficha.estado.value}",
        )

    anterior = ficha.estado
    ficha.estado = EstadoFicha.CANCELADA

    # Las piezas que no llegaron a montarse vuelven al estante. Si no se
    # devolvieran, el almacén las daría por consumidas para siempre.
    devolver_todo(db, ficha, actor.id, f"Cancelación de la ficha {ficha.numero}")

    ficha.historial_estados.append(
        FichaEstadoLog(
            estado_anterior=anterior,
            estado_nuevo=EstadoFicha.CANCELADA,
            usuario_id=actor.id,
            comentario="Ficha cancelada · repuestos devueltos al inventario",
        )
    )
    db.commit()
