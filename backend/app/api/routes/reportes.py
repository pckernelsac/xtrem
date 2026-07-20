from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.fechas import hoy_local
from app.db.session import get_db
from app.models.user import User
from app.services import reportes, reportes_export

router = APIRouter(prefix="/reportes", tags=["reportes"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Un rango abierto sobre años de datos vuelve lento el reporte y rara vez es
#: lo que se quiere; se acota a un año.
MAX_DIAS_RANGO = 366


def _validar_rango(desde: date, hasta: date) -> None:
    if hasta < desde:
        raise HTTPException(status_code=422, detail="La fecha final es anterior a la inicial")
    if (hasta - desde).days > MAX_DIAS_RANGO:
        raise HTTPException(
            status_code=422, detail="El rango no puede superar un año"
        )


def _hoy() -> date:
    # `date.today()` daría el día del servidor (UTC en el contenedor), que
    # después de las 7 p. m. ya es mañana para Lima.
    return hoy_local()


def _excel(contenido: bytes, nombre: str) -> Response:
    return Response(
        content=contenido,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nombre}.xlsx"'},
    )


# ------------------------------------------------------------------ Ventas
@router.get("/ventas")
def ventas(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("reportes.ver")),
    desde: date = Query(default_factory=lambda: _hoy() - timedelta(days=29)),
    hasta: date = Query(default_factory=_hoy),
) -> dict:
    _validar_rango(desde, hasta)
    return reportes.reporte_ventas(db, desde, hasta)


@router.get("/ventas/export")
def ventas_export(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("reportes.exportar")),
    desde: date = Query(default_factory=lambda: _hoy() - timedelta(days=29)),
    hasta: date = Query(default_factory=_hoy),
    formato: str = Query(default="excel", pattern="^(excel|pdf)$"),
) -> Response:
    _validar_rango(desde, hasta)
    data = reportes.reporte_ventas(db, desde, hasta)
    nombre = f"ventas-{desde}-{hasta}"

    if formato == "pdf":
        return Response(
            content=reportes_export.exportar_ventas_pdf(data),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{nombre}.pdf"'},
        )
    return _excel(reportes_export.exportar_ventas_excel(data), nombre)


# -------------------------------------------------------------- Productos
@router.get("/productos-vendidos")
def productos_vendidos(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("reportes.ver")),
    desde: date = Query(default_factory=lambda: _hoy() - timedelta(days=29)),
    hasta: date = Query(default_factory=_hoy),
    limite: int = Query(default=20, ge=1, le=100),
) -> dict:
    _validar_rango(desde, hasta)
    return reportes.reporte_productos_vendidos(db, desde, hasta, limite)


@router.get("/productos-vendidos/export")
def productos_export(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("reportes.exportar")),
    desde: date = Query(default_factory=lambda: _hoy() - timedelta(days=29)),
    hasta: date = Query(default_factory=_hoy),
) -> Response:
    _validar_rango(desde, hasta)
    data = reportes.reporte_productos_vendidos(db, desde, hasta, limite=100)
    return _excel(reportes_export.exportar_productos_excel(data), f"productos-{desde}-{hasta}")


# ------------------------------------------------------------ Inventario
@router.get("/inventario")
def inventario(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("reportes.ver")),
) -> dict:
    return reportes.reporte_inventario(db)


@router.get("/inventario/export")
def inventario_export(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("reportes.exportar")),
) -> Response:
    data = reportes.reporte_inventario(db)
    return _excel(reportes_export.exportar_inventario_excel(data), f"inventario-{_hoy()}")
