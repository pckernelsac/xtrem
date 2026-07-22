from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.router import api_router
from app.api.routes import publico, publico_comprobante
from app.core.audit import AuditMiddleware
from app.core.config import settings
from app.db.session import engine

DESCRIPCION = """
ERP de **Zona Xtrema Bikes & Componentes**: taller de bicicletas, inventario,
ventas, caja y facturación electrónica SUNAT.

### Autenticación
La mayoría de endpoints requieren un **token JWT** en el header
`Authorization: Bearer <token>`. Obtén uno en `POST /api/v1/auth/login` y pégalo
en el botón **Authorize** 🔒 de esta página para probar los endpoints protegidos.

### Permisos
Cada endpoint exige un permiso granular (`ventas.crear`, `fichas.imprimir`, …).
El token lleva el rol del usuario; un `403` significa que falta el permiso.
"""

TAGS = [
    {"name": "auth", "description": "Login, refresh de token y cambio de contraseña."},
    {"name": "usuarios", "description": "Cuentas del sistema."},
    {"name": "roles", "description": "Roles y matriz de permisos."},
    {"name": "clientes", "description": "Directorio de clientes."},
    {"name": "bicicletas", "description": "Bicicletas y su historial."},
    {"name": "fichas", "description": "Órdenes de taller, PDF, ticket térmico y firmas."},
    {"name": "inventario", "description": "Productos, categorías, kardex e importación."},
    {"name": "ventas", "description": "Ventas, cotizaciones y su ciclo de vida."},
    {"name": "caja", "description": "Apertura, movimientos y arqueo de caja."},
    {"name": "facturación", "description": "Comprobantes electrónicos vía FactPro."},
    {"name": "reportes", "description": "Reportes y exportación a Excel/PDF."},
    {"name": "sistema", "description": "Notificaciones accionables."},
    {"name": "auditoría", "description": "Bitácora de acciones."},
    {"name": "infra", "description": "Health checks."},
]

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description=DESCRIPCION,
    summary="ERP para taller y tienda de bicicletas con facturación SUNAT.",
    openapi_tags=TAGS,
    contact={"name": "Zona Xtrema Bikes & Componentes", "url": "https://www.zonaxtrema.pe"},
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# El middleware de auditoría se registra antes que CORS para que mida el tiempo
# real de proceso; se ejecuta en orden inverso al de registro.
app.add_middleware(AuditMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _openapi_con_seguridad() -> dict:
    """Declara el esquema Bearer para que el botón Authorize de Swagger funcione."""
    from fastapi.openapi.utils import get_openapi

    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        summary=app.summary,
        description=app.description,
        tags=app.openapi_tags,
        contact=app.contact,
        routes=app.routes,
    )
    schema["components"].setdefault("securitySchemes", {})["BearerJWT"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    # Seguridad global; los endpoints públicos igual funcionan sin token.
    schema["security"] = [{"BearerJWT": []}]
    app.openapi_schema = schema
    return schema


app.openapi = _openapi_con_seguridad


app.include_router(api_router, prefix=settings.API_V1_PREFIX)
# Rutas cortas que cuelgan de la raíz: el QR de la ficha (/f) y el PDF público
# del comprobante que se manda por WhatsApp (/c), para no engordar el enlace.
app.include_router(publico.router)
app.include_router(publico_comprobante.router)


@app.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    """Liveness: el proceso responde."""
    return {"status": "ok", "environment": settings.ENVIRONMENT}


@app.get("/health/db", tags=["infra"])
def health_db() -> dict[str, str]:
    """Readiness: la base de datos responde."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": settings.POSTGRES_DB}
