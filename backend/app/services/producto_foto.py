"""Normalización de las fotos del catálogo.

Lo que llega del mostrador es lo que salió del celular: 4 MB, orientación en
EXIF y resolución de cámara. Guardar eso tal cual haría que la cuadrícula del
punto de venta descargue decenas de megas por pantalla, así que toda imagen se
reescala y se recodifica antes de tocar la base.
"""

import io

from fastapi import HTTPException, status
from PIL import Image, ImageOps, UnidentifiedImageError

#: Tope de subida. Un JPEG de celular ronda los 3-5 MB; más que esto es un
#: archivo que no debería estar en un catálogo de repuestos.
MAX_BYTES = 8 * 1024 * 1024

#: Lado mayor tras el reescalado. Alcanza para la ficha del producto y para una
#: pantalla retina de la cuadrícula, sin guardar píxeles que nadie va a ver.
LADO_MAX = 800

MIME_SALIDA = "image/webp"

FORMATOS_ACEPTADOS = {"JPEG", "PNG", "WEBP", "GIF", "BMP"}


def normalizar(datos: bytes) -> bytes:
    """Devuelve la imagen lista para guardar: WEBP, ≤800 px de lado, sin EXIF.

    WEBP y no JPEG porque conserva la transparencia de las fotos recortadas de
    catálogo del proveedor, que en JPEG saldrían con un fondo negro.
    """
    if not datos:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="El archivo está vacío"
        )
    if len(datos) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"La imagen supera los {MAX_BYTES // (1024 * 1024)} MB",
        )

    try:
        imagen = Image.open(io.BytesIO(datos))
        imagen.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El archivo no es una imagen que se pueda leer",
        ) from exc

    if imagen.format not in FORMATOS_ACEPTADOS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Formato de imagen no soportado ({imagen.format})",
        )

    # Las fotos de celular vienen apaisadas con la rotación sólo en el EXIF;
    # sin esto, la miniatura sale de costado.
    imagen = ImageOps.exif_transpose(imagen)

    if imagen.mode not in ("RGB", "RGBA"):
        imagen = imagen.convert("RGBA" if "A" in imagen.getbands() else "RGB")

    imagen.thumbnail((LADO_MAX, LADO_MAX), Image.LANCZOS)

    salida = io.BytesIO()
    imagen.save(salida, format="WEBP", quality=82, method=4)
    return salida.getvalue()
