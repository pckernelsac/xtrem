"""Corte de demo a producción del facturador.

Al pasar la cuenta a producción cambian las series (`BBB1`/`FFF1` → las que
autorice SUNAT). El correlativo se reinicia solo, porque cada serie tiene su
propia secuencia (`comprobante_<serie>_seq`) y la de la serie nueva nace en 1.

Lo que **no** se arregla solo son los comprobantes que quedaron de la etapa de
pruebas: siguen en la tabla y no se distinguen de los reales. El registro de
ventas que se exporta para el contador filtra por fecha de emisión, no por
serie, así que un periodo que abarque las pruebas las declararía ante SUNAT como
si fueran documentos válidos. Este script las retira.

Uso (dentro del contenedor del backend):

    python -m app.db.corte_produccion              # sólo informa, no toca nada
    python -m app.db.corte_produccion --aplicar    # ejecuta el corte

Por defecto considera «de pruebas» todo comprobante cuya serie no sea una de las
configuradas ahora mismo (`SERIE_*`), así que hay que correrlo **después** de
cambiar las variables de entorno a producción y redesplegar. Con `--series` se
pueden indicar a mano, separadas por comas.
"""

import argparse
import sys

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.comprobante import ComprobanteElectronico
from app.models.venta import Venta


def _series_de_produccion() -> set[str]:
    return {
        settings.SERIE_FACTURA.upper(),
        settings.SERIE_BOLETA.upper(),
        settings.SERIE_NC_FACTURA.upper(),
        settings.SERIE_NC_BOLETA.upper(),
    }


def _resumen(db: Session, series_fuera: set[str]) -> list[tuple[str, str, int, int, int]]:
    """Por serie y tipo: cuántos comprobantes hay y en qué rango de números."""
    filas = db.execute(
        select(
            ComprobanteElectronico.serie,
            ComprobanteElectronico.tipo,
            func.count(ComprobanteElectronico.id),
            func.min(ComprobanteElectronico.numero),
            func.max(ComprobanteElectronico.numero),
        )
        .where(ComprobanteElectronico.serie.in_(series_fuera))
        .group_by(ComprobanteElectronico.serie, ComprobanteElectronico.tipo)
        .order_by(ComprobanteElectronico.serie)
    ).all()
    return [(s, t.value, c, mn, mx) for s, t, c, mn, mx in filas]


def _secuencias(db: Session) -> list[tuple[str, int]]:
    filas = db.execute(
        text(
            "SELECT sequencename, last_value FROM pg_sequences "
            "WHERE sequencename LIKE 'comprobante\\_%' ORDER BY sequencename"
        )
    ).all()
    return [(nombre, valor) for nombre, valor in filas]


def corte(aplicar: bool, series_manuales: set[str] | None, solo_pruebas: bool = False) -> None:
    db = SessionLocal()
    try:
        produccion = _series_de_produccion()
        print(f"Series de producción configuradas: {', '.join(sorted(produccion))}")

        if solo_pruebas:
            # Todo lo emitido contra el ambiente de pruebas, sea cual sea su
            # serie. Es lo que hace falta si ya se probó con la definitiva.
            fuera = set(
                db.scalars(
                    select(ComprobanteElectronico.serie)
                    .where(ComprobanteElectronico.emitido_en_produccion.is_(False))
                    .distinct()
                ).all()
            )
            print("Criterio: todo lo emitido en el ambiente de PRUEBAS.")
        elif series_manuales:
            fuera = series_manuales
        else:
            todas = set(db.scalars(select(ComprobanteElectronico.serie).distinct()).all())
            fuera = {s for s in todas if s.upper() not in produccion}

        if not fuera:
            print("No hay nada que retirar. Nada que hacer.")
            return

        print(f"Series afectadas: {', '.join(sorted(fuera))}\n")

        filas = _resumen(db, fuera)
        total = sum(f[2] for f in filas)
        for serie, tipo, cantidad, minimo, maximo in filas:
            print(f"  {serie} · {tipo}: {cantidad} comprobantes ({serie}-{minimo} a {serie}-{maximo})")
        print(f"\nTotal a borrar: {total}")

        # Las ventas no se tocan, pero conviene decir cuántas se quedan sin
        # comprobante: volverán a aparecer como pendientes de facturar, que es
        # justo lo que se quiere si eran ventas reales facturadas en pruebas.
        ventas = db.scalar(
            select(func.count(func.distinct(ComprobanteElectronico.venta_id))).where(
                ComprobanteElectronico.serie.in_(fuera),
                ComprobanteElectronico.venta_id.is_not(None),
            )
        ) or 0
        print(f"Ventas que quedarán sin comprobante: {ventas} (se podrán reemitir)")

        print("\nSecuencias de correlativo:")
        for nombre, valor in _secuencias(db):
            print(f"  {nombre}: {valor}")

        if not aplicar:
            print(
                "\n[SIMULACIÓN] No se ha modificado nada.\n"
                "Repite con --aplicar para ejecutar el corte."
            )
            return

        # La autorreferencia de las notas de crédito impediría el DELETE.
        db.execute(
            text(
                "UPDATE comprobantes SET documento_afectado_id = NULL "
                "WHERE documento_afectado_id IN "
                "(SELECT id FROM comprobantes WHERE serie = ANY(:series))"
            ),
            {"series": list(fuera)},
        )
        # Los lotes que informaron esos comprobantes dejan de tener sentido:
        # sin ellos quedarían apuntando a documentos que ya no existen.
        db.execute(
            text(
                "UPDATE comprobantes SET lote_id = NULL WHERE serie = ANY(:series)"
            ),
            {"series": list(fuera)},
        )
        lotes = db.execute(
            text(
                "DELETE FROM lotes_sunat WHERE id NOT IN "
                "(SELECT DISTINCT lote_id FROM comprobantes WHERE lote_id IS NOT NULL)"
            )
        ).rowcount
        borrados = db.execute(
            text("DELETE FROM comprobantes WHERE serie = ANY(:series)"), {"series": list(fuera)}
        ).rowcount
        if lotes:
            print(f"  resúmenes y bajas eliminados: {lotes}")

        # Las secuencias de las series retiradas se eliminan; las de producción
        # se reinician sólo si no tienen comprobantes todavía, para no romper la
        # correlatividad de una serie que ya empezó a emitir.
        for nombre, _ in _secuencias(db):
            serie = nombre.removeprefix("comprobante_").removesuffix("_seq").upper()
            if serie in {s.upper() for s in fuera}:
                db.execute(text(f"DROP SEQUENCE IF EXISTS {nombre}"))
                print(f"  secuencia eliminada: {nombre}")
            elif serie in produccion:
                emitidos = db.scalar(
                    select(func.count(ComprobanteElectronico.id)).where(
                        ComprobanteElectronico.serie == serie
                    )
                ) or 0
                if emitidos == 0:
                    db.execute(text(f"ALTER SEQUENCE {nombre} RESTART WITH 1"))
                    print(f"  secuencia reiniciada: {nombre}")
                else:
                    print(
                        f"  secuencia CONSERVADA: {nombre} ({emitidos} comprobantes ya "
                        "emitidos en esa serie)"
                    )

        db.commit()
        print(f"\nCorte aplicado. Comprobantes borrados: {borrados}")
        print("La próxima emisión de cada serie de producción saldrá con el número 1.")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retira comprobantes de prueba antes de emitir en producción"
    )
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Ejecuta el corte. Sin esta bandera sólo informa.",
    )
    parser.add_argument(
        "--series",
        default="",
        help="Series a retirar, separadas por comas. Por defecto, las que no estén configuradas.",
    )
    parser.add_argument(
        "--pruebas",
        action="store_true",
        help=(
            "Retira TODO lo emitido contra el ambiente de pruebas, sin mirar la "
            "serie. Es lo que hace falta si se probó con la serie definitiva."
        ),
    )
    args = parser.parse_args()

    manuales = {s.strip().upper() for s in args.series.split(",") if s.strip()}
    corte(args.aplicar, manuales or None, args.pruebas)


if __name__ == "__main__":
    sys.exit(main())
