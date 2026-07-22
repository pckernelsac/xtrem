"""Acceso público al PDF de un comprobante por su código corto.

Cuelga de la raíz (no de /api/v1) para que el enlace enviado por WhatsApp sea
corto. El backend proxea el archivo que aloja FactPro, así el cliente nunca ve
la URL de FactPro ni el RUC del emisor.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.comprobante import ComprobanteElectronico
from app.services import factpro_client

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
