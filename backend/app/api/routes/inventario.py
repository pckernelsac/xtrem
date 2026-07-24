import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.inventario import (
    Categoria,
    MovimientoKardex,
    Producto,
    ProductoFoto,
    TipoItem,
    TipoMovimiento,
)
from app.models.ficha import FichaRepuesto
from app.models.user import User
from app.models.venta import VentaItem
from app.schemas.inventario import (
    CategoriaCreate,
    CategoriaOut,
    CategoriaUpdate,
    MovimientoCreate,
    MovimientoOut,
    MovimientoPage,
    ProductoCreate,
    ProductoOut,
    ProductoPage,
    ProductoUpdate,
    ResultadoImportacion,
    ResumenInventario,
)
from app.services.inventario import recalcular_stock, registrar_movimiento
from app.services.inventario_excel import importar_productos, plantilla_xlsx
from app.services.producto_foto import MAX_BYTES as MAX_FOTO_BYTES
from app.services.producto_foto import MIME_SALIDA, normalizar

router = APIRouter(prefix="/inventario", tags=["inventario"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_EXCEL_BYTES = 5 * 1024 * 1024


# =========================================================== Categorías
@router.get("/categorias", response_model=list[CategoriaOut])
def list_categorias(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventario.ver")),
) -> list[CategoriaOut]:
    filas = db.execute(
        select(Categoria, func.count(Producto.id))
        .outerjoin(Producto, Producto.categoria_id == Categoria.id)
        .group_by(Categoria.id)
        .order_by(Categoria.nombre)
    ).all()

    return [
        CategoriaOut.model_validate(c).model_copy(update={"productos_count": n})
        for c, n in filas
    ]


@router.post("/categorias", response_model=CategoriaOut, status_code=status.HTTP_201_CREATED)
def create_categoria(
    data: CategoriaCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventario.crear")),
) -> CategoriaOut:
    if db.scalar(select(Categoria).where(func.lower(Categoria.nombre) == data.nombre.lower())):
        raise HTTPException(status_code=409, detail="Ya existe una categoría con ese nombre")

    categoria = Categoria(**data.model_dump())
    db.add(categoria)
    db.commit()
    db.refresh(categoria)
    return CategoriaOut.model_validate(categoria)


@router.patch("/categorias/{categoria_id}", response_model=CategoriaOut)
def update_categoria(
    categoria_id: uuid.UUID,
    data: CategoriaUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventario.editar")),
) -> CategoriaOut:
    categoria = db.get(Categoria, categoria_id)
    if categoria is None:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    cambios = data.model_dump(exclude_unset=True)
    if "nombre" in cambios:
        choque = db.scalar(
            select(Categoria).where(
                func.lower(Categoria.nombre) == cambios["nombre"].lower(),
                Categoria.id != categoria.id,
            )
        )
        if choque:
            raise HTTPException(status_code=409, detail="Ya existe una categoría con ese nombre")

    for campo, valor in cambios.items():
        setattr(categoria, campo, valor)
    db.commit()
    db.refresh(categoria)

    n = db.scalar(select(func.count(Producto.id)).where(Producto.categoria_id == categoria.id)) or 0
    return CategoriaOut.model_validate(categoria).model_copy(update={"productos_count": n})


@router.delete("/categorias/{categoria_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_categoria(
    categoria_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventario.eliminar")),
) -> None:
    categoria = db.get(Categoria, categoria_id)
    if categoria is None:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    n = db.scalar(select(func.count(Producto.id)).where(Producto.categoria_id == categoria.id)) or 0
    if n:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La categoría tiene {n} producto(s); reasígnalos antes de eliminarla",
        )

    db.delete(categoria)
    db.commit()


# =========================================================== Resumen
@router.get("/resumen", response_model=ResumenInventario)
def resumen(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventario.ver")),
) -> ResumenInventario:
    # Las cifras de almacén sólo cuentan productos: un servicio no tiene stock
    # que reponer ni valor que inmovilizar, y contarlo distorsionaría el tablero.
    activos = select(Producto).where(
        Producto.is_active.is_(True), Producto.tipo == TipoItem.PRODUCTO
    )

    return ResumenInventario(
        productos_activos=db.scalar(select(func.count()).select_from(activos.subquery())) or 0,
        servicios_activos=db.scalar(
            select(func.count()).select_from(
                select(Producto)
                .where(Producto.is_active.is_(True), Producto.tipo == TipoItem.SERVICIO)
                .subquery()
            )
        )
        or 0,
        bajo_minimo=db.scalar(
            select(func.count()).select_from(
                activos.where(
                    Producto.stock_minimo > 0,
                    Producto.stock_actual <= Producto.stock_minimo,
                ).subquery()
            )
        )
        or 0,
        sin_stock=db.scalar(
            select(func.count()).select_from(
                activos.where(Producto.stock_actual <= 0).subquery()
            )
        )
        or 0,
        archivados=db.scalar(
            select(func.count())
            .select_from(Producto)
            .where(Producto.is_active.is_(False))
        )
        or 0,
        valor_total=db.scalar(
            select(func.coalesce(func.sum(Producto.stock_actual * Producto.precio_compra), 0))
            .where(Producto.is_active.is_(True), Producto.tipo == TipoItem.PRODUCTO)
        )
        or Decimal("0"),
    )


# =========================================================== Productos
@router.get("/productos", response_model=ProductoPage)
def list_productos(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventario.ver")),
    search: str | None = Query(default=None, description="SKU, nombre, marca o código de barras"),
    tipo: TipoItem | None = Query(default=None, description="Producto o servicio"),
    categoria_id: uuid.UUID | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    solo_alertas: bool = Query(default=False, description="Sólo bajo mínimo o sin stock"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> ProductoPage:
    stmt = select(Producto)

    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Producto.sku).like(like),
                func.lower(Producto.nombre).like(like),
                func.lower(func.coalesce(Producto.marca, "")).like(like),
                func.lower(func.coalesce(Producto.codigo_barras, "")).like(like),
            )
        )
    if tipo is not None:
        stmt = stmt.where(Producto.tipo == tipo)
    if categoria_id:
        stmt = stmt.where(Producto.categoria_id == categoria_id)
    if is_active is not None:
        stmt = stmt.where(Producto.is_active == is_active)
    if solo_alertas:
        # Los servicios quedan fuera aunque su stock sea 0: no hay nada que reponer.
        stmt = stmt.where(Producto.tipo == TipoItem.PRODUCTO).where(
            or_(
                Producto.stock_actual <= 0,
                (Producto.stock_minimo > 0) & (Producto.stock_actual <= Producto.stock_minimo),
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        db.scalars(stmt.order_by(Producto.nombre).offset((page - 1) * page_size).limit(page_size))
        .unique()
        .all()
    )

    return ProductoPage(
        items=[ProductoOut.model_validate(p) for p in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/productos/buscar", response_model=ProductoOut)
def buscar_por_codigo(
    codigo: str = Query(min_length=1, description="Código de barras o SKU"),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventario.ver")),
) -> Producto:
    """Resuelve un código escaneado a un producto.

    La pistola escribe el código y manda Enter, así que el mostrador necesita
    una única llamada que devuelva el producto exacto, no una lista.
    """
    limpio = codigo.strip()

    producto = db.scalar(
        select(Producto).where(
            Producto.codigo_barras == limpio, Producto.is_active.is_(True)
        )
    )
    # Muchos productos del taller no traen código impreso; el SKU sirve de
    # respaldo cuando se teclea a mano.
    if producto is None:
        producto = db.scalar(
            select(Producto).where(
                Producto.sku == limpio.upper().replace(" ", ""),
                Producto.is_active.is_(True),
            )
        )

    if producto is None:
        raise HTTPException(
            status_code=404, detail=f"Ningún producto activo con el código {limpio}"
        )
    return producto


@router.get("/productos/{producto_id}", response_model=ProductoOut)
def get_producto(
    producto_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventario.ver")),
) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return producto


@router.post("/productos", response_model=ProductoOut, status_code=status.HTTP_201_CREATED)
def create_producto(
    data: ProductoCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("inventario.crear")),
) -> Producto:
    if db.scalar(select(Producto).where(Producto.sku == data.sku)):
        raise HTTPException(status_code=409, detail=f"Ya existe un producto con el SKU {data.sku}")
    if data.categoria_id and db.get(Categoria, data.categoria_id) is None:
        raise HTTPException(status_code=422, detail="La categoría indicada no existe")

    campos = data.model_dump(exclude={"stock_inicial"})
    producto = Producto(**campos, stock_actual=Decimal("0"))
    db.add(producto)
    db.flush()

    # El stock inicial entra como movimiento, no como valor suelto: así el
    # kardex arranca cuadrado desde el primer día.
    if data.stock_inicial > 0:
        registrar_movimiento(
            db,
            producto.id,
            TipoMovimiento.ENTRADA,
            data.stock_inicial,
            usuario_id=actor.id,
            costo_unitario=data.precio_compra or None,
            motivo="Stock inicial",
        )

    db.commit()
    db.refresh(producto)
    return producto


@router.patch("/productos/{producto_id}", response_model=ProductoOut)
def update_producto(
    producto_id: uuid.UUID,
    data: ProductoUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventario.editar")),
) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    cambios = data.model_dump(exclude_unset=True)

    if "sku" in cambios and cambios["sku"] != producto.sku:
        if db.scalar(select(Producto).where(Producto.sku == cambios["sku"])):
            raise HTTPException(status_code=409, detail="Ya existe un producto con ese SKU")
    if cambios.get("categoria_id") and db.get(Categoria, cambios["categoria_id"]) is None:
        raise HTTPException(status_code=422, detail="La categoría indicada no existe")

    # Convertir a servicio un producto con existencias dejaría stock huérfano:
    # invisible en el almacén pero sumado en el kardex. Hay que vaciarlo antes.
    if cambios.get("tipo") == TipoItem.SERVICIO and producto.stock_actual > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{producto.sku} tiene {producto.stock_actual:g} en stock; "
                "déjalo en cero con un ajuste antes de convertirlo en servicio"
            ),
        )
    if cambios.get("tipo") == TipoItem.SERVICIO:
        cambios["stock_minimo"] = Decimal("0")

    for campo, valor in cambios.items():
        setattr(producto, campo, valor)

    db.commit()
    db.refresh(producto)
    return producto


# =========================================================== Foto
@router.put("/productos/{producto_id}/foto", response_model=ProductoOut)
async def subir_foto(
    producto_id: uuid.UUID,
    archivo: UploadFile = File(description="JPG, PNG o WEBP de hasta 8 MB"),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventario.editar")),
) -> Producto:
    """Reemplaza la foto del ítem. La imagen se reescala antes de guardarse."""
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    # Rechazar por tamaño ANTES de cargar el cuerpo en memoria: `archivo.size`
    # lo trae el parser sin leer los bytes.
    if archivo.size is not None and archivo.size > MAX_FOTO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"La imagen supera los {MAX_FOTO_BYTES // (1024 * 1024)} MB",
        )

    contenido = normalizar(await archivo.read())

    foto = db.scalar(select(ProductoFoto).where(ProductoFoto.producto_id == producto_id))
    if foto is None:
        foto = ProductoFoto(producto_id=producto_id)
        db.add(foto)

    foto.contenido = contenido
    foto.mime = MIME_SALIDA
    foto.actualizado_at = datetime.now(UTC)
    # El espejo en `productos` es lo que hace que el listado sepa que hay foto
    # sin leer los bytes; se mueve siempre junto con la imagen.
    producto.foto_actualizada_at = foto.actualizado_at

    db.commit()
    db.refresh(producto)
    return producto


@router.delete("/productos/{producto_id}/foto", response_model=ProductoOut)
def borrar_foto(
    producto_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventario.editar")),
) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    foto = db.scalar(select(ProductoFoto).where(ProductoFoto.producto_id == producto_id))
    if foto is not None:
        db.delete(foto)
    producto.foto_actualizada_at = None

    db.commit()
    db.refresh(producto)
    return producto


@router.get("/productos/{producto_id}/foto", include_in_schema=False)
def ver_foto(producto_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    """Sirve la imagen. Sin token, a propósito.

    Un `<img src>` no manda el header Authorization, y la alternativa sería
    descargar cada miniatura por AJAX para convertirla en blob. Son fotos de
    repuestos —no hay dato personal— y el id es un UUID que no se puede
    enumerar, así que el intercambio vale la pena.
    """
    foto = db.scalar(select(ProductoFoto).where(ProductoFoto.producto_id == producto_id))
    if foto is None:
        raise HTTPException(status_code=404, detail="Este ítem no tiene foto")

    return Response(
        content=foto.contenido,
        media_type=foto.mime,
        headers={
            # La URL lleva ?v=<timestamp>, así que este contenido es inmutable:
            # al cambiar la foto cambia la URL y el navegador vuelve a pedirla.
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Length": str(len(foto.contenido)),
        },
    )


@router.delete("/productos/{producto_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar_producto(
    producto_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventario.eliminar")),
) -> None:
    """Borrado definitivo, sólo para lo que nunca llegó a usarse.

    Archivar (`PATCH {is_active: false}`) es la vía normal de dar de baja: el
    ítem desaparece del mostrador pero sus ventas y fichas siguen citándolo. El
    borrado real existe para el error de captura —el SKU duplicado, la prueba—
    y por eso se niega en cuanto haya un documento que lo mencione.
    """
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    en_ventas = (
        db.scalar(select(func.count()).select_from(VentaItem).where(VentaItem.producto_id == producto_id))
        or 0
    )
    en_fichas = (
        db.scalar(
            select(func.count())
            .select_from(FichaRepuesto)
            .where(FichaRepuesto.producto_id == producto_id)
        )
        or 0
    )
    if en_ventas or en_fichas:
        usos = " y ".join(
            parte
            for parte in (
                f"{en_ventas} venta(s)" if en_ventas else "",
                f"{en_fichas} ficha(s)" if en_fichas else "",
            )
            if parte
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"{producto.sku} aparece en {usos}; archívalo en vez de eliminarlo "
                "para no romper esos documentos"
            ),
        )

    # Kardex y foto cuelgan del producto con ON DELETE CASCADE: se van con él.
    db.delete(producto)
    db.commit()


# =========================================================== Kardex
@router.post(
    "/productos/{producto_id}/movimientos",
    response_model=MovimientoOut,
    status_code=status.HTTP_201_CREATED,
)
def crear_movimiento(
    producto_id: uuid.UUID,
    data: MovimientoCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("inventario.ajustar_stock")),
) -> MovimientoKardex:
    """Entrada, salida o ajuste. En un AJUSTE, `cantidad` es el stock contado."""
    # `registrar_movimiento` ignora los servicios en silencio, que es lo correcto
    # cuando el movimiento viene de una venta. Pedido a mano sí es un error.
    item = db.get(Producto, producto_id)
    if item is not None and item.es_servicio:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{item.sku} es un servicio y no maneja stock ni kardex",
        )

    asiento = registrar_movimiento(
        db,
        producto_id,
        data.tipo,
        data.cantidad,
        usuario_id=actor.id,
        costo_unitario=data.costo_unitario,
        motivo=data.motivo,
        referencia=data.referencia,
    )
    db.commit()
    db.refresh(asiento)
    return asiento


@router.get("/kardex", response_model=MovimientoPage)
def kardex(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventario.ver")),
    producto_id: uuid.UUID | None = Query(default=None),
    tipo: TipoMovimiento | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> MovimientoPage:
    stmt = select(MovimientoKardex)
    if producto_id:
        stmt = stmt.where(MovimientoKardex.producto_id == producto_id)
    if tipo:
        stmt = stmt.where(MovimientoKardex.tipo == tipo)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        db.scalars(
            stmt.order_by(MovimientoKardex.created_at.desc(), MovimientoKardex.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .unique()
        .all()
    )

    return MovimientoPage(
        items=[MovimientoOut.model_validate(m) for m in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/productos/{producto_id}/auditoria")
def auditar_stock(
    producto_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("inventario.ver")),
) -> dict[str, object]:
    """Compara el saldo guardado contra la suma del kardex.

    `stock_actual` está denormalizado por velocidad; esto permite detectar si
    alguna vez se desincronizó del libro de movimientos.
    """
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    calculado = recalcular_stock(db, producto)
    return {
        "sku": producto.sku,
        "stock_registrado": producto.stock_actual,
        "stock_segun_kardex": calculado,
        "cuadra": producto.stock_actual == calculado,
        "diferencia": producto.stock_actual - calculado,
    }


# =========================================================== Excel
@router.get("/plantilla-excel")
def descargar_plantilla(
    _: User = Depends(require_permission("inventario.ver")),
) -> Response:
    return Response(
        content=plantilla_xlsx(),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": 'attachment; filename="plantilla-inventario.xlsx"'},
    )


@router.post("/importar", response_model=ResultadoImportacion)
async def importar_excel(
    archivo: UploadFile = File(...),
    modo_prueba: bool = Query(
        default=True,
        description="true (por defecto) valida y reporta sin escribir nada en la base",
    ),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("inventario.crear")),
) -> ResultadoImportacion:
    """Importa productos desde .xlsx.

    Arranca en modo prueba a propósito: primero se revisa el reporte fila por
    fila y recién después se confirma con `modo_prueba=false`.
    """
    if not (archivo.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El archivo debe ser .xlsx (Excel). Los .xls antiguos no son compatibles.",
        )

    # Rechazar por tamaño antes de leer el cuerpo entero en memoria.
    if archivo.size is not None and archivo.size > MAX_EXCEL_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El archivo supera los 5 MB",
        )

    contenido = await archivo.read()
    if len(contenido) > MAX_EXCEL_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="El archivo supera los 5 MB",
        )
    if not contenido:
        raise HTTPException(status_code=422, detail="El archivo está vacío")

    return importar_productos(db, contenido, usuario_id=actor.id, modo_prueba=modo_prueba)
