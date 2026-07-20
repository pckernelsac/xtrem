import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.fechas import hoy_local, inicio_del_dia, rango_utc
from app.db.session import get_db
from app.models.cliente import Cliente
from app.models.ficha import Ficha
from app.models.user import User
from app.models.venta import EstadoVenta, TipoVenta, Venta
from app.schemas.venta import (
    AnularIn,
    ConteoVentas,
    ConvertirIn,
    VentaCreate,
    VentaDetail,
    VentaOut,
    VentaPage,
    VentaUpdate,
)
from app.services.venta_pdf import render_venta_pdf, render_venta_ticket
from app.services.venta import (
    anular_venta,
    confirmar_venta,
    reemplazar_items,
    siguiente_numero,
    validar_productos,
)

router = APIRouter(prefix="/ventas", tags=["ventas"])


def _get_venta(db: Session, venta_id: uuid.UUID) -> Venta:
    venta = db.get(Venta, venta_id)
    if venta is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada")
    return venta


def _validar_relaciones(db: Session, cliente_id, ficha_id) -> None:
    if cliente_id and db.get(Cliente, cliente_id) is None:
        raise HTTPException(status_code=422, detail="El cliente indicado no existe")
    if ficha_id and db.get(Ficha, ficha_id) is None:
        raise HTTPException(status_code=422, detail="La ficha indicada no existe")


@router.get("/conteos", response_model=ConteoVentas)
def conteos(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ventas.ver")),
    tipo: TipoVenta | None = Query(default=None),
) -> ConteoVentas:
    # Sin archivadas, para que el número de la pestaña cuadre con las filas.
    stmt = select(Venta.estado, func.count(Venta.id)).where(Venta.archivada_at.is_(None))
    if tipo:
        stmt = stmt.where(Venta.tipo == tipo)

    filas = db.execute(stmt.group_by(Venta.estado)).all()
    por_estado = {e.value: 0 for e in EstadoVenta}
    for estado, cantidad in filas:
        por_estado[estado.value] = cantidad

    archivadas_stmt = select(func.count()).select_from(Venta).where(Venta.archivada_at.is_not(None))
    if tipo:
        archivadas_stmt = archivadas_stmt.where(Venta.tipo == tipo)

    return ConteoVentas(
        todas=sum(por_estado.values()),
        por_estado=por_estado,
        archivadas=db.scalar(archivadas_stmt) or 0,
    )


@router.get("", response_model=VentaPage)
def list_ventas(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ventas.ver")),
    search: str | None = Query(default=None, description="N° de documento o cliente"),
    tipo: TipoVenta | None = Query(default=None),
    estado: EstadoVenta | None = Query(default=None),
    cliente_id: uuid.UUID | None = Query(default=None),
    sesion_caja_id: uuid.UUID | None = Query(
        default=None, description="Ventas cobradas en una jornada de caja concreta"
    ),
    desde: date | None = Query(default=None, description="Fecha de emisión, inclusive"),
    hasta: date | None = Query(default=None, description="Fecha de emisión, inclusive"),
    archivadas: bool = Query(
        default=False, description="true devuelve sólo las archivadas"
    ),
    incluir_archivadas: bool = Query(
        default=False,
        description=(
            "Ignora el filtro de archivado y devuelve ambas. Para vistas contables "
            "—el arqueo de caja— donde archivar no debe descuadrar el total del día."
        ),
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> VentaPage:
    # Lo archivado se excluye por defecto: quien no conozca esta bandera sigue
    # viendo el listado de trabajo, no el archivo completo.
    stmt = select(Venta).outerjoin(Cliente, Venta.cliente_id == Cliente.id)
    if not incluir_archivadas:
        stmt = stmt.where(
            Venta.archivada_at.is_not(None) if archivadas else Venta.archivada_at.is_(None)
        )

    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Venta.numero).like(like),
                func.lower(func.coalesce(Cliente.nombre, "")).like(like),
                func.lower(func.coalesce(Cliente.numero_documento, "")).like(like),
            )
        )
    if tipo:
        stmt = stmt.where(Venta.tipo == tipo)
    if estado:
        stmt = stmt.where(Venta.estado == estado)
    if cliente_id:
        stmt = stmt.where(Venta.cliente_id == cliente_id)
    if sesion_caja_id:
        stmt = stmt.where(Venta.sesion_caja_id == sesion_caja_id)
    # Los días son días del taller (Lima), aunque `created_at` esté en UTC.
    ini, fin = rango_utc(desde, hasta)
    if ini:
        stmt = stmt.where(Venta.created_at >= ini)
    if fin:
        stmt = stmt.where(Venta.created_at < fin)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        db.scalars(
            stmt.order_by(Venta.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        .unique()
        .all()
    )

    return VentaPage(
        items=[VentaOut.model_validate(v) for v in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{venta_id}", response_model=VentaDetail)
def get_venta(
    venta_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ventas.ver")),
) -> Venta:
    return _get_venta(db, venta_id)


@router.post("", response_model=VentaDetail, status_code=status.HTTP_201_CREATED)
def create_venta(
    data: VentaCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("ventas.crear")),
) -> Venta:
    """Crea una venta cobrada o una cotización pendiente.

    Una VENTA descuenta stock y entra a la caja en el acto. Una COTIZACION no
    toca ni el almacén ni el dinero: es una promesa de precio.
    """
    _validar_relaciones(db, data.cliente_id, data.ficha_id)
    validar_productos(db, data.items)

    venta = Venta(
        numero=siguiente_numero(db, data.tipo),
        tipo=data.tipo,
        estado=(
            EstadoVenta.PENDIENTE
            if data.tipo is TipoVenta.COTIZACION
            else EstadoVenta.CONFIRMADA
        ),
        cliente_id=data.cliente_id,
        ficha_id=data.ficha_id,
        descuento=data.descuento,
        notas=data.notas,
        valido_hasta=data.valido_hasta,
        usuario_id=actor.id,
    )
    db.add(venta)
    db.flush()

    reemplazar_items(db, venta, data.items)

    if data.tipo is TipoVenta.VENTA:
        confirmar_venta(db, venta, data.pagos, actor.id)
    elif data.pagos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Una cotización no lleva pagos; conviértela en venta para cobrarla",
        )

    db.commit()
    db.refresh(venta)
    return venta


@router.patch("/{venta_id}", response_model=VentaDetail)
def update_venta(
    venta_id: uuid.UUID,
    data: VentaUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ventas.editar")),
) -> Venta:
    venta = _get_venta(db, venta_id)

    # Una venta confirmada ya movió stock y dinero: editarla desharía el
    # cuadre. Para corregirla se anula y se emite otra.
    if venta.tipo is not TipoVenta.COTIZACION or venta.estado is not EstadoVenta.PENDIENTE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sólo se editan cotizaciones pendientes; anula la venta y emite una nueva",
        )

    cambios = data.model_dump(exclude_unset=True)
    items = cambios.pop("items", None)

    if "cliente_id" in cambios:
        _validar_relaciones(db, cambios["cliente_id"], None)

    for campo, valor in cambios.items():
        setattr(venta, campo, valor)

    if items is not None:
        from app.schemas.venta import ItemIn

        reemplazar_items(db, venta, [ItemIn(**i) for i in items])

    db.commit()
    db.refresh(venta)
    return venta


@router.post("/{venta_id}/convertir", response_model=VentaDetail)
def convertir(
    venta_id: uuid.UUID,
    data: ConvertirIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("ventas.crear")),
) -> Venta:
    """Convierte una cotización aceptada en venta: cobra y descuenta stock.

    Conserva el número de cotización para no perder el rastro de lo que el
    cliente aceptó.
    """
    venta = _get_venta(db, venta_id)

    if venta.tipo is not TipoVenta.COTIZACION:
        raise HTTPException(status_code=409, detail="Este documento ya es una venta")
    if venta.estado is not EstadoVenta.PENDIENTE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La cotización está {venta.estado.value.lower()} y no se puede convertir",
        )

    # El stock se comprueba recién ahora: entre la cotización y la aceptación
    # pudo venderse la última unidad a otro cliente.
    validar_productos(db, venta.items)

    venta.tipo = TipoVenta.VENTA
    confirmar_venta(db, venta, data.pagos, actor.id)

    db.commit()
    db.refresh(venta)
    return venta


@router.post("/{venta_id}/rechazar", response_model=VentaDetail)
def rechazar(
    venta_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ventas.editar")),
) -> Venta:
    """Cierra una cotización que el cliente no aceptó."""
    venta = _get_venta(db, venta_id)

    if venta.tipo is not TipoVenta.COTIZACION:
        raise HTTPException(status_code=409, detail="Sólo se rechazan cotizaciones")
    if venta.estado is not EstadoVenta.PENDIENTE:
        raise HTTPException(status_code=409, detail="La cotización ya no está pendiente")

    venta.estado = EstadoVenta.RECHAZADA
    db.commit()
    db.refresh(venta)
    return venta


@router.post("/{venta_id}/anular", response_model=VentaDetail)
def anular(
    venta_id: uuid.UUID,
    data: AnularIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("ventas.anular")),
) -> Venta:
    """Anula una venta: devuelve la mercadería y el dinero cobrado."""
    venta = _get_venta(db, venta_id)
    anular_venta(db, venta, data.motivo, actor.id)
    db.commit()
    db.refresh(venta)
    return venta


@router.get("/{venta_id}/pdf")
def descargar_pdf(
    venta_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ventas.ver")),
    descargar: bool = Query(default=False, description="fuerza la descarga en vez de abrirlo"),
) -> Response:
    """Hoja A4 del documento: la que se entrega o se manda por correo."""
    venta = _get_venta(db, venta_id)
    pdf = render_venta_pdf(venta)

    nombre = "cotizacion" if venta.tipo is TipoVenta.COTIZACION else "venta"
    disposition = "attachment" if descargar else "inline"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{nombre}-{venta.numero}.pdf"',
        },
    )


@router.get("/{venta_id}/ticket")
def descargar_ticket(
    venta_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ventas.ver")),
) -> Response:
    """Mismo documento en 80 mm, para la térmica del mostrador."""
    venta = _get_venta(db, venta_id)
    pdf = render_venta_ticket(venta)

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="ticket-{venta.numero}.pdf"',
        },
    )


#: Una cotización viva sigue en juego; el resto ya no se toca y puede salir
#: del listado del día a día.
ESTADOS_ARCHIVABLES = {EstadoVenta.CONFIRMADA, EstadoVenta.ANULADA, EstadoVenta.RECHAZADA}


@router.post("/{venta_id}/archivar", response_model=VentaDetail)
def archivar(
    venta_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ventas.editar")),
) -> Venta:
    """Saca el documento del listado. No lo borra ni lo anula.

    La venta sigue contando en caja, kardex, reportes y ante SUNAT: archivar es
    sólo dejar de verla entre las del día.
    """
    venta = _get_venta(db, venta_id)

    if venta.estado not in ESTADOS_ARCHIVABLES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{venta.numero} está pendiente; conviértela, recházala o anúlala "
                "antes de archivarla"
            ),
        )

    venta.archivada_at = datetime.now(UTC)
    db.commit()
    db.refresh(venta)
    return venta


@router.post("/{venta_id}/restaurar", response_model=VentaDetail)
def restaurar(
    venta_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ventas.editar")),
) -> Venta:
    venta = _get_venta(db, venta_id)
    venta.archivada_at = None
    db.commit()
    db.refresh(venta)
    return venta


@router.get("/resumen/dia", response_model=dict)
def resumen_dia(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("ventas.ver")),
) -> dict:
    """Totales de hoy para el dashboard.

    «Hoy» empieza a medianoche en Lima, no en UTC: si no, todo lo cobrado
    después de las 7 p. m. aparecería como venta del día siguiente.
    """
    inicio = inicio_del_dia(hoy_local())

    ventas = (
        db.scalars(
            select(Venta).where(
                Venta.tipo == TipoVenta.VENTA,
                Venta.estado == EstadoVenta.CONFIRMADA,
                Venta.created_at >= inicio,
            )
        )
        .unique()
        .all()
    )

    return {
        "cantidad": len(ventas),
        "total": sum((v.total for v in ventas), Decimal("0.00")),
        "ticket_promedio": (
            (sum((v.total for v in ventas), Decimal("0.00")) / len(ventas)).quantize(
                Decimal("0.01")
            )
            if ventas
            else Decimal("0.00")
        ),
    }
