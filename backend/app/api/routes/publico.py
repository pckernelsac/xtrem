"""Acceso público a una ficha mediante su código corto.

Es la ruta a la que apunta el QR impreso en el ticket térmico. Cuelga de la
raíz (no de /api/v1) para que la URL quepa en un QR de baja densidad, legible
por una impresora de 203 dpi.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.ficha import Ficha
from app.services.consulta_publica import datos_consulta
from app.services.ficha_pdf import EMPRESA, _asset_data_url, _env, render_ficha_pdf, render_ficha_ticket

router = APIRouter(prefix="/f", tags=["público"], include_in_schema=False)

#: Color de la píldora de estado en la página pública.
TONO_ESTADO = {
    "RECIBIDA": "gris",
    "EN_REVISION": "azul",
    "ESPERANDO_REPUESTOS": "ambar",
    "EN_REPARACION": "azul",
    "LISTA_PARA_ENTREGAR": "verde",
    "ENTREGADA": "verde",
    "CANCELADA": "rojo",
}


def _buscar_ficha(db: Session, codigo: str) -> Ficha:
    ficha = db.scalar(select(Ficha).where(Ficha.codigo_publico == codigo.strip().upper()))
    if ficha is None:
        raise HTTPException(status_code=404, detail="Ficha no encontrada o código inválido")
    return ficha


@router.get("/{codigo}", response_class=HTMLResponse)
def consulta_publica(
    codigo: str,
    db: Session = Depends(get_db),
    formato: str = Query(default="web", pattern="^(web|pdf|ticket)$"),
) -> Response:
    """Vista pública de la ficha del cliente.

    Por defecto muestra una página HTML pensada para el celular (lo que abre el
    QR); `?formato=pdf` o `?formato=ticket` devuelven los documentos. El código
    es la única credencial: equivale a la copia impresa que el cliente ya tiene.
    """
    ficha = _buscar_ficha(db, codigo)

    if formato == "pdf":
        url_qr = f"{settings.PUBLIC_BASE_URL}/f/{ficha.codigo_publico}"
        return Response(
            content=render_ficha_pdf(ficha, url_publica=url_qr),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="ficha-{ficha.numero}.pdf"'},
        )
    if formato == "ticket":
        return Response(
            content=render_ficha_ticket(ficha),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="ticket-{ficha.numero}.pdf"'},
        )

    datos = datos_consulta(db, ficha)
    html = _env().get_template("consulta_publica.html").render(
        d=datos,
        comprobante=datos["comprobante"],
        tono=TONO_ESTADO.get(ficha.estado.value, "gris"),
        logo=_asset_data_url("logo_zonaxtrema.png"),
        empresa=EMPRESA,
    )
    return HTMLResponse(content=html)
