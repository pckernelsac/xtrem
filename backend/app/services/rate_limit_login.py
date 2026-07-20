"""Freno a la fuerza bruta contra el login.

Sin esto, un atacante puede probar contraseñas contra `admin@zonaxtrema.pe`
indefinidamente: el endpoint respondía 401 y nada más. La contención es doble:

* **Por cuenta**: protege al usuario concreto que están atacando.
* **Por IP**: evita que desde una misma máquina se rocíe una contraseña común
  sobre muchos correos distintos (*password spraying*), que el contador por
  cuenta no vería.

El castigo por cuenta es escalonado —cuanto más insiste, más espera— para que
un empleado que se equivoca dos veces no quede fuera media hora, pero un script
sí se detenga en seco.
"""

import ipaddress
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.intento_login import IntentoLogin

#: Ventana en la que se acumulan los fallos. Pasada, la cuenta vuelve a cero.
VENTANA = timedelta(minutes=15)

#: Fallos tolerados por cuenta antes del primer bloqueo.
MAX_POR_CUENTA = 5

#: Espera según cuántos fallos van. El escalón se elige por el número de fallos
#: acumulados, así que insistir durante el bloqueo lo alarga.
ESCALONES = (
    (5, timedelta(minutes=1)),
    (7, timedelta(minutes=5)),
    (10, timedelta(minutes=15)),
    (15, timedelta(minutes=30)),
)

#: Tope por IP: cubre el rociado sobre muchos correos desde la misma máquina.
MAX_POR_IP = 20
BLOQUEO_IP = timedelta(minutes=15)


def ip_de(request: Request) -> str | None:
    """IP del cliente, mirando la cabecera del proxy si la hay.

    Detrás de Traefik/nginx todas las peticiones llegan desde la IP del proxy;
    sin leer `X-Forwarded-For` el límite por IP bloquearía a todo el mundo a la
    vez. La cabecera es falsificable si el servicio queda expuesto sin proxy
    delante, y por eso el límite por cuenta —que no depende de ella— es la
    defensa principal.
    """
    directa = request.client.host if request.client else None

    reenviada = request.headers.get("x-forwarded-for")
    if not reenviada:
        return directa

    # La cabecera la escribe quien quiera: si no es una IP válida se descarta y
    # se usa la de la conexión. Sin esto, un valor cualquiera acabaría en la
    # base o rompería la consulta.
    candidata = reenviada.split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(candidata))
    except ValueError:
        return directa


def _espera_por_fallos(fallos: int) -> timedelta | None:
    espera = None
    for minimo, duracion in ESCALONES:
        if fallos >= minimo:
            espera = duracion
    return espera


def _segundos(hasta: datetime, ahora: datetime) -> int:
    return max(1, int((hasta - ahora).total_seconds()))


def verificar(db: Session, email: str, ip: str | None) -> None:
    """Lanza 429 si la cuenta o la IP están en penitencia.

    Se llama ANTES de comprobar la contraseña: si no, cada intento bloqueado
    seguiría gastando un hash de bcrypt, que es justo lo caro.
    """
    ahora = datetime.now(UTC)
    desde = ahora - VENTANA

    fallos_cuenta = (
        db.scalar(
            select(func.count())
            .select_from(IntentoLogin)
            .where(
                IntentoLogin.email == email,
                IntentoLogin.exito.is_(False),
                IntentoLogin.created_at >= desde,
            )
        )
        or 0
    )

    espera = _espera_por_fallos(fallos_cuenta)
    if espera is not None:
        ultimo = db.scalar(
            select(func.max(IntentoLogin.created_at)).where(
                IntentoLogin.email == email,
                IntentoLogin.exito.is_(False),
                IntentoLogin.created_at >= desde,
            )
        )
        if ultimo is not None:
            if ultimo.tzinfo is None:
                ultimo = ultimo.replace(tzinfo=UTC)
            libre = ultimo + espera
            if libre > ahora:
                segundos = _segundos(libre, ahora)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Demasiados intentos fallidos. Vuelve a intentarlo en "
                        f"{max(1, round(segundos / 60))} minuto(s)."
                    ),
                    headers={"Retry-After": str(segundos)},
                )

    if ip:
        fallos_ip = (
            db.scalar(
                select(func.count())
                .select_from(IntentoLogin)
                .where(
                    IntentoLogin.ip == ip,
                    IntentoLogin.exito.is_(False),
                    IntentoLogin.created_at >= desde,
                )
            )
            or 0
        )
        if fallos_ip >= MAX_POR_IP:
            ultimo_ip = db.scalar(
                select(func.max(IntentoLogin.created_at)).where(
                    IntentoLogin.ip == ip,
                    IntentoLogin.exito.is_(False),
                    IntentoLogin.created_at >= desde,
                )
            )
            if ultimo_ip is not None:
                if ultimo_ip.tzinfo is None:
                    ultimo_ip = ultimo_ip.replace(tzinfo=UTC)
                libre = ultimo_ip + BLOQUEO_IP
                if libre > ahora:
                    segundos = _segundos(libre, ahora)
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=(
                            "Demasiados intentos fallidos desde esta conexión. "
                            f"Vuelve a intentarlo en {max(1, round(segundos / 60))} minuto(s)."
                        ),
                        headers={"Retry-After": str(segundos)},
                    )


def registrar(
    db: Session,
    email: str,
    ip: str | None,
    *,
    exito: bool,
    user_agent: str | None = None,
) -> None:
    """Anota el intento. Se hace commit propio: el fallo debe quedar guardado
    aunque la petición termine en 401."""
    db.add(
        IntentoLogin(
            email=email,
            ip=ip,
            exito=exito,
            user_agent=(user_agent or "")[:200] or None,
        )
    )
    db.commit()


def limpiar(db: Session, email: str, ip: str | None) -> None:
    """Borra los fallos recientes tras entrar bien.

    Quien acierta demuestra ser el dueño de la cuenta: arrastrar sus fallos
    previos sólo serviría para bloquearlo en el siguiente error de tipeo.
    """
    desde = datetime.now(UTC) - VENTANA
    condiciones = [
        IntentoLogin.exito.is_(False),
        IntentoLogin.created_at >= desde,
        IntentoLogin.email == email,
    ]
    db.query(IntentoLogin).filter(*condiciones).delete(synchronize_session=False)
    db.commit()


def purgar_antiguos(db: Session, dias: int = 30) -> int:
    """Los intentos viejos ya no frenan nada y sólo engordan la tabla."""
    limite = datetime.now(UTC) - timedelta(days=dias)
    borrados = (
        db.query(IntentoLogin)
        .filter(IntentoLogin.created_at < limite)
        .delete(synchronize_session=False)
    )
    db.commit()
    return borrados
