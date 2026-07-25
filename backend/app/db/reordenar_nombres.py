"""Reordena el nombre de los clientes con DNI que quedaron con los apellidos
delante ("QUISPE MAMANI ROSA" -> "ROSA QUISPE MAMANI").

Hasta ahora la consulta a RENIEC guardaba el nombre en el orden del padrón, y
por eso los saludos de WhatsApp llamaban al cliente por su apellido. El código
ya guarda el orden correcto; este script arregla lo que quedó registrado antes.

**No adivina el orden.** Vuelve a consultar cada DNI en RENIEC y sólo reescribe
el nombre cuando las palabras del padrón son exactamente las mismas que las
guardadas, sólo que en otro orden. Así un "Rosa Quispe Mamani" ya correcto se
deja igual, y un nombre editado a mano o que no corresponde al titular del DNI
se salta y se reporta en vez de pisarse.

Cada consulta cuesta un crédito de FactPro, así que conviene probar primero en
simulación y con `--limite`.

Correr con (en simulación, no toca la base):

    docker compose exec zx_api python -m app.db.reordenar_nombres

Ver primero unos pocos:

    docker compose exec zx_api python -m app.db.reordenar_nombres --limite 10

Aplicar de verdad:

    docker compose exec zx_api python -m app.db.reordenar_nombres --aplicar

Siempre deja un CSV de respaldo con el nombre anterior de cada cliente tocado,
para poder revertir a mano si hiciera falta.
"""

import argparse
import csv
import time
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.cliente import Cliente, TipoDocumento
from app.services.consulta_documento import consultar_dni

#: Pausa entre consultas: el padrón se consulta cliente por cliente y no hay
#: prisa; conviene no golpear la API de FactPro en ráfaga.
PAUSA_SEGUNDOS = 0.3

#: Un nombre del padrón trae siempre dos apellidos más el nombre de pila. Con
#: menos de tres palabras no hay nada que reordenar y la consulta sería un
#: crédito gastado en vano.
MINIMO_PALABRAS = 3


def _palabras(nombre: str) -> list[str]:
    """Palabras del nombre en mayúsculas y sin tildes, en su orden original.

    Se ignoran tildes y caja porque el padrón las escribe de forma
    inconsistente ("NUÑEZ" / "NÚÑEZ") y porque en el mostrador se teclea de
    cualquier manera: nada de eso cambia si el orden está bien o mal.
    """
    sin_tildes = unicodedata.normalize("NFKD", nombre.upper())
    limpio = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return limpio.split()


def _clave(nombre: str) -> Counter[str]:
    """Bolsa de palabras: dos nombres con la misma clave son el mismo con las
    palabras en otro orden."""
    return Counter(_palabras(nombre))


def _candidatos(db: Session, limite: int | None) -> list[Cliente]:
    stmt = (
        select(Cliente)
        .where(Cliente.tipo_documento == TipoDocumento.DNI)
        .order_by(Cliente.created_at)
    )
    clientes = [
        c
        for c in db.scalars(stmt).all()
        if c.numero_documento.isdigit()
        and len(c.numero_documento) == 8
        and len(c.nombre.split()) >= MINIMO_PALABRAS
    ]
    return clientes[:limite] if limite else clientes


def reordenar(db: Session, aplicar: bool, limite: int | None, csv_path: Path) -> None:
    # Sin token de consultas cada cliente daría el mismo 503; mejor cortar aquí
    # con el motivo, y no tras recorrer toda la cartera.
    if not settings.consulta_documento_disponible:
        raise SystemExit(
            "FACTPRO_CONSULTAS_TOKEN no está configurado: este script necesita "
            "consultar RENIEC para saber el orden correcto de cada nombre."
        )

    clientes = _candidatos(db, limite)
    print(f"Clientes con DNI a revisar: {len(clientes)}")
    if not clientes:
        return

    filas: list[dict[str, str]] = []
    corregidos = ya_ok = distintos = fallidos = 0

    for i, cliente in enumerate(clientes, start=1):
        # El nombre guardado se copia antes de tocar nada: es lo que va al CSV
        # de respaldo y lo único con lo que se podría revertir.
        original = cliente.nombre
        etiqueta = f"[{i}/{len(clientes)}] {cliente.numero_documento} {original}"

        try:
            datos = consultar_dni(cliente.numero_documento)
        except HTTPException as exc:
            fallidos += 1
            print(f"  ! {etiqueta}: no se pudo consultar ({exc.detail})")
            filas.append(
                {
                    "dni": cliente.numero_documento,
                    "nombre_antes": original,
                    "nombre_despues": "",
                    "accion": f"error: {exc.detail}",
                }
            )
            time.sleep(PAUSA_SEGUNDOS)
            continue

        nuevo = datos["nombre"]
        accion: str

        if _palabras(nuevo) == _palabras(original):
            # Mismo orden; si difiere en tildes o mayúsculas se respeta lo que
            # haya escrito la tienda, que suele estar mejor que el padrón.
            ya_ok += 1
            accion = "sin cambios"
        elif _clave(nuevo) != _clave(original):
            # Mismas palabras es la única prueba de que es la misma persona con
            # el orden cambiado. Si no coinciden, el nombre se tocó a mano o el
            # DNI es de otra persona: se reporta y se deja como está.
            distintos += 1
            accion = "revisar a mano"
            print(f"  ? {etiqueta}\n      RENIEC dice: {nuevo}")
        else:
            corregidos += 1
            accion = "reordenado" if aplicar else "reordenado (simulación)"
            print(f"  - {etiqueta}\n      queda como: {nuevo}")
            if aplicar:
                cliente.nombre = nuevo

        filas.append(
            {
                "dni": cliente.numero_documento,
                "nombre_antes": original,
                "nombre_despues": nuevo,
                "accion": accion,
            }
        )
        time.sleep(PAUSA_SEGUNDOS)

    # El respaldo se escribe antes del commit: si la escritura falla, no hay
    # cambios sin registro de cómo estaban.
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=["dni", "nombre_antes", "nombre_despues", "accion"])
        escritor.writeheader()
        escritor.writerows(filas)

    if aplicar:
        db.commit()

    print()
    print(f"Reordenados:      {corregidos}")
    print(f"Ya correctos:     {ya_ok}")
    print(f"Para revisar:     {distintos}")
    print(f"Con error:        {fallidos}")
    print(f"Detalle en:       {csv_path}")
    if not aplicar:
        print("\nSimulación: no se tocó la base. Repite con --aplicar para guardar.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Guarda los cambios. Sin esta bandera sólo simula.",
    )
    parser.add_argument(
        "--limite",
        type=int,
        help="Revisa sólo los N clientes más antiguos (para una prueba corta).",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        help="Ruta del CSV de respaldo. Por defecto, uno con la fecha en el directorio actual.",
    )
    args = parser.parse_args()

    csv_path = args.csv or Path(
        f"reordenar_nombres_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )

    db = SessionLocal()
    try:
        reordenar(db, aplicar=args.aplicar, limite=args.limite, csv_path=csv_path)
    finally:
        db.close()


if __name__ == "__main__":
    main()
