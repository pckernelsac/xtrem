"""Acceso público al PDF de una nota de venta o cotización por su código corto.

Cuelga de la raíz (no de /api/v1) para que el enlace enviado por WhatsApp sea
corto, igual que el de la ficha (/f) y el del comprobante electrónico (/c). El
código es la única credencial: equivale al papel que el cliente ya tiene.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.venta import TipoVenta, Venta
from app.services.venta_pdf import render_venta_pdf, render_venta_ticket

router = APIRouter(prefix="/v", tags=["público"], include_in_schema=False)


@router.get("/{codigo}")
def venta_publica(
    codigo: str,
    db: Session = Depends(get_db),
    formato: str = Query(default="pdf", pattern="^(pdf|ticket)$"),
) -> Response:
    venta = db.scalar(select(Venta).where(Venta.codigo_publico == codigo.strip().upper()))
    if venta is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado o código inválido")

    nombre_base = "cotizacion" if venta.tipo is TipoVenta.COTIZACION else "nota-de-venta"

    if formato == "ticket":
        contenido = render_venta_ticket(venta)
        nombre = f"ticket-{venta.numero}.pdf"
    else:
        contenido = render_venta_pdf(venta)
        nombre = f"{nombre_base}-{venta.numero}.pdf"

    return Response(
        content=contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )
