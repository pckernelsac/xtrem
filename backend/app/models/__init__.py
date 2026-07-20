"""Registro central de modelos ORM.

Cada fase agrega aquí sus imports para que Alembic los detecte en autogenerate.
"""

from app.models.auditoria import RegistroAuditoria
from app.models.bicicleta import Bicicleta, TipoBicicleta
from app.models.caja import (
    EstadoCaja,
    MetodoPago,
    MovimientoCaja,
    SesionCaja,
    TipoMovimientoCaja,
)
from app.models.cliente import Cliente, TipoDocumento
from app.models.comprobante import (
    ComprobanteElectronico,
    EstadoComprobante,
    TipoComprobante,
)
from app.models.intento_login import IntentoLogin
from app.models.ficha import (
    EstadoFicha,
    Ficha,
    FichaEstadoLog,
    FichaRepuesto,
    ServicioSolicitado,
)
from app.models.inventario import (
    Categoria,
    MovimientoKardex,
    Producto,
    TipoMovimiento,
    UnidadMedida,
)
from app.models.role import Permission, Role, role_permissions
from app.models.user import User
from app.models.venta import (
    EstadoVenta,
    PagoVenta,
    TipoVenta,
    Venta,
    VentaItem,
)

__all__ = [
    "EstadoCaja",
    "MetodoPago",
    "MovimientoCaja",
    "SesionCaja",
    "TipoMovimientoCaja",
    "EstadoVenta",
    "PagoVenta",
    "TipoVenta",
    "Venta",
    "VentaItem",
    "Categoria",
    "MovimientoKardex",
    "Producto",
    "TipoMovimiento",
    "UnidadMedida",
    "Bicicleta",
    "TipoBicicleta",
    "Cliente",
    "TipoDocumento",
    "ComprobanteElectronico",
    "EstadoComprobante",
    "TipoComprobante",
    "EstadoFicha",
    "Ficha",
    "FichaEstadoLog",
    "FichaRepuesto",
    "IntentoLogin",
    "ServicioSolicitado",
    "Permission",
    "Role",
    "role_permissions",
    "User",
    "RegistroAuditoria",
]
