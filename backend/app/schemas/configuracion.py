"""Entrada y salida de la configuración de facturación.

Ningún secreto sale por aquí: de la clave SOL y la del certificado sólo se dice
**si están puestas**, nunca su contenido.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field


class ConfiguracionUpdate(BaseModel):
    """Todo opcional: el formulario envía sólo lo que cambia."""

    ruc: str | None = Field(default=None, max_length=11)
    razon_social: str | None = Field(default=None, max_length=200)
    nombre_comercial: str | None = Field(default=None, max_length=200)
    ubigeo: str | None = Field(default=None, max_length=6)
    direccion: str | None = Field(default=None, max_length=200)
    departamento: str | None = Field(default=None, max_length=60)
    provincia: str | None = Field(default=None, max_length=60)
    distrito: str | None = Field(default=None, max_length=60)

    serie_factura: str | None = Field(default=None, max_length=4)
    serie_boleta: str | None = Field(default=None, max_length=4)
    serie_nc_factura: str | None = Field(default=None, max_length=4)
    serie_nc_boleta: str | None = Field(default=None, max_length=4)

    sol_usuario: str | None = Field(default=None, max_length=60)
    #: Vacío significa «no la cambies»: el formulario nunca trae la actual.
    sol_clave: str | None = Field(default=None, max_length=100)

    produccion: bool | None = None
    declaracion_automatica: bool | None = None


class ConfiguracionOut(BaseModel):
    """Estado de la configuración, sin secretos."""

    tiene_certificado: bool
    certificado_nombre: str | None
    certificado_vence: date | None
    certificado_emitido_a: str | None
    certificado_cargado_at: datetime | None
    #: Negativo si ya venció. El día que caduca se deja de facturar.
    dias_para_vencer: int | None

    #: Enmascarado: es la mitad de la credencial y tampoco se devuelve entero.
    #: Sirve para reconocer cuál está puesto, no para reutilizarlo.
    sol_usuario: str | None
    tiene_sol_clave: bool

    produccion: bool
    ruc: str
    razon_social: str
    nombre_comercial: str
    ubigeo: str
    direccion: str
    departamento: str
    provincia: str
    distrito: str

    serie_factura: str
    serie_boleta: str
    serie_nc_factura: str
    serie_nc_boleta: str

    declaracion_automatica: bool
    #: Con todo lo necesario cargado se emite de verdad; si no, en simulación.
    lista_para_emitir: bool

    actualizado_por: str | None
    updated_at: datetime | None
