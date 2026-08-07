"""Descarta los intentos de emisión que SUNAT nunca llegó a aceptar.

Un comprobante en `ERROR` es un envío que se rechazó **antes** de existir para
SUNAT: no tiene CDR, no se declaró y su número no llegó a usarse. La tabla lo
conserva a propósito, porque el reintento reutiliza el correlativo reservado y
así la serie no queda con huecos (`facturacion._numero_reservado`).

Eso sirve cuando se reintenta enseguida. Cuando el rechazo se debió a algo ajeno
al documento —un alta de SUNAT que aún no había surtido efecto, por ejemplo— lo
que queda es un montón de filas fallidas que van a duplicar el número de las
buenas en cuanto se reemita. Este script las retira y **devuelve la secuencia
atrás**, que es la parte que no se puede hacer a mano sin dejar un hueco:
`nextval` no retrocede, así que borrar las filas sin tocar la secuencia haría que
la siguiente emisión saltara los números consumidos.

No toca nada que tenga CDR ni nada que no esté en `ERROR`. Ese filtro no es un
parámetro: un script capaz de borrar comprobantes válidos no debería existir.

Uso (dentro del contenedor del backend):

    python -m app.db.descartar_fallidos              # sólo informa, no toca nada
    python -m app.db.descartar_fallidos --aplicar    # descarta y ajusta las secuencias
    python -m app.db.descartar_fallidos --serie B001 # acota a una serie
"""

import argparse
import sys

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.comprobante import ComprobanteElectronico, EstadoComprobante


def _fallidos(serie: str | None):
    """Los que se pueden descartar sin perder nada.

    `cdr_xml IS NULL` es redundante con el estado, y va a propósito: si alguna
    vez un comprobante con CDR acabara marcado como ERROR, este script debe
    dejarlo en paz en vez de borrar la única copia del cargo de SUNAT.
    """
    consulta = select(ComprobanteElectronico).where(
        ComprobanteElectronico.estado == EstadoComprobante.ERROR,
        ComprobanteElectronico.cdr_xml.is_(None),
    )
    if serie:
        consulta = consulta.where(func.upper(ComprobanteElectronico.serie) == serie.upper())
    return consulta.order_by(ComprobanteElectronico.serie, ComprobanteElectronico.numero)


def _secuencia_de(serie: str) -> str:
    return f"comprobante_{serie.lower()}_seq"


def descartar(aplicar: bool, serie: str | None) -> None:
    db = SessionLocal()
    try:
        filas = list(db.scalars(_fallidos(serie)).all())
        if not filas:
            print("No hay intentos fallidos que descartar. Nada que hacer.")
            return

        series = sorted({f.serie for f in filas})
        print(f"Intentos fallidos encontrados: {len(filas)}\n")
        for f in filas:
            codigo = f.tipo_estado_sunat or "—"
            motivo = (f.mensaje_error or "").splitlines()[0][:70] if f.mensaje_error else ""
            ambiente = "producción" if f.emitido_en_produccion else "pruebas"
            print(f"  {f.numero_completo}  {f.tipo.value:<13} {ambiente:<10} [{codigo}] {motivo}")

        ventas = len({f.venta_id for f in filas if f.venta_id})
        print(f"\nVentas afectadas: {ventas} (volverán a quedar pendientes de facturar)")

        print("\nSecuencias de correlativo:")
        for s in series:
            seq = _secuencia_de(s)
            actual = db.scalar(
                text("SELECT last_value FROM pg_sequences WHERE sequencename = :n"),
                {"n": seq},
            )
            # Lo que quedará en la serie una vez retirados los fallidos manda
            # sobre el valor actual: la secuencia debe continuar desde ahí.
            resto = db.scalar(
                select(func.max(ComprobanteElectronico.numero)).where(
                    func.upper(ComprobanteElectronico.serie) == s.upper(),
                    ComprobanteElectronico.id.not_in([f.id for f in filas]),
                )
            )
            siguiente = (resto or 0) + 1
            print(f"  {seq}: {actual} → la próxima emisión saldrá con {s}-{siguiente}")

        if not aplicar:
            print(
                "\n[SIMULACIÓN] No se ha modificado nada.\n"
                "Repite con --aplicar para descartarlos."
            )
            return

        ids = [f.id for f in filas]

        # Una nota de crédito que apuntara a uno de éstos impediría el DELETE.
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

        for s in series:
            seq = _secuencia_de(s)
            resto = db.scalar(
                select(func.max(ComprobanteElectronico.numero)).where(
                    func.upper(ComprobanteElectronico.serie) == s.upper()
                )
            )
            siguiente = (resto or 0) + 1
            db.execute(text(f"ALTER SEQUENCE IF EXISTS {seq} RESTART WITH {siguiente}"))
            print(f"  secuencia {seq} ajustada: la próxima será {s}-{siguiente}")

        db.commit()
        print(f"\nDescartados: {borrados} intentos fallidos.")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descarta los comprobantes en ERROR que SUNAT nunca aceptó"
    )
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Ejecuta el descarte. Sin esta bandera sólo informa.",
    )
    parser.add_argument(
        "--serie",
        default="",
        help="Acota a una serie concreta. Por defecto, todas.",
    )
    args = parser.parse_args()
    descartar(args.aplicar, args.serie.strip() or None)


if __name__ == "__main__":
    sys.exit(main())
