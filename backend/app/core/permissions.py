"""Catálogo central de permisos del ERP.

El código de permiso es `<modulo>.<accion>`. Este catálogo es la fuente de verdad:
el seed sincroniza la tabla `permissions` contra él, y los endpoints referencian
las constantes en vez de strings sueltos.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDef:
    code: str
    module: str
    description: str


def _crud(module: str, label: str, extra: dict[str, str] | None = None) -> list[PermissionDef]:
    base = {
        "ver": f"Ver {label}",
        "crear": f"Crear {label}",
        "editar": f"Editar {label}",
        "eliminar": f"Eliminar {label}",
    }
    base.update(extra or {})
    return [PermissionDef(f"{module}.{a}", module, d) for a, d in base.items()]


PERMISSIONS: list[PermissionDef] = [
    PermissionDef("dashboard.ver", "dashboard", "Ver el dashboard y sus KPIs"),
    *_crud("clientes", "clientes"),
    *_crud("bicicletas", "bicicletas"),
    *_crud(
        "fichas",
        "fichas de mantenimiento",
        {
            "cambiar_estado": "Cambiar el estado de una orden",
            "firmar": "Registrar firmas de entrega",
            "imprimir": "Generar el PDF de la ficha",
        },
    ),
    *_crud("inventario", "productos de inventario", {"ajustar_stock": "Ajustar stock y kardex"}),
    *_crud("ventas", "ventas", {"anular": "Anular una venta"}),
    *_crud(
        "facturacion",
        "documentos electrónicos",
        {"emitir": "Emitir comprobantes a SUNAT", "anular": "Anular o comunicar baja"},
    ),
    *_crud(
        "caja",
        "movimientos de caja",
        {"abrir": "Abrir caja", "cerrar": "Cerrar y arquear caja"},
    ),
    PermissionDef("reportes.ver", "reportes", "Ver reportes"),
    PermissionDef("reportes.exportar", "reportes", "Exportar reportes a PDF/Excel"),
    *_crud("usuarios", "usuarios"),
    *_crud("roles", "roles y permisos"),
    PermissionDef("auditoria.ver", "auditoria", "Ver la bitácora de auditoría"),
]

PERMISSION_CODES: set[str] = {p.code for p in PERMISSIONS}

# Roles base que se crean en el seed. El administrador recibe todos los permisos.
DEFAULT_ROLES: dict[str, dict[str, object]] = {
    "administrador": {
        "name": "Administrador",
        "description": "Acceso total al sistema",
        "permissions": "*",
    },
    "vendedor": {
        "name": "Vendedor",
        "description": "Atiende clientes, cotiza y vende",
        "permissions": [
            "dashboard.ver",
            "clientes.ver", "clientes.crear", "clientes.editar",
            "bicicletas.ver", "bicicletas.crear", "bicicletas.editar",
            "fichas.ver", "fichas.crear",
            "inventario.ver",
            "ventas.ver", "ventas.crear",
            "facturacion.ver", "facturacion.emitir",
            "reportes.ver",
        ],
    },
    "tecnico": {
        "name": "Técnico",
        "description": "Atiende el taller y las fichas de mantenimiento",
        "permissions": [
            "dashboard.ver",
            "clientes.ver",
            "bicicletas.ver", "bicicletas.crear", "bicicletas.editar",
            "fichas.ver", "fichas.crear", "fichas.editar",
            "fichas.cambiar_estado", "fichas.firmar", "fichas.imprimir",
            "inventario.ver", "inventario.ajustar_stock",
        ],
    },
    "cajero": {
        "name": "Cajero",
        "description": "Opera la caja y cobra las ventas",
        "permissions": [
            "dashboard.ver",
            "clientes.ver",
            "ventas.ver", "ventas.crear",
            "facturacion.ver", "facturacion.emitir",
            "caja.ver", "caja.crear", "caja.abrir", "caja.cerrar",
            "reportes.ver",
        ],
    },
}
