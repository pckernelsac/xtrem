"""Configuración de facturación editable desde la interfaz.

Hasta ahora el certificado y las claves SOL venían del entorno, lo que obliga a
tocar el despliegue para cambiarlos. Con esta tabla se pueden cargar desde la
aplicación, que es lo que hace falta cuando el certificado caduca un sábado.

**Fila única.** No hay varias configuraciones: el sistema factura para un solo
emisor. El identificador fijo lo garantiza sin depender de que nadie recuerde
no insertar una segunda.

Los secretos se guardan **cifrados** (ver `core/cifrado.py`) y no se devuelven
nunca por la API: se pueden reemplazar, no leer.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

#: Identificador fijo de la única fila.
ID_CONFIGURACION = uuid.UUID("00000000-0000-0000-0000-000000000001")


class ConfiguracionSunat(TimestampMixin, Base):
    """Datos del emisor, certificado y credenciales SOL."""

    __tablename__ = "configuracion_sunat"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=ID_CONFIGURACION)

    # --- Certificado digital ---
    #: Contenido del .pfx, cifrado. Nunca sale de aquí sin descifrar.
    certificado: Mapped[bytes | None] = mapped_column(LargeBinary)
    certificado_clave: Mapped[bytes | None] = mapped_column(LargeBinary)
    certificado_nombre: Mapped[str | None] = mapped_column(String(200))
    #: Se lee del propio certificado al cargarlo, para poder avisar antes de que
    #: caduque: el día que expira, se deja de facturar.
    certificado_vence: Mapped[date | None] = mapped_column(Date)
    certificado_emitido_a: Mapped[str | None] = mapped_column(String(300))

    # --- Credenciales SOL ---
    #: Usuario SECUNDARIO. El principal no debería usarse para esto.
    sol_usuario: Mapped[str | None] = mapped_column(String(60))
    sol_clave: Mapped[bytes | None] = mapped_column(LargeBinary)

    #: False = ambiente de pruebas de SUNAT; los documentos no tienen validez.
    produccion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Emisor y series ---
    ruc: Mapped[str | None] = mapped_column(String(11))
    razon_social: Mapped[str | None] = mapped_column(String(200))
    nombre_comercial: Mapped[str | None] = mapped_column(String(200))
    ubigeo: Mapped[str | None] = mapped_column(String(6))
    direccion: Mapped[str | None] = mapped_column(String(200))
    departamento: Mapped[str | None] = mapped_column(String(60))
    provincia: Mapped[str | None] = mapped_column(String(60))
    distrito: Mapped[str | None] = mapped_column(String(60))

    serie_factura: Mapped[str | None] = mapped_column(String(4))
    serie_boleta: Mapped[str | None] = mapped_column(String(4))
    serie_nc_factura: Mapped[str | None] = mapped_column(String(4))
    serie_nc_boleta: Mapped[str | None] = mapped_column(String(4))

    #: Manda el resumen del día anterior sin que nadie pulse nada. Va apagado
    #: por defecto: emitir a SUNAT sin intervención debe ser una decisión
    #: explícita de quien administra.
    declaracion_automatica: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    actualizado_por_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    actualizado_por: Mapped["User | None"] = relationship(lazy="joined")  # noqa: F821
    certificado_cargado_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    @property
    def tiene_certificado(self) -> bool:
        return self.certificado is not None

    @property
    def tiene_credenciales(self) -> bool:
        return bool(self.sol_usuario and self.sol_clave and self.certificado_clave)

    def dias_para_vencer(self, hoy: date) -> int | None:
        """Días que le quedan al certificado. Negativo si ya venció."""
        if self.certificado_vence is None:
            return None
        return (self.certificado_vence - hoy).days
