"""Tareas periódicas del backend.

Va con `asyncio` dentro del propio proceso, sin añadir un planificador ni un
contenedor aparte: son dos tareas y el sistema corre en una sola réplica. Si
algún día se escalara a varias, esto habría que sacarlo fuera o cada réplica
haría el trabajo por su cuenta.

Tres cosas, y sólo dos tocan a SUNAT por iniciativa propia:

1. **Recoger los CDR pendientes.** Es sólo consultar, no tiene efectos, y sin
   ella los resúmenes se quedarían en «en proceso» para siempre porque los
   tickets no se resuelven solos.
2. **Reenviar lo que SUNAT no recibió** mientras estuvo caído. Tampoco es
   iniciativa propia en realidad: son documentos que alguien ya mandó emitir y
   que se quedaron a medio camino. Cuanto antes lleguen, mejor: hay plazo.
3. **Declarar el día anterior**, si está activado. Va **apagado por defecto**:
   mandar documentos a SUNAT sin que nadie lo pida debe ser una decisión
   explícita de quien administra.
"""

import asyncio
import contextlib
import logging
from datetime import timedelta

from app.core.fechas import ahora_local, hoy_local
from app.db.session import SessionLocal
from app.services import configuracion_sunat, facturacion, lotes_sunat

log = logging.getLogger("programador")

#: Cada cuánto da una vuelta el ciclo. Marca el retraso máximo con el que se
#: entrega un comprobante que pilló a SUNAT caído, así que va corto: las caídas
#: duran minutos y no tiene sentido esperar a la hora siguiente.
INTERVALO = timedelta(minutes=5)

#: Hora local a partir de la cual se declara el día anterior. Se elige por la
#: mañana: la jornada ya cerró y queda margen de sobra dentro del plazo.
HORA_DECLARACION = 9


async def _recoger_cdr() -> None:
    """Cierra los lotes que esperan respuesta de SUNAT."""
    db = SessionLocal()
    try:
        lotes = lotes_sunat.recoger_pendientes(db)
        cerrados = [l for l in lotes if not l.pendiente_de_cdr]
        if cerrados:
            log.info("CDR recogidos: %s", ", ".join(l.identificador for l in cerrados))
    except Exception:  # noqa: BLE001 - una tarea de fondo nunca debe tumbar el proceso
        log.exception("Fallo al recoger los CDR pendientes")
    finally:
        db.close()


async def _reenviar_pendientes() -> None:
    """Entrega los comprobantes que se quedaron sin llegar a SUNAT.

    Cada uno va con su XML y su correlativo originales, así que esto no emite
    nada nuevo: termina de entregar lo que ya se emitió.
    """
    db = SessionLocal()
    try:
        procesados = facturacion.reenviar_pendientes(db)
        entregados = [c for c in procesados if not c.envio_pendiente]
        if entregados:
            log.info(
                "Reenviados a SUNAT: %s",
                ", ".join(f"{c.numero_completo} ({c.estado.value})" for c in entregados),
            )
        if len(procesados) > len(entregados):
            log.warning("SUNAT sigue sin responder; quedan comprobantes en cola")
    except Exception:  # noqa: BLE001
        log.exception("Fallo al reenviar los comprobantes pendientes")
    finally:
        db.close()


async def _declarar_dia_anterior() -> None:
    """Manda el resumen del día anterior, si la declaración automática está activa."""
    db = SessionLocal()
    try:
        if not configuracion_sunat.resolver(db).declaracion_automatica:
            return

        ayer = hoy_local() - timedelta(days=1)
        if not lotes_sunat.boletas_sin_informar(db, ayer):
            return

        # Sin actor: lo generó el sistema, no una persona.
        lote = lotes_sunat.generar_resumen(db, ayer, None)
        log.info("Resumen automático enviado: %s (%s)", lote.identificador, lote.estado.value)
    except Exception:  # noqa: BLE001
        log.exception("Fallo al declarar automáticamente el día anterior")
    finally:
        db.close()


async def _bucle() -> None:
    """Ciclo de fondo. Cada vuelta decide qué toca hacer."""
    ultimo_dia_declarado = None

    while True:
        try:
            # Primero la cola: un comprobante sin entregar corre contra un plazo
            # y además no puede entrar en ningún resumen hasta que SUNAT lo tenga.
            await _reenviar_pendientes()
            await _recoger_cdr()

            ahora = ahora_local()
            hoy = ahora.date()
            # Una vez al día, pasada la hora fijada. Se recuerda el día para no
            # reintentarlo en cada vuelta si no hubiera nada que declarar.
            if ahora.hour >= HORA_DECLARACION and ultimo_dia_declarado != hoy:
                await _declarar_dia_anterior()
                ultimo_dia_declarado = hoy
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Fallo en el ciclo del programador")

        await asyncio.sleep(INTERVALO.total_seconds())


def iniciar() -> asyncio.Task:
    """Arranca el ciclo y devuelve la tarea, para poder pararla al apagar."""
    log.info(
        "Programador activo: reenvíos y CDR cada %s min, declaración automática a las %s h",
        int(INTERVALO.total_seconds() // 60),
        HORA_DECLARACION,
    )
    return asyncio.create_task(_bucle())


async def detener(tarea: asyncio.Task) -> None:
    tarea.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await tarea
