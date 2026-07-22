import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin
from app.models.ficha import generar_codigo_publico


class TipoComprobante(str, enum.Enum):
    FACTURA = "FACTURA"
    BOLETA = "BOLETA"
    NOTA_CREDITO = "NOTA_CREDITO"


class EstadoComprobante(str, enum.Enum):
    """Estado local del comprobante en su ciclo de vida.

    No confundir con el `tipo_estado` que devuelve SUNAT (01=Registrado,
    05=Aceptado, …): ese se guarda aparte en `tipo_estado_sunat`.
    """

    PENDIENTE = "PENDIENTE"     # creado localmente, aún no enviado
    REGISTRADO = "REGISTRADO"   # aceptado por FactPro, en cola hacia SUNAT
    ACEPTADO = "ACEPTADO"       # SUNAT lo aceptó (con CDR)
    RECHAZADO = "RECHAZADO"     # SUNAT lo rechazó
    ANULADO = "ANULADO"         # comunicado de baja aceptado
    ERROR = "ERROR"             # falló el envío (red, validación de FactPro)


ETIQUETAS_ESTADO_COMPROBANTE: dict[str, str] = {
    "PENDIENTE": "Pendiente",
    "REGISTRADO": "Registrado",
    "ACEPTADO": "Aceptado",
    "RECHAZADO": "Rechazado",
    "ANULADO": "Anulado",
    "ERROR": "Error",
}

ETIQUETAS_TIPO_COMPROBANTE: dict[str, str] = {
    "FACTURA": "Factura",
    "BOLETA": "Boleta",
    "NOTA_CREDITO": "Nota de crédito",
}


class ComprobanteElectronico(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "comprobantes"
    __table_args__ = (
        Index("ix_comprobantes_estado", "estado"),
        Index("ix_comprobantes_tipo", "tipo"),
        # Único por serie-número, pero sólo para comprobantes que llegaron a
        # emitirse: los intentos en ERROR quedan con número 0 y no deben chocar
        # entre sí ni impedir el reintento.
        Index(
            "ux_comprobantes_serie_numero",
            "serie",
            "numero",
            unique=True,
            postgresql_where=text("estado <> 'ERROR'"),
        ),
    )

    tipo: Mapped[TipoComprobante] = mapped_column(
        Enum(TipoComprobante, name="tipo_comprobante"), nullable=False
    )
    estado: Mapped[EstadoComprobante] = mapped_column(
        Enum(EstadoComprobante, name="estado_comprobante"),
        default=EstadoComprobante.PENDIENTE,
        nullable=False,
    )

    serie: Mapped[str] = mapped_column(String(8), nullable=False)
    numero: Mapped[int] = mapped_column(nullable=False)

    #: Código corto para el enlace público del PDF (/c/{codigo}) que se manda
    #: por WhatsApp. Es la única credencial: equivale a la copia que el cliente
    #: ya tiene. Comparte alfabeto y largo con el código de las fichas.
    codigo_publico: Mapped[str] = mapped_column(
        String(16), unique=True, index=True, default=lambda: generar_codigo_publico()
    )

    @property
    def numero_completo(self) -> str:
        return f"{self.serie}-{self.numero}"

    #: Venta que factura. Una venta factura una sola vez (índice único parcial):
    #: reemitir tras un rechazo se hace anulando y creando otra venta.
    venta_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ventas.id", ondelete="RESTRICT"), index=True
    )
    venta: Mapped["Venta | None"] = relationship(lazy="joined")  # noqa: F821

    #: Para notas de crédito: el comprobante que anulan/corrigen.
    documento_afectado_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("comprobantes.id", ondelete="SET NULL")
    )

    fecha_emision: Mapped[date] = mapped_column(Date, nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), default="PEN", nullable=False)

    # --- Importes congelados al emitir ---
    #: Se guardan aquí y no se leen de la venta a propósito: el comprobante es
    #: un documento tributario y su importe no puede depender de que la venta
    #: siga existiendo ni de que nadie la haya tocado después. Nulos sólo en
    #: los comprobantes anteriores a este cambio cuya venta ya no existe.
    base_imponible: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    igv: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    # --- Identidad del receptor, congelada al emitir ---
    cliente_tipo_documento: Mapped[str] = mapped_column(String(2))
    cliente_numero_documento: Mapped[str] = mapped_column(String(15))
    cliente_denominacion: Mapped[str] = mapped_column(String(200))

    # --- Datos que devuelve SUNAT/FactPro ---
    tipo_estado_sunat: Mapped[str | None] = mapped_column(String(4))
    descripcion_estado_sunat: Mapped[str | None] = mapped_column(String(60))
    hash_cpe: Mapped[str | None] = mapped_column(String(120))
    qr: Mapped[str | None] = mapped_column(Text)

    xml_url: Mapped[str | None] = mapped_column(String(400))
    pdf_url: Mapped[str | None] = mapped_column(String(400))
    cdr_url: Mapped[str | None] = mapped_column(String(400))

    #: JSON exacto que se envió y la respuesta cruda: trazabilidad total ante
    #: una observación de SUNAT o una diferencia con FactPro.
    payload_enviado: Mapped[dict | None] = mapped_column(JSONB)
    respuesta: Mapped[dict | None] = mapped_column(JSONB)
    mensaje_error: Mapped[str | None] = mapped_column(Text)

    motivo_anulacion: Mapped[str | None] = mapped_column(String(300))
    fecha_anulacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Marca los comprobantes emitidos SIN SUNAT real (sin token FactPro).
    #: Distingue una demo de un documento tributario válido; nunca debe
    #: presentarse como legal.
    es_simulado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    usuario: Mapped["User | None"] = relationship(lazy="joined")  # noqa: F821

    fecha_envio: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
