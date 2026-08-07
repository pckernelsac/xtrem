import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.models.bicicleta import TipoBicicleta
from app.models.caja import MetodoPago
from app.models.comprobante import EstadoComprobante, TipoComprobante
from app.models.ficha import EstadoFicha, ServicioSolicitado
from app.models.inventario import TipoItem


class RepuestoIn(BaseModel):
    cantidad: Decimal = Field(default=Decimal("1"), gt=0, max_digits=10, decimal_places=2)
    descripcion: str = Field(min_length=1, max_length=200)
    marca: str | None = Field(default=None, max_length=80)
    precio_unitario: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2
    )
    #: Enlaza la línea con el inventario. Si viene, la pieza se descuenta del
    #: stock; si no, es texto libre y no mueve el almacén.
    producto_id: uuid.UUID | None = None


class ProductoRepuesto(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    nombre: str
    #: Un servicio no lleva existencias; sin el tipo, la ficha mostraría
    #: "disponible 0" y alarmaría por una línea que nunca toca el almacén.
    tipo: TipoItem
    stock_actual: Decimal


class RepuestoOut(RepuestoIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    orden: int
    subtotal: Decimal
    producto: ProductoRepuesto | None = None


class ClienteFicha(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    tipo_documento: str
    numero_documento: str
    telefono: str | None
    email: str | None


class BicicletaFicha(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    marca: str
    modelo: str | None
    color: str | None
    numero_serie: str | None
    tipo: TipoBicicleta


class UsuarioFicha(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str


class FichaBase(BaseModel):
    canal_referencia: str | None = Field(default=None, max_length=120)
    servicios: list[ServicioSolicitado] = Field(default_factory=list)
    servicio_otro: str | None = Field(default=None, max_length=200)
    costo_servicio: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2
    )
    diagnostico_inicial: str | None = None
    trabajo_realizado: str | None = None
    tiempo_invertido_min: int | None = Field(default=None, ge=0, le=100_000)
    observaciones: str | None = None
    garantia_dias: int | None = Field(default=None, ge=0, le=3650)

    @field_validator("servicios")
    @classmethod
    def sin_duplicados(cls, v: list[ServicioSolicitado]) -> list[ServicioSolicitado]:
        # Se preserva el orden de la ficha impresa pero se descartan repetidos.
        vistos: list[ServicioSolicitado] = []
        for s in v:
            if s not in vistos:
                vistos.append(s)
        return vistos


class FichaCreate(FichaBase):
    cliente_id: uuid.UUID
    #: Varias: un cliente puede dejar dos o más bicicletas en el mismo servicio.
    #: Vacío es válido: un servicio de sólo mano de obra no lleva ninguna.
    bicicleta_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    fecha_recepcion: datetime | None = None
    tecnico_recepcion_id: uuid.UUID | None = None
    tecnico_responsable_id: uuid.UUID | None = None
    #: Anticipo cobrado al recibir. Entra a caja al crear y no se edita después.
    adelanto: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=10, decimal_places=2)
    adelanto_metodo: MetodoPago | None = None
    repuestos: list[RepuestoIn] = Field(default_factory=list)


class FichaUpdate(FichaBase):
    canal_referencia: str | None = None
    servicios: list[ServicioSolicitado] | None = None  # type: ignore[assignment]
    costo_servicio: Decimal | None = None  # type: ignore[assignment]
    fecha_recepcion: datetime | None = None
    tecnico_recepcion_id: uuid.UUID | None = None
    tecnico_responsable_id: uuid.UUID | None = None
    tecnico_entrega_id: uuid.UUID | None = None
    #: Si viene, reemplaza la lista completa de bicicletas del servicio.
    bicicleta_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)
    #: Corregir el adelanto mueve caja: la diferencia se compensa con su propio
    #: movimiento en la sesión abierta, no se reescribe el cobro de recepción.
    adelanto: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    adelanto_metodo: MetodoPago | None = None
    #: Si viene, reemplaza la tabla completa de repuestos (no hace merge fila a fila).
    repuestos: list[RepuestoIn] | None = None


class CambioEstadoIn(BaseModel):
    estado: EstadoFicha
    comentario: str | None = Field(default=None, max_length=300)


class AjusteAdelantoIn(BaseModel):
    """Corrección del adelanto cobrado en recepción.

    Es el importe final que queda en la ficha, no la diferencia: la caja se
    ajusta sola con el movimiento que falte.
    """

    adelanto: Decimal = Field(ge=0, max_digits=10, decimal_places=2)
    #: Método del adelanto corregido. Si no viene, se conserva el que tenía.
    adelanto_metodo: MetodoPago | None = None
    motivo: str | None = Field(default=None, max_length=200)


class EstadoLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    estado_anterior: EstadoFicha | None
    estado_nuevo: EstadoFicha
    comentario: str | None
    created_at: datetime
    usuario: UsuarioFicha | None


class FichaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    numero: str
    estado: EstadoFicha
    cliente: ClienteFicha
    #: Puede venir vacía: hay servicios de sólo mano de obra.
    bicicletas: list[BicicletaFicha] = Field(default_factory=list)
    fecha_recepcion: datetime
    fecha_entrega: datetime | None
    tecnico_recepcion: UsuarioFicha | None
    tecnico_responsable: UsuarioFicha | None
    total_repuestos: Decimal
    costo_servicio: Decimal
    total: Decimal
    adelanto: Decimal
    saldo: Decimal
    archivada: bool = False
    created_at: datetime


class FacturacionFichaOut(BaseModel):
    """Resumen del documento al que derivó el servicio, si ya se cobró.

    Un servicio cobrado siempre tiene su nota de venta (la venta que respalda el
    importe); los campos del comprobante llegan vacíos mientras no se haya
    emitido la boleta o factura electrónica.
    """

    venta_id: uuid.UUID
    venta_numero: str
    comprobante_id: uuid.UUID | None = None
    tipo: TipoComprobante | None = None
    numero: str | None = None
    estado: EstadoComprobante | None = None
    es_simulado: bool = False
    #: Enlace público al PDF (`/c/{codigo}`), que se genera al pedirlo.
    pdf_url: str | None = None


class FichaDetail(FichaOut):
    codigo_publico: str
    canal_referencia: str | None
    servicios: list[str]
    servicio_otro: str | None
    diagnostico_inicial: str | None
    trabajo_realizado: str | None
    tiempo_invertido_min: int | None
    observaciones: str | None
    garantia_dias: int | None
    adelanto_metodo: MetodoPago | None
    tecnico_entrega: UsuarioFicha | None
    repuestos: list[RepuestoOut]
    historial_estados: list[EstadoLogOut]
    #: Lo rellena el endpoint de detalle; no es una columna de la ficha.
    facturacion: FacturacionFichaOut | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def servicios_labels(self) -> list[str]:
        from app.models.ficha import ETIQUETAS_SERVICIO

        return [ETIQUETAS_SERVICIO.get(s, s) for s in self.servicios]


class FichaPage(BaseModel):
    items: list[FichaOut]
    total: int
    page: int
    page_size: int


class PagoServicioIn(BaseModel):
    """Un cobro del saldo al convertir el servicio en comprobante."""

    metodo: MetodoPago
    monto: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    referencia: str | None = Field(default=None, max_length=80)


class FacturarFichaIn(BaseModel):
    """Cobro del servicio, tanto para la nota de venta como para el electrónico."""

    #: Pagos que cubren el saldo pendiente del servicio. El adelanto ya
    #: registrado en recepción no se repite aquí.
    pagos: list[PagoServicioIn] = Field(default_factory=list)


class CompartirOut(BaseModel):
    """Enlaces para entregar la ficha al cliente."""

    url_pdf: str
    #: Teléfono normalizado a formato internacional, o None si no era usable.
    telefono: str | None
    whatsapp_url: str
    mensaje: str


class ConteoEstados(BaseModel):
    """Contadores para las tabs del listado: Todas (17) · Recibida (11) · ..."""

    todas: int
    por_estado: dict[str, int]
    #: Fuera del tablero; no entran en `todas` ni en `por_estado`.
    archivadas: int = 0
