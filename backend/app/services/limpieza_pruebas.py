"""Retirar los documentos emitidos contra el ambiente de pruebas.

Existe porque probar deja rastro: los comprobantes de prueba se quedan en la
tabla y el registro de ventas que se exporta para el contador filtra por fecha,
no por ambiente. Sin limpiarlos, acabarían declarados ante SUNAT como si fueran
válidos.

**Nunca toca lo emitido en producción.** No es una opción ni un parámetro: el
filtro `emitido_en_produccion = False` está en todas las consultas de este
módulo, y no hay forma de pedirle otra cosa. Un botón que puede borrar
documentos tributarios válidos no debería existir.
"""

import uuid
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.comprobante import ComprobanteElectronico, LoteSunat


def _solo_pruebas(consulta):
    """El filtro que hace segura toda esta funcionalidad."""
    return consulta.where(ComprobanteElectronico.emitido_en_produccion.is_(False))


def resumen(db: Session) -> dict:
    """Qué se borraría, sin borrar nada.

    Se enseña antes de actuar: un recuento y las series afectadas permiten
    reconocer al vuelo si hay algo que no debería estar ahí.
    """
    filas = db.execute(
        _solo_pruebas(
            select(
                ComprobanteElectronico.serie,
                ComprobanteElectronico.tipo,
                func.count(ComprobanteElectronico.id),
                func.sum(ComprobanteElectronico.total),
            )
        )
        .group_by(ComprobanteElectronico.serie, ComprobanteElectronico.tipo)
        .order_by(ComprobanteElectronico.serie)
    ).all()

    documentos = [
        {
            "serie": serie,
            "tipo": tipo.value,
            "cantidad": cantidad,
            "total": total or Decimal("0.00"),
        }
        for serie, tipo, cantidad, total in filas
    ]

    lotes = (
        db.scalar(
            select(func.count(LoteSunat.id)).where(
                LoteSunat.emitido_en_produccion.is_(False)
            )
        )
        or 0
    )

    # Lo que hay en producción se informa para tranquilidad de quien mira: deja
    # claro, antes de pulsar, que esos documentos no entran en el borrado.
    en_produccion = (
        db.scalar(
            select(func.count(ComprobanteElectronico.id)).where(
                ComprobanteElectronico.emitido_en_produccion.is_(True)
            )
        )
        or 0
    )

    ventas = (
        db.scalar(
            _solo_pruebas(
                select(func.count(func.distinct(ComprobanteElectronico.venta_id))).where(
                    ComprobanteElectronico.venta_id.is_not(None)
                )
            )
        )
        or 0
    )

    return {
        "documentos": documentos,
        "total_documentos": sum(d["cantidad"] for d in documentos),
        "lotes": lotes,
        "ventas_afectadas": ventas,
        "comprobantes_en_produccion": en_produccion,
    }


def borrar(db: Session, actor_id: uuid.UUID | None) -> dict:
    """Retira los documentos de prueba y devuelve lo que se llevó.

    Las **ventas no se tocan**: vuelven a quedar pendientes de facturar, que es
    justo lo que se quiere si eran ventas reales que se facturaron probando.
    """
    previo = resumen(db)

    ids = list(
        db.scalars(_solo_pruebas(select(ComprobanteElectronico.id))).all()
    )
    if not ids:
        return {**previo, "borrados": 0, "lotes_borrados": 0, "secuencias": []}

    # La autorreferencia de las notas de crédito impediría el DELETE.
    db.execute(
        text(
            "UPDATE comprobantes SET documento_afectado_id = NULL "
            "WHERE documento_afectado_id = ANY(:ids)"
        ),
        {"ids": ids},
    )
    db.execute(
        text("UPDATE comprobantes SET lote_id = NULL WHERE id = ANY(:ids)"),
        {"ids": ids},
    )
    borrados = db.execute(
        text("DELETE FROM comprobantes WHERE id = ANY(:ids)"), {"ids": ids}
    ).rowcount

    # Los lotes de prueba se van con ellos; sin esto quedarían apuntando a
    # documentos que ya no existen.
    lotes_borrados = db.execute(
        text("DELETE FROM lotes_sunat WHERE emitido_en_produccion = false")
    ).rowcount

    # Las secuencias de las series que se quedan sin comprobantes se reinician,
    # para que la primera emisión real salga con el número 1. Las de una serie
    # que ya emitió en producción se conservan: reiniciarlas repetiría números.
    reiniciadas = []
    secuencias = db.execute(
        text(
            "SELECT sequencename FROM pg_sequences "
            "WHERE sequencename LIKE 'comprobante\\_%'"
        )
    ).scalars().all()

    for nombre in secuencias:
        serie = nombre.removeprefix("comprobante_").removesuffix("_seq").upper()
        quedan = (
            db.scalar(
                select(func.count(ComprobanteElectronico.id)).where(
                    func.upper(ComprobanteElectronico.serie) == serie
                )
            )
            or 0
        )
        if quedan == 0:
            db.execute(text(f"ALTER SEQUENCE {nombre} RESTART WITH 1"))
            reiniciadas.append(serie)

    db.commit()
    return {
        **previo,
        "borrados": borrados,
        "lotes_borrados": lotes_borrados,
        "secuencias": reiniciadas,
    }
