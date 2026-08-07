import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.api.deps import bearer_scheme, get_current_user, require_permission
from app.core.config import settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models.bicicleta import Bicicleta
from app.models.caja import ETIQUETAS_METODO, MetodoPago, TipoMovimientoCaja
from app.models.cliente import Cliente
from app.models.comprobante import ComprobanteElectronico
from app.models.ficha import (
    ESTADOS_FINALES,
    ETIQUETAS_ESTADO,
    EstadoFicha,
    Ficha,
    FichaBicicleta,
    FichaEstadoLog,
    FichaRepuesto,
)
from app.models.user import User
from app.models.venta import Venta
from app.schemas.comprobante import ComprobanteDetail
from app.schemas.ficha import (
    AjusteAdelantoIn,
    CambioEstadoIn,
    CompartirOut,
    ConteoEstados,
    FacturacionFichaOut,
    FacturarFichaIn,
    FichaCreate,
    FichaDetail,
    FichaOut,
    FichaPage,
    FichaUpdate,
    RepuestoIn,
)
from app.schemas.venta import VentaDetail
from app.services.caja import (
    exigir_sesion_abierta,
    registrar_movimiento_caja,
    sesion_abierta,
)
from app.services.comprobante_pdf import url_publica as url_pdf_comprobante
from app.services.facturacion import comprobante_vigente_de, emitir_desde_venta
from app.services.ficha_facturacion import crear_venta_desde_ficha
from app.services.ficha_inventario import devolver_todo, sincronizar_consumo, validar_productos
from app.services.ficha_pdf import render_ficha_pdf, render_ficha_ticket
from app.services.whatsapp import enlace_whatsapp, mensaje_ficha, normalizar_telefono

router = APIRouter(prefix="/fichas", tags=["fichas"])

CERO = Decimal("0.00")


def _siguiente_numero(db: Session) -> str:
    """Correlativo de 6 dígitos desde la secuencia de Postgres."""
    valor = db.scalar(text("SELECT nextval('ficha_numero_seq')"))
    return f"{valor:06d}"


def _url_qr(ficha: Ficha) -> str:
    """URL corta para el QR del ticket y el enlace de WhatsApp.

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


def _venta_de_ficha(db: Session, ficha_id: uuid.UUID) -> Venta | None:
    """La venta que respalda el comprobante del servicio, si ya se convirtió."""
    return db.scalar(select(Venta).where(Venta.ficha_id == ficha_id))


def _resumen_facturacion(db: Session, ficha: Ficha) -> FacturacionFichaOut | None:
    """Resumen del documento al que derivó el servicio, si ya se cobró.

    La nota de venta se reporta en cuanto existe la venta, con o sin comprobante
    electrónico encima: si sólo se informara del comprobante, un servicio ya
    cobrado con nota de venta seguiría apareciendo como pendiente de cobro y se
    volvería a cobrar el saldo.
    """
    venta = _venta_de_ficha(db, ficha.id)
    if venta is None:
        return None

    resumen = FacturacionFichaOut(venta_id=venta.id, venta_numero=venta.numero)

    comp = comprobante_vigente_de(db, venta.id)
    if comp is not None:
        resumen.comprobante_id = comp.id
        resumen.tipo = comp.tipo
        resumen.numero = comp.numero_completo
        resumen.estado = comp.estado
        resumen.es_simulado = comp.es_simulado
        resumen.pdf_url = url_pdf_comprobante(comp)

    return resumen


def _exigir_cobrable(ficha: Ficha) -> None:
    """Condiciones comunes a la nota de venta y al comprobante electrónico."""
    if ficha.estado is not EstadoFicha.ENTREGADA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sólo se cobra un servicio ya entregado",
        )
    if ficha.total <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El servicio no tiene importe que cobrar",
        )


def _aplicar_ajuste_adelanto(
    db: Session,
    ficha: Ficha,
    nuevo: Decimal,
    metodo_pedido: MetodoPago | None,
    motivo: str | None,
    actor_id: uuid.UUID | None,
) -> bool:
    """Deja el adelanto en `nuevo` y compensa la diferencia en caja.

    El adelanto se cobró al recibir, así que corregirlo mueve dinero: la
    diferencia se registra en la sesión de caja abierta —ingreso si sube,
    egreso si baja o se devuelve—, que es donde debe verse el efectivo que
    entra o sale hoy. Si además cambia el método, se revierte el cobro
    anterior entero y se registra el nuevo, porque el arqueo cuenta cada medio
    de pago por separado.

    Devuelve False si no había nada que cambiar. No hace commit: el llamador
    cierra la transacción, y así el ajuste viaja junto al resto de la edición.
    """
    # Con la venta creada el adelanto ya es un pago de esa venta —y del
    # comprobante emitido encima—: cambiarlo dejaría el documento diciendo un
    # importe y la venta pagada con otro.
    if _venta_de_ficha(db, ficha.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "El servicio ya fue cobrado y el adelanto forma parte de esa venta. "
                "Anula el comprobante o emite una nota de crédito para corregirlo."
            ),
        )
    if ficha.estado is EstadoFicha.CANCELADA:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La ficha está cancelada y ya no admite cambios",
        )

    anterior = ficha.adelanto or CERO
    metodo_anterior = ficha.adelanto_metodo or MetodoPago.EFECTIVO
    metodo_nuevo = metodo_pedido or metodo_anterior

    if nuevo > ficha.total:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"El adelanto (S/ {nuevo:.2f}) supera el total del servicio "
                f"(S/ {ficha.total:.2f})"
            ),
        )

    cambia_metodo = anterior > CERO and nuevo > CERO and metodo_nuevo is not metodo_anterior
    if nuevo == anterior and not cambia_metodo:
        return False

    concepto = f"Ajuste de adelanto servicio N° {ficha.numero}"
    movimientos: list[tuple[TipoMovimientoCaja, MetodoPago, Decimal]] = []
    if cambia_metodo:
        movimientos.append((TipoMovimientoCaja.EGRESO, metodo_anterior, anterior))
        movimientos.append((TipoMovimientoCaja.INGRESO, metodo_nuevo, nuevo))
    elif nuevo > anterior:
        movimientos.append((TipoMovimientoCaja.INGRESO, metodo_nuevo, nuevo - anterior))
    else:
        movimientos.append((TipoMovimientoCaja.EGRESO, metodo_anterior, anterior - nuevo))

    # El efectivo sale o entra del cajón y exige caja abierta; los métodos
    # digitales sólo se anotan si hay sesión, igual que al crear la ficha.
    hay_efectivo = any(metodo is MetodoPago.EFECTIVO for _, metodo, _ in movimientos)
    sesion = exigir_sesion_abierta(db) if hay_efectivo else sesion_abierta(db)
    if sesion is not None:
        for tipo, metodo, monto in movimientos:
            registrar_movimiento_caja(
                db,
                sesion,
                tipo,
                metodo,
                monto,
                concepto=concepto,
                usuario_id=actor_id,
                referencia=ficha.numero,
            )

    ficha.adelanto = nuevo
    ficha.adelanto_metodo = metodo_nuevo if nuevo > CERO else None

    detalle = f"Adelanto corregido de S/ {anterior:.2f} a S/ {nuevo:.2f}"
    if cambia_metodo:
        detalle += (
            f" ({ETIQUETAS_METODO.get(metodo_anterior.value, metodo_anterior.value)}"
            f" → {ETIQUETAS_METODO.get(metodo_nuevo.value, metodo_nuevo.value)})"
        )
    if motivo:
        detalle += f" · {motivo}"

    # El historial es la única traza visible del cambio en el mostrador; el
    # estado no se mueve, sólo se anota el ajuste en la línea de tiempo.
    ficha.historial_estados.append(
        FichaEstadoLog(
            estado_anterior=None,
            estado_nuevo=ficha.estado,
            usuario_id=actor_id,
            comentario=detalle,
        )
    )
    return True


def _reemplazar_bicicletas(
    db: Session,
    ficha: Ficha,
    bicicleta_ids: list[uuid.UUID],
    cliente: Cliente,
) -> None:
    """Deja el servicio con exactamente esas bicicletas, en ese orden.

    Se valida una a una contra el dueño: la ficha impresa da por hecho que
    todas las máquinas son del cliente que las trajo, y una combinación
    cruzada saldría en papel con datos incoherentes.
    """
    # Repetir una bicicleta la contaría dos veces en la ficha impresa. Se
    # descarta el duplicado en lugar de fallar: para el mostrador es un
    # doble clic, no un error que merezca perder lo escrito.
    unicas: list[uuid.UUID] = []
    for bid in bicicleta_ids:
        if bid not in unicas:
            unicas.append(bid)

    ficha.bicicletas_asoc.clear()
    db.flush()

    for i, bid in enumerate(unicas):
        bici = db.get(Bicicleta, bid)
        if bici is None:
            raise HTTPException(status_code=422, detail="La bicicleta indicada no existe")
        if bici.cliente_id != cliente.id:
            raise HTTPException(
                status_code=422,
                detail=f"La bicicleta pertenece a {bici.cliente.nombre}, no a {cliente.nombre}",
            )
        ficha.bicicletas_asoc.append(FichaBicicleta(bicicleta_id=bici.id, orden=i))


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
        .outerjoin(Bicicleta)
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
    stmt = select(Ficha).join(Cliente)
    stmt = stmt.where(
        Ficha.archivada_at.is_not(None) if archivadas else Ficha.archivada_at.is_(None)
    )

    if search:
        like = f"%{search.strip().lower()}%"
        # Las bicicletas se filtran con EXISTS y no con un join: una ficha con
        # dos bicicletas se duplicaría en el resultado, inflando el total y
        # dejando páginas cortas.
        stmt = stmt.where(
            or_(
                Ficha.numero.like(f"%{search.strip()}%"),
                func.lower(Cliente.nombre).like(like),
                func.lower(Cliente.numero_documento).like(like),
                Ficha.bicicletas_asoc.any(
                    FichaBicicleta.bicicleta.has(
                        or_(
                            func.lower(Bicicleta.marca).like(like),
                            func.lower(func.coalesce(Bicicleta.numero_serie, "")).like(like),
                        )
                    )
                ),
            )
        )
    if estado:
        stmt = stmt.where(Ficha.estado == estado)
    if cliente_id:
        stmt = stmt.where(Ficha.cliente_id == cliente_id)
    if bicicleta_id:
        stmt = stmt.where(
            Ficha.bicicletas_asoc.any(FichaBicicleta.bicicleta_id == bicicleta_id)
        )

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
    ficha = _get_ficha(db, ficha_id)
    # Atributo transitorio que lee FichaDetail; no es una columna de la ficha.
    ficha.facturacion = _resumen_facturacion(db, ficha)  # type: ignore[attr-defined]
    return ficha


@router.post("", response_model=FichaDetail, status_code=status.HTTP_201_CREATED)
def create_ficha(
    data: FichaCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("fichas.crear")),
) -> Ficha:
    cliente = db.get(Cliente, data.cliente_id)
    if cliente is None:
        raise HTTPException(status_code=422, detail="El cliente indicado no existe")

    ficha = Ficha(
        numero=_siguiente_numero(db),
        cliente_id=cliente.id,
        estado=EstadoFicha.RECIBIDA,
        fecha_recepcion=data.fecha_recepcion or datetime.now(UTC),
        tecnico_recepcion_id=data.tecnico_recepcion_id or actor.id,
        tecnico_responsable_id=data.tecnico_responsable_id,
        canal_referencia=data.canal_referencia,
        servicios=[s.value for s in data.servicios],
        servicio_otro=data.servicio_otro,
        costo_servicio=data.costo_servicio,
        adelanto=data.adelanto,
        adelanto_metodo=data.adelanto_metodo if data.adelanto > 0 else None,
        diagnostico_inicial=data.diagnostico_inicial,
        trabajo_realizado=data.trabajo_realizado,
        tiempo_invertido_min=data.tiempo_invertido_min,
        observaciones=data.observaciones,
        garantia_dias=data.garantia_dias,
    )
    db.add(ficha)
    db.flush()

    _reemplazar_bicicletas(db, ficha, data.bicicleta_ids, cliente)
    _reemplazar_repuestos(db, ficha, data.repuestos, actor.id)

    # El adelanto entra a caja aquí, al recibir: es dinero que ya se cobró. El
    # saldo se cobrará al convertir el servicio en comprobante.
    if data.adelanto and data.adelanto > 0:
        if data.adelanto > ficha.total:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"El adelanto (S/ {data.adelanto:.2f}) supera el total del servicio "
                f"(S/ {ficha.total:.2f})",
            )
        metodo = data.adelanto_metodo or MetodoPago.EFECTIVO
        sesion = (
            exigir_sesion_abierta(db) if metodo is MetodoPago.EFECTIVO else sesion_abierta(db)
        )
        if sesion is not None:
            registrar_movimiento_caja(
                db,
                sesion,
                TipoMovimientoCaja.INGRESO,
                metodo,
                data.adelanto,
                concepto=f"Adelanto servicio N° {ficha.numero}",
                usuario_id=actor.id,
                referencia=ficha.numero,
            )

    ficha.historial_estados.append(
        FichaEstadoLog(
            estado_anterior=None,
            estado_nuevo=EstadoFicha.RECIBIDA,
            usuario_id=actor.id,
            comentario="Servicio creado",
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
    bicicleta_ids = changes.pop("bicicleta_ids", None)
    # El adelanto no se asigna a pelo como los demás campos: mueve caja y lo
    # aplica su propio ajuste, más abajo, cuando el total ya es el definitivo.
    metodo_enviado = "adelanto_metodo" in changes
    adelanto_nuevo = changes.pop("adelanto", None)
    adelanto_metodo = changes.pop("adelanto_metodo", None)
    if adelanto_nuevo is None and metodo_enviado:
        adelanto_nuevo = ficha.adelanto or CERO

    if "servicios" in changes and changes["servicios"] is not None:
        changes["servicios"] = [
            s.value if hasattr(s, "value") else s for s in changes["servicios"]
        ]

    for field, value in changes.items():
        setattr(ficha, field, value)

    if bicicleta_ids is not None:
        _reemplazar_bicicletas(db, ficha, bicicleta_ids, ficha.cliente)

    if repuestos is not None:
        _reemplazar_repuestos(db, ficha, [RepuestoIn(**r) for r in repuestos], actor.id)

    # Va después de los repuestos porque el ajuste se valida contra el total, y
    # la misma edición puede haberlo cambiado. Si el importe no varió no hace
    # nada: el formulario manda el adelanto siempre, toque o no ese campo.
    if adelanto_nuevo is not None:
        _aplicar_ajuste_adelanto(db, ficha, adelanto_nuevo, adelanto_metodo, None, actor.id)

    # El adelanto ya se cobró en caja: dejar el total por debajo de él daría un
    # saldo negativo imposible de facturar y sin vía de devolución.
    if ficha.adelanto and ficha.adelanto > ficha.total:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"El total quedaría en S/ {ficha.total:.2f}, por debajo del adelanto ya "
                f"cobrado (S/ {ficha.adelanto:.2f}). Ajusta el adelanto o los importes."
            ),
        )

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


@router.patch("/{ficha_id}/adelanto", response_model=FichaDetail)
def ajustar_adelanto(
    ficha_id: uuid.UUID,
    data: AjusteAdelantoIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("fichas.editar")),
) -> Ficha:
    """Corrige el adelanto de un servicio que todavía no se cobró.

    El adelanto se cobra al recibir y por eso no se toca desde la edición
    normal de la ficha: mover ese importe mueve caja. Aquí sí se puede, porque
    la corrección se compensa con su propio movimiento —ingreso si sube,
    egreso si baja o se devuelve— en la sesión de caja abierta, que es donde
    debe reflejarse el dinero que entra o sale hoy.

    Se admite incluso con la ficha ENTREGADA, mientras no exista la venta: ese
    es justo el momento en que el error salta, al ir a cobrar el saldo, y para
    entonces la edición normal de la ficha ya está cerrada.
    """
    ficha = _get_ficha(db, ficha_id)

    cambiado = _aplicar_ajuste_adelanto(
        db, ficha, data.adelanto, data.adelanto_metodo, data.motivo, actor.id
    )
    if not cambiado:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El adelanto ya tiene ese importe",
        )

    db.commit()
    db.refresh(ficha)
    ficha.facturacion = None  # type: ignore[attr-defined]
    return ficha


@router.post("/{ficha_id}/cobrar", response_model=VentaDetail, status_code=status.HTTP_201_CREATED)
def cobrar_ficha(
    ficha_id: uuid.UUID,
    data: FacturarFichaIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("ventas.crear")),
) -> Venta:
    """Cobra el servicio con una nota de venta, sin emitir comprobante electrónico.

    Es el documento interno del mostrador: sirve cuando el cliente no pide
    boleta ni factura. Deja la misma venta que dejaría facturar, así que después
    se puede emitir el comprobante encima sin volver a cobrar.
    """
    ficha = _get_ficha(db, ficha_id)
    _exigir_cobrable(ficha)

    if _venta_de_ficha(db, ficha.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El servicio ya fue cobrado",
        )

    venta = crear_venta_desde_ficha(db, ficha, data.pagos, actor.id)
    db.commit()
    db.refresh(venta)
    return venta


@router.post("/{ficha_id}/facturar", response_model=ComprobanteDetail)
def facturar_ficha(
    ficha_id: uuid.UUID,
    data: FacturarFichaIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("facturacion.emitir")),
) -> ComprobanteElectronico:
    """Convierte un servicio entregado en boleta o factura electrónica.

    Genera (o reutiliza) la venta que respalda el comprobante, cobra el saldo en
    caja y emite el documento por FactPro. El tipo lo decide el documento del
    cliente: factura si tiene RUC, boleta en cualquier otro caso.
    """
    ficha = _get_ficha(db, ficha_id)
    _exigir_cobrable(ficha)

    # Reintento idempotente: si ya existe la venta —porque se cobró con nota de
    # venta o porque un intento anterior falló—, no se vuelve a cobrar ni a
    # crear otra; los pagos del cuerpo se ignoran. Con un comprobante vigente se
    # bloquea; si el intento anterior quedó en ERROR, se reintenta sobre la misma.
    venta = _venta_de_ficha(db, ficha.id)
    if venta is not None:
        if comprobante_vigente_de(db, venta.id) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El servicio ya fue facturado",
            )
        return emitir_desde_venta(db, venta, actor.id)

    venta = crear_venta_desde_ficha(db, ficha, data.pagos, actor.id)
    return emitir_desde_venta(db, venta, actor.id)


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
    pdf = render_ficha_pdf(ficha, url_publica=_url_qr(ficha))

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

    # Enlace corto por código público (/f/{codigo}), igual que el de las boletas
    # electrónicas: no vence y no expone un token largo en el chat del cliente.
    url = _url_qr(ficha)
    destino = telefono or ficha.cliente.telefono
    mensaje = mensaje_ficha(ficha, url)

    return CompartirOut(
        url_pdf=url,
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
            comentario="Servicio cancelado · repuestos devueltos al inventario",
        )
    )
    db.commit()
