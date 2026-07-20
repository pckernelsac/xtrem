"""El «día» del negocio.

Todo se guarda en UTC —`created_at`, `fecha_apertura`, etc.— y eso está bien:
es un instante, sin ambigüedad. Pero «hoy», «ayer» o «del 19 al 20» no son
instantes, son días *del taller*, y el taller está en Lima.

Calcular esos límites en UTC es un error silencioso que sólo aparece de noche:
la medianoche UTC son las 7 p. m. en Lima, así que todo lo vendido entre las
7 p. m. y la medianoche se contaba como del día siguiente. El dashboard mostraba
en «ingresos de hoy» la caja de anoche.

Perú no aplica horario de verano, así que el desfase es siempre −5, pero se usa
`ZoneInfo` igual: si algún día se abre sucursal en otra zona, basta cambiar
`TIMEZONE`.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings

TZ_NEGOCIO = ZoneInfo(settings.TIMEZONE)


def ahora_local() -> datetime:
    """El instante actual, expresado en la zona del negocio."""
    return datetime.now(TZ_NEGOCIO)


def hoy_local() -> date:
    """Qué día es hoy para el taller, no para el servidor."""
    return ahora_local().date()


def dia_local(momento: datetime) -> date:
    """A qué día del taller pertenece un instante guardado en UTC."""
    return momento.astimezone(TZ_NEGOCIO).date()


def inicio_del_dia(dia: date) -> datetime:
    """Medianoche de `dia` en Lima, como instante UTC para comparar en la BD."""
    return datetime.combine(dia, time.min, tzinfo=TZ_NEGOCIO)


def rango_utc(desde: date | None, hasta: date | None) -> tuple[datetime | None, datetime | None]:
    """Convierte un rango de días del taller en `[inicio, fin)` comparable.

    `hasta` es inclusive: se devuelve la medianoche del día siguiente como
    extremo abierto, que es la única forma de incluir el último día entero sin
    depender de la precisión del timestamp.
    """
    ini = inicio_del_dia(desde) if desde else None
    fin = inicio_del_dia(hasta + timedelta(days=1)) if hasta else None
    return ini, fin
