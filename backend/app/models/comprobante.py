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

    @property
    def tiene_xml(self) -> bool:
        """Si se guardó el XML firmado, que es el documento con valor legal.

        Los emitidos con el proveedor anterior no lo tienen: sus archivos vivían
        en el servidor de aquél, que es justamente lo que se dejó de depender.
        """
        return bool(self.xml_firmado)

    @property
    def tiene_cdr(self) -> bool:
        """Si SUNAT ya devolvió la constancia de recepción."""
        return bool(self.cdr_xml)

    #: Venta que factura. Una venta factura una sola vez (índice único parcial):
    #: reemitir tras un rechazo se hace anulando y creando otra venta.
    venta_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ventas.id", ondelete="RESTRICT"), index=True
    )
    venta: Mapped["Venta | None"] = relationship(lazy="joined")  # noqa: F821
    lote: Mapped["LoteSunat | None"] = relationship(back_populates="comprobantes")

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
    #: 300 y no 60: Nubefact devuelve frases completas ("La Factura numero
    #: FFF1-1, ha sido aceptada") y los rechazos de SUNAT son más largos aún.
    descripcion_estado_sunat: Mapped[str | None] = mapped_column(String(300))
    hash_cpe: Mapped[str | None] = mapped_column(String(120))
    qr: Mapped[str | None] = mapped_column(Text)

    #: URLs de los proveedores anteriores. Se conservan por los comprobantes
    #: históricos; emitiendo directo ya no se usan, porque el archivo es propio.
    xml_url: Mapped[str | None] = mapped_column(String(400))
    pdf_url: Mapped[str | None] = mapped_column(String(400))
    cdr_url: Mapped[str | None] = mapped_column(String(400))

    #: El XML firmado y el CDR, guardados aquí y no en disco ni en un tercero.
    #: SUNAT obliga a conservarlos cinco años, y el contenedor es desechable.
    xml_firmado: Mapped[str | None] = mapped_column(Text)
    cdr_xml: Mapped[str | None] = mapped_column(Text)

    #: Anulado en el ERP pero aún sin comunicar a SUNAT. La baja no es
    #: inmediata: las facturas van en un lote (RA) y las boletas se anulan
    #: informándolas en el resumen diario con estado 3.
    baja_pendiente: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    #: Lote en el que se informó a SUNAT. Las boletas **deben** ir en un
    #: resumen diario; mientras esto sea nulo, la boleta está emitida pero no
    #: declarada, que es un incumplimiento con plazo.
    lote_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lotes_sunat.id", ondelete="SET NULL"), index=True
    )

    #: JSON exacto que se envió y la respuesta cruda: trazabilidad total ante
    #: una observación de SUNAT o una diferencia con FactPro.
    payload_enviado: Mapped[dict | None] = mapped_column(JSONB)
    respuesta: Mapped[dict | None] = mapped_column(JSONB)
    mensaje_error: Mapped[str | None] = mapped_column(Text)

    motivo_anulacion: Mapped[str | None] = mapped_column(String(300))
    fecha_anulacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Marca los comprobantes que NO llegaron a enviarse a SUNAT (sin
    #: certificado configurado). Nunca deben presentarse como válidos.
    es_simulado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    #: Ambiente en el que se emitió, congelado al emitir. **No se deduce del
    #: ajuste actual**: al pasar a producción, los comprobantes de prueba
    #: seguirían pareciendo válidos y se colarían en el registro del contador,
    #: que filtra por fecha y no sabría distinguirlos.
    emitido_en_produccion: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    usuario: Mapped["User | None"] = relationship(lazy="joined")  # noqa: F821

    fecha_envio: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TipoLote(str, enum.Enum):
    """Documentos que agrupan comprobantes y se procesan en diferido."""

    #: Resumen diario de boletas. Obligatorio: emitir la boleta no la declara.
    RESUMEN = "RC"
    #: Comunicación de baja, para anular facturas y sus notas.
    BAJA = "RA"


class EstadoLote(str, enum.Enum):
    #: Armado pero todavía no enviado.
    PENDIENTE = "PENDIENTE"
    #: Enviado; SUNAT devolvió un ticket y lo está procesando.
    ENVIADO = "ENVIADO"
    ACEPTADO = "ACEPTADO"
    RECHAZADO = "RECHAZADO"
    ERROR = "ERROR"


ETIQUETAS_ESTADO_LOTE: dict[str, str] = {
    "PENDIENTE": "Pendiente",
    "ENVIADO": "En proceso",
    "ACEPTADO": "Aceptado",
    "RECHAZADO": "Rechazado",
    "ERROR": "Error",
}


class LoteSunat(UUIDMixin, TimestampMixin, Base):
    """Un resumen diario o una comunicación de baja enviados a SUNAT.

    Se guarda como entidad propia y no como un campo del comprobante porque el
    proceso es **asíncrono**: se envía, SUNAT devuelve un ticket y el CDR se
    recoge después. Entre esos dos momentos hay que saber qué se mandó, cuándo y
    con qué ticket, o el resumen se pierde y las boletas quedan sin declarar.
    """

    __tablename__ = "lotes_sunat"
    __table_args__ = (
        Index("ix_lotes_sunat_estado", "estado"),
        Index("ux_lotes_sunat_identificador", "identificador", unique=True),
    )

    # `values_callable` hace que se guarde el VALOR ("RC"/"RA") y no el nombre
    # del miembro, que es lo que SQLAlchemy persiste por defecto. Así la base
    # habla el idioma de SUNAT y el código conserva nombres legibles.
    tipo: Mapped[TipoLote] = mapped_column(
        Enum(
            TipoLote,
            name="tipo_lote",
            values_callable=lambda enum: [miembro.value for miembro in enum],
        ),
        nullable=False,
    )
    estado: Mapped[EstadoLote] = mapped_column(
        Enum(EstadoLote, name="estado_lote"), default=EstadoLote.PENDIENTE, nullable=False
    )

    #: RC-20260804-1 o RA-20260804-1. Único: SUNAT rechaza un identificador
    #: repetido, y repetirlo suele significar que se envió dos veces lo mismo.
    identificador: Mapped[str] = mapped_column(String(30), nullable=False)
    #: Día de los comprobantes que se informan.
    fecha_referencia: Mapped[date] = mapped_column(Date, nullable=False)
    #: Día en que se comunica. SUNAT da un plazo desde la referencia.
    fecha_emision: Mapped[date] = mapped_column(Date, nullable=False)
    correlativo: Mapped[int] = mapped_column(nullable=False)

    #: Lo devuelve SUNAT al aceptar el envío; con él se recoge el CDR después.
    ticket: Mapped[str | None] = mapped_column(String(40), index=True)

    codigo_sunat: Mapped[str | None] = mapped_column(String(10))
    descripcion_sunat: Mapped[str | None] = mapped_column(String(500))
    mensaje_error: Mapped[str | None] = mapped_column(Text)

    #: El archivo es nuestro, igual que en los comprobantes.
    xml_firmado: Mapped[str | None] = mapped_column(Text)
    cdr_xml: Mapped[str | None] = mapped_column(Text)

    es_simulado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    emitido_en_produccion: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    usuario: Mapped["User | None"] = relationship(lazy="joined")  # noqa: F821

    comprobantes: Mapped[list["ComprobanteElectronico"]] = relationship(
        back_populates="lote", lazy="selectin"
    )

    @property
    def cantidad(self) -> int:
        return len(self.comprobantes)

    @property
    def pendiente_de_cdr(self) -> bool:
        """Enviado pero sin respuesta: hay que volver a consultar el ticket."""
        return self.estado is EstadoLote.ENVIADO and bool(self.ticket)
