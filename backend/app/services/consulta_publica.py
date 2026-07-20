"""Datos de la vista pública de una ficha (la que abre el QR del ticket).

Expone sólo lo que el cliente ya tiene derecho a ver de SU bicicleta: estado,
servicios, trabajo, repuestos, garantía y el comprobante si se emitió. Nada de
costos internos, notas privadas ni datos de otros clientes.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.fechas import dia_local, hoy_local
from app.models.comprobante import ComprobanteElectronico, EstadoComprobante
from app.models.ficha import ETIQUETAS_ESTADO, ETIQUETAS_SERVICIO, Ficha
from app.models.venta import Venta


def datos_consulta(db: Session, ficha: Ficha) -> dict:
    servicios = [ETIQUETAS_SERVICIO.get(s, s) for s in (ficha.servicios or [])]
    if ficha.servicio_otro:
        servicios.append(ficha.servicio_otro)

    # Garantía: sólo tiene sentido mostrar "vence el…" una vez entregada.
    garantia = None
    if ficha.garantia_dias and ficha.fecha_entrega:
        # Días de Lima en los dos extremos: con la fecha del servidor la
        # garantía figuraba vencida desde las 7 p. m. del último día válido.
        vence = dia_local(ficha.fecha_entrega) + timedelta(days=ficha.garantia_dias)
        garantia = {
            "dias": ficha.garantia_dias,
            "vence": vence.isoformat(),
            "vigente": vence >= hoy_local(),
        }
    elif ficha.garantia_dias:
        garantia = {"dias": ficha.garantia_dias, "vence": None, "vigente": None}

    # Comprobante electrónico, si la ficha derivó en una venta facturada.
    comprobante = None
    venta = db.scalar(select(Venta).where(Venta.ficha_id == ficha.id))
    if venta is not None:
        comp = db.scalar(
            select(ComprobanteElectronico).where(
                ComprobanteElectronico.venta_id == venta.id,
                ComprobanteElectronico.estado.in_(
                    [EstadoComprobante.ACEPTADO, EstadoComprobante.REGISTRADO]
                ),
            )
        )
        if comp is not None:
            comprobante = {
                "tipo": comp.tipo.value,
                "numero": comp.numero_completo,
                "pdf_url": comp.pdf_url,
                "es_simulado": comp.es_simulado,
            }

    repuestos = [
        {
            "cantidad": f"{r.cantidad:g}",
            "descripcion": r.descripcion,
            "marca": r.marca or "",
        }
        for r in ficha.repuestos
    ]

    historial = [
        {
            "estado": ETIQUETAS_ESTADO[log.estado_nuevo.value],
            "fecha": log.created_at.isoformat(),
            "comentario": log.comentario,
        }
        for log in ficha.historial_estados
    ]

    return {
        "numero": ficha.numero,
        "estado": ficha.estado.value,
        "estado_label": ETIQUETAS_ESTADO[ficha.estado.value],
        "fecha_recepcion": ficha.fecha_recepcion.isoformat(),
        "fecha_entrega": ficha.fecha_entrega.isoformat() if ficha.fecha_entrega else None,
        "bicicleta": {
            "marca": ficha.bicicleta.marca,
            "modelo": ficha.bicicleta.modelo,
            "color": ficha.bicicleta.color,
            "tipo": ficha.bicicleta.tipo.value,
        },
        "cliente_nombre": ficha.cliente.nombre,
        "servicios": servicios,
        "diagnostico": ficha.diagnostico_inicial,
        "trabajo_realizado": ficha.trabajo_realizado,
        "repuestos": repuestos,
        "garantia": garantia,
        "comprobante": comprobante,
        "historial": historial,
    }
