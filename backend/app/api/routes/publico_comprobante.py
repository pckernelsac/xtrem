"""Acceso público al PDF de un comprobante por su código corto.

Cuelga de la raíz (no de /api/v1) para que el enlace enviado por WhatsApp sea
corto. El PDF **se genera aquí**, con los datos que guarda la base: no se pide a
nadie ni se proxea ningún archivo ajeno. Es la diferencia que hace que estos
enlaces no puedan volver a romperse porque un proveedor deje de responder.
"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.comprobante import ComprobanteElectronico
from app.services.comprobante_pdf import render_comprobante_pdf

router = APIRouter(prefix="/c", tags=["público"], include_in_schema=False)


@router.get("/{codigo}")
def comprobante_publico(codigo: str, db: Session = Depends(get_db)) -> Response:
    """Sirve el PDF del comprobante. El código es la única credencial: equivale
    a la copia que el cliente ya tiene."""
    comprobante = db.scalar(
        select(ComprobanteElectronico).where(
            ComprobanteElectronico.codigo_publico == codigo.strip().upper()
        )
    )
    if comprobante is None:
        raise HTTPException(
            status_code=404, detail="Comprobante no encontrado o código inválido"
        )

    pdf = render_comprobante_pdf(comprobante)
    nombre = f"{comprobante.tipo.value.lower()}-{comprobante.numero_completo}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre}"'},
    )
